#!/usr/bin/env python3
"""CalendarApp: the decrypted, verified calendar of the logged-in user.

The logic lives in core/ and is combined here:
  core.state        — load, verify, snapshot and save the local file
  core.sync_engine  — upload and download without overwriting others
  core.entries      — entry queries and changes
  core.users        — users, roles, signing keys and sync config
"""

import threading

from core.entries import EntriesMixin
from core.state import StateMixin
from core.sync_engine import SyncMixin
from core.users import UsersMixin
from crypto import sign_keys_fingerprint


class CalendarApp(StateMixin, SyncMixin, EntriesMixin, UsersMixin):

    def __init__(self, sym_key_cal: bytes,
                 kpriv_admin_sign=None,
                 kpriv_edit_sign=None,
                 role: str = "viewer",
                 user_hash: str | None = None):
        self._sym_key_cal      = sym_key_cal
        self._kpriv_admin_sign = kpriv_admin_sign  # None unless admin
        self._kpriv_edit_sign  = kpriv_edit_sign   # None unless admin or editor
        self._role             = role
        self._is_admin         = role == "admin"
        self._user_hash        = user_hash

        # _lock guards the in-memory and local file state. _sync_lock makes
        # sure only one download/upload sequence talks to the server at a time.
        self._lock      = threading.RLock()
        self._sync_lock = threading.Lock()
        # Local changes not yet on the server, as re-applicable operations.
        self._pending: list = []
        # Number of upload/download threads that are running or waiting.
        self._active_syncs = 0

        self.buffer   = []
        self._reload()
        # Last state known to be on the server; pending ops build on top of it.
        self._base = self._snapshot()

    # ── Properties ────────────────────────────────────────────────────────────

    @property
    def role(self) -> str:
        return self._role

    @property
    def is_admin(self) -> bool:
        return self._is_admin

    @property
    def can_edit(self) -> bool:
        return self._kpriv_edit_sign is not None

    @property
    def fingerprint(self) -> str:
        return sign_keys_fingerprint(self._sign_keys)

    @property
    def sync_config(self):
        return self._sync_config

