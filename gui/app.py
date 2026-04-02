#!/usr/bin/env python3

import uuid
import threading
from datetime import datetime

from crypto import encrypt_entry, decrypt_entry, sign_file, verify_file
from storage import load_file, save_file
from sync import sync


class CalendarApp:

    def __init__(self, private_key):
        self.private_key = private_key
        self.public_key = private_key.public_key()
        self.entries = []
        self._sync_config_enc = None
        self.version = 0
        self.signature = None
        self.buffer = []
        self.unsigned = False
        self._reload()

    def _reload(self):
        self.entries, self._sync_config_enc, self.version, self.signature = load_file()
        self.buffer = []
        self.unsigned = False
        self._verify_and_build_buffer()

    def _verify_and_build_buffer(self):
        if self.signature is None:
            self.unsigned = True
        elif not verify_file(self.entries, self._sync_config_enc, self.version, self.signature, self.public_key):
            raise RuntimeError("Calendar file signature is invalid. File may have been tampered with.")

        for e in self.entries:
            try:
                dec = decrypt_entry(e, self.private_key)
                self.buffer.append({
                    "id": dec["id"],
                    "timestamp": dec["timestamp"],
                    "data": dec
                })
            except Exception:
                continue

        self.buffer.sort(key=lambda x: x["timestamp"])

    @property
    def sync_config(self):
        if self._sync_config_enc is None:
            return None
        try:
            return decrypt_entry(self._sync_config_enc, self.private_key)
        except Exception:
            return None

    def _save_and_sync(self, on_sync_done=None):
        new_version = self.version + 1
        new_sig = sign_file(self.entries, self._sync_config_enc, new_version, self.private_key)
        save_file(self.entries, self._sync_config_enc, new_version, new_sig)
        self._reload()

        config = self.sync_config
        if config is not None:
            def _run():
                msg = sync(config)
                if on_sync_done:
                    on_sync_done(msg)
            threading.Thread(target=_run, daemon=True).start()

    def get_entries(self):
        """Return list of decrypted entry dicts, sorted by timestamp."""
        return [e["data"] for e in self.buffer]

    def add_entry(self, title: str, date_str: str, time_str: str,
                  comments: list[str], on_sync_done=None):
        """
        date_str: DD.MM.YYYY
        time_str: HH:MM | all-day | unknown
        """
        date_dt = datetime.strptime(date_str, "%d.%m.%Y")

        if time_str not in ("all-day", "unknown"):
            t = datetime.strptime(time_str, "%H:%M")
            date_dt = date_dt.replace(hour=t.hour, minute=t.minute)

        timestamp = date_dt.timestamp()

        entry = {
            "id": str(uuid.uuid4()),
            "title": title,
            "date": date_str,
            "time": time_str,
            "timestamp": timestamp,
            "comments": comments,
        }

        encrypted = encrypt_entry(entry, self.public_key)

        pos = 0
        for i, e in enumerate(self.buffer):
            if timestamp < e["timestamp"]:
                pos = i
                break
            pos = i + 1

        self.entries.insert(pos, encrypted)
        self._save_and_sync(on_sync_done)

    def delete_entries(self, ids: list[str], on_sync_done=None):
        """Remove entries by ID list."""
        original_len = len(self.entries)
        self.entries = [e for e in self.entries if e["id"] not in ids]
        if len(self.entries) == original_len:
            return False
        self._save_and_sync(on_sync_done)
        return True

    def update_sync_config(self, sync_data: dict | None, on_sync_done=None):
        """Replace the stored sync config. Pass None to remove it."""
        from storage import SYNC_CONFIG_ID
        if sync_data is None:
            self._sync_config_enc = None
        else:
            entry = {
                "id": SYNC_CONFIG_ID,
                "url": sync_data["url"],
                "user": sync_data["user"],
                "password": sync_data["password"],
                "remote_path": sync_data["remote_path"],
            }
            self._sync_config_enc = encrypt_entry(entry, self.public_key)
        self._save_and_sync(on_sync_done)
