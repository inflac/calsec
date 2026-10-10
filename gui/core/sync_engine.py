"""Uploading local changes and downloading remote ones without lost updates."""

import copy
import json
import threading

import i18n
import storage
from crypto import (
    format_fingerprint,
    normalize_fingerprint,
    pem_to_public_key,
    sign_keys_fingerprint,
    verify_entries,
    verify_users,
)


class SyncMixin:
    """Change + sync logic of CalendarApp."""

    _MAX_SYNC_CONFLICTS = 5

    # -- Background work -------------------------------------------------------

    @property
    def is_syncing(self) -> bool:
        """True while an upload or download is running or waiting to run."""
        with self._lock:
            return self._active_syncs > 0

    @property
    def has_unsynced_changes(self) -> bool:
        """True if local changes have not reached the server yet."""
        with self._lock:
            return bool(self._pending)

    def _run_in_background(self, fn) -> None:
        """Run fn in a daemon thread and count it as an active sync until it ends."""
        with self._lock:
            self._active_syncs += 1

        def _run():
            try:
                fn()
            finally:
                with self._lock:
                    self._active_syncs -= 1

        threading.Thread(target=_run, daemon=True).start()

    # -- Change + upload -------------------------------------------------------

    def _commit(self, op, on_sync_done=None) -> None:
        """Apply op locally, save, and upload without overwriting others' changes.

        op mutates the in-memory state and returns the changed section
        ("entries", "users" or "both"), or None if there is nothing to do.
        It must be safe to run again on a newer state: if someone else uploaded
        in the meantime, their file is loaded and all pending ops are re-applied.
        """
        with self._lock:
            snap = self._snapshot()
            written = False
            try:
                changed = op()
                if changed is None:
                    return
                written = True
                self._write_local(changed)
            except Exception:
                self._restore(snap)
                if written:
                    storage.save_file(self._raw_state())
                    self._reload()
                raise
            sync_enabled = self.sync_config is not None
            if sync_enabled:
                self._pending.append(op)
            else:
                self._base = self._snapshot()
        if sync_enabled:
            self._start_push(on_sync_done)

    def _start_push(self, on_sync_done=None) -> None:
        def _run():
            with self._sync_lock:
                try:
                    msg, is_error = self._push_pending()
                except Exception as exc:
                    msg, is_error = i18n._("sync_err_exception").format(exc=exc), True
            if on_sync_done:
                on_sync_done(msg, is_error)

        self._run_in_background(_run)

    def _push_pending(self) -> tuple[str, bool]:
        """Upload pending local changes. The caller must hold _sync_lock.

        The remote file is downloaded first. If someone else changed it since
        our last sync, their version is loaded and the pending changes are
        re-applied on top. The upload only succeeds if the remote file still
        has the ETag we just read, so a change that lands in between is
        detected and handled the same way.
        """
        import sync as _sync

        merged = False
        dropped = 0
        conflicts = 0
        while True:
            with self._lock:
                if not self._pending:
                    return self._push_summary(i18n._("sync_pull_ok"), merged, dropped)
                config = self.sync_config
            if config is None:
                with self._lock:
                    self._pending.clear()
                    self._base = self._snapshot()
                return i18n._("sync_not_configured"), False

            remote = _sync.fetch(config)
            if remote.status == "error":
                return remote.msg, True

            with self._lock:
                if remote.status == "ok" and not self._matches_base(remote.data):
                    error, n_dropped = self._rebase_onto(remote.data)
                    if error:
                        return error, True
                    merged = True
                    dropped += n_dropped
                    if not self._pending:
                        return self._push_summary(i18n._("sync_pull_ok"), merged, dropped)
                body = json.dumps(self._raw_state(), indent=2).encode("utf-8")
                pushed = self._snapshot()
                n_pushed = len(self._pending)

            result = _sync.push(
                config, body,
                if_match=remote.etag if remote.status == "ok" else None,
                create_only=remote.status == "missing",
            )
            if result.status == "conflict":
                conflicts += 1
                if conflicts >= self._MAX_SYNC_CONFLICTS:
                    return i18n._("sync_err_conflict_unresolved"), True
                continue
            if result.status != "ok":
                return result.msg, True

            with self._lock:
                del self._pending[:n_pushed]
                self._base = pushed
                if not self._pending:
                    return self._push_summary(result.msg, merged, dropped)

    @staticmethod
    def _push_summary(msg: str, merged: bool, dropped: int) -> tuple[str, bool]:
        if merged:
            msg = i18n._("sync_merged")
        if dropped:
            return i18n._("sync_ops_dropped").format(msg=msg, count=dropped), True
        return msg, False

    def _matches_base(self, data: dict) -> bool:
        """True if data is the remote state our pending changes build on."""
        base = self._base
        return (data.get("version_users") == base["version_users"]
                and data.get("version_entries") == base["version_entries"]
                and data.get("sig_users") == base["sig_users"]
                and data.get("sig_entries") == base["sig_entries"])

    @staticmethod
    def _verify_remote(data: dict) -> str | None:
        """Verify both signatures of a downloaded file against its own keys.
        Returns an error message, or None if the file is consistently signed."""
        sign_keys = data.get("sign_keys") or {}
        sig_users = data.get("sig_users")
        sig_entries = data.get("sig_entries")
        if not sig_users or not sig_entries or not sign_keys:
            return i18n._("sync_err_missing_signatures")
        try:
            kpub_admin_sign = pem_to_public_key(sign_keys["admin"])
            kpub_edit_sign = pem_to_public_key(sign_keys["edit"])
        except Exception:
            return i18n._("sync_err_users_sig_invalid")
        if not verify_users(data.get("version_users"), sign_keys, data.get("users", {}),
                            data.get("sync_config"), sig_users, kpub_admin_sign):
            return i18n._("sync_err_users_sig_invalid")
        if not verify_entries(data.get("version_entries"), data.get("entries", []),
                              sig_entries, kpub_edit_sign):
            return i18n._("sync_err_entries_sig_invalid")
        return None

    def _rebase_onto(self, data: dict) -> tuple[str | None, int]:
        """Load a newer remote file and re-apply pending ops on top of it.

        The caller must hold _lock. Returns (error, dropped). On error the
        local state is left unchanged. dropped counts pending ops that no
        longer apply to the remote state.
        """
        error = self._verify_remote(data)
        if error:
            return error, 0
        # Only build on files signed with the keys we already trust. A key
        # change needs the trust prompt of a manual sync.
        if data.get("sign_keys") != self._base["sign_keys"]:
            return i18n._("sync_err_rebase_keys_changed"), 0

        local = self._snapshot()
        self._restore(self._base)
        try:
            storage.save_file(data)
            self._reload()
        except Exception:
            self._restore(local)
            storage.save_file(self._raw_state())
            self._reload()
            return i18n._("sync_err_rebase_failed"), 0
        self._base = self._snapshot()
        return None, self._reapply_pending()

    def _reapply_pending(self) -> int:
        changed = set()
        kept = []
        dropped = 0
        for op in self._pending:
            snap = self._snapshot()
            try:
                result = op()
            except Exception:
                self._restore(snap)
                dropped += 1
                continue
            if result is not None:
                changed.add(result)
                kept.append(op)
        self._pending[:] = kept
        if changed:
            self._write_local(
                "both" if "both" in changed or len(changed) > 1 else changed.pop())
        return dropped

    # -- Download (all users) --------------------------------------------------

    def sync_pull(self, on_done=None, request_trust=None) -> None:
        """Download a newer calendar.json in the background.

        Local changes that are not uploaded yet are kept: they are re-applied
        on top of the downloaded state and uploaded.
        """
        config = self.sync_config
        if config is None:
            if on_done:
                on_done(i18n._("sync_not_configured"), False)
            return

        def _run():
            with self._sync_lock:
                try:
                    msg, is_error = self._pull(config, request_trust)
                except Exception as exc:
                    msg, is_error = i18n._("sync_err_exception").format(exc=exc), True
            if on_done:
                on_done(msg, is_error)

        self._run_in_background(_run)

    def _pull(self, config, request_trust) -> tuple[str, bool]:
        """Download and apply the remote file. The caller must hold _sync_lock."""
        import sync as _sync

        with self._lock:
            has_pending = bool(self._pending)
        if has_pending:
            msg, is_error = self._push_pending()
            if msg != i18n._("sync_err_rebase_keys_changed"):
                return msg, is_error
            # The signing keys changed: fall through to the trust prompt. The
            # pending changes were signed with keys that are no longer valid.

        remote = _sync.fetch(config)
        if remote.status != "ok":
            return remote.msg, True
        data = remote.data

        error = self._verify_remote(data)
        if error:
            return error, True

        remote_sign_keys = data["sign_keys"]
        with self._lock:
            trusted_sign_keys = copy.deepcopy(self._base["sign_keys"])
        sign_keys_changed = remote_sign_keys != trusted_sign_keys
        if sign_keys_changed:
            if request_trust is None:
                return i18n._("sync_err_sign_keys_mismatch"), True
            remote_fingerprint = sign_keys_fingerprint(remote_sign_keys)
            expected = request_trust(remote_fingerprint)
            if expected is None:
                return i18n._("sync_err_sign_keys_not_confirmed"), True
            if normalize_fingerprint(expected) != remote_fingerprint:
                return i18n._("sync_err_fingerprint_mismatch").format(
                    fingerprint=format_fingerprint(remote_fingerprint)), True

        with self._lock:
            if self._pending and not sign_keys_changed:
                # Changes made while this download was running.
                if self._matches_base(data):
                    return remote.msg, False
                error, dropped = self._rebase_onto(data)
                if error:
                    return error, True
                return self._push_summary(remote.msg, False, dropped)

            dropped_pending = bool(self._pending)
            if (not dropped_pending
                    and data["version_users"] <= self.version_users
                    and data["version_entries"] <= self.version_entries):
                return i18n._("sync_up_to_date"), False

            local = self._snapshot()
            if dropped_pending:
                self._pending.clear()
                self._restore(self._base)
            try:
                storage.save_file(data)
                self._reload()
            except Exception:
                self._restore(local)
                storage.save_file(self._raw_state())
                self._reload()
                return i18n._("sync_err_load_failed"), True
            self._base = self._snapshot()

        msg = remote.msg
        if sign_keys_changed:
            msg = i18n._("sync_sign_keys_accepted").format(msg=msg)
        if dropped_pending:
            return i18n._("sync_pending_dropped").format(msg=msg), True
        return msg, False

