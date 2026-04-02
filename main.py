#!/usr/bin/env python3

import json
import os
import uuid
import base64
import getpass
import sys
from datetime import datetime

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.asymmetric import ec

from sync import sync


DATA_FILE = "calendar.json"
KEY_PRIVATE = "calsec_private.pem"
KEY_PUBLIC = "calsec_public.pem"

SYNC_CONFIG_ID = "__sync_config__"


# ---------- Utility ----------

def b64(x): return base64.b64encode(x).decode()
def b64d(x): return base64.b64decode(x)


def load_file():
    if not os.path.exists(DATA_FILE):
        return [], None, 0, None
    try:
        with open(DATA_FILE, "r") as f:
            obj = json.load(f)
        if isinstance(obj, list):
            # Migrate old format (plain list, no signature, no sync config, no version)
            return obj, None, 0, None
        return obj.get("entries", []), obj.get("sync_config"), obj.get("version", 0), obj.get("signature")
    except Exception:
        print("Error: Failed to read calendar file.")
        sys.exit(1)


def save_file(entries, sync_config_enc=None, version=0, signature=None):
    try:
        with open(DATA_FILE, "w") as f:
            json.dump(
                {"version": version, "entries": entries, "sync_config": sync_config_enc, "signature": signature},
                f, indent=2
            )
    except Exception:
        print("Error: Failed to write calendar file.")
        sys.exit(1)


# ---------- Key Management ----------

def provision():
    print("Generating ECC keypair (SECP256R1)...")

    private_key = ec.generate_private_key(ec.SECP256R1())
    public_key = private_key.public_key()

    while True:
        pw1 = getpass.getpass("Enter password for private key: ")
        pw2 = getpass.getpass("Repeat password: ")

        if pw1 != pw2:
            print("Passwords do not match.")
        elif len(pw1) < 8:
            print("Password too short (minimum 8 characters).")
        else:
            break

    password = pw1.encode()

    try:
        with open(KEY_PRIVATE, "wb") as f:
            f.write(
                private_key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.PKCS8,
                    encryption_algorithm=serialization.BestAvailableEncryption(password)
                )
            )

        with open(KEY_PUBLIC, "wb") as f:
            f.write(
                public_key.public_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PublicFormat.SubjectPublicKeyInfo
                )
            )

        os.chmod(KEY_PRIVATE, 0o600)
        os.chmod(KEY_PUBLIC, 0o644)

    except Exception:
        print("Error: Failed to write key files.")
        sys.exit(1)

    print("Keys generated successfully.")

    # Nextcloud sync config (optional)
    print("\nNextcloud Sync Configuration (press Enter to skip)")
    url = input("Nextcloud URL (e.g. https://cloud.example.com): ").strip().rstrip("/")

    sync_config_enc = None
    if url:
        nc_user = input("Username: ").strip()
        nc_password = getpass.getpass("App password: ")
        remote_path = input(f"Remote path [{DATA_FILE}]: ").strip() or DATA_FILE
        if not remote_path.startswith("/"):
            remote_path = "/" + remote_path

        sync_data = {
            "id": SYNC_CONFIG_ID,
            "url": url,
            "user": nc_user,
            "password": nc_password,
            "remote_path": remote_path,
        }
        sync_config_enc = encrypt_entry(sync_data, public_key)
        print("Sync configuration encrypted and stored.")

    # On re-provision: existing entries cannot be decrypted with the new key
    existing_entries, _, existing_version, _ = load_file()
    if existing_entries:
        print("\nWarning: Existing entries cannot be decrypted with the new key.")
        answer = input("Clear existing entries? [y/N] ").strip().lower()
        if answer == "y":
            existing_entries = []

    new_version = existing_version + 1
    new_sig = sign_file(existing_entries, sync_config_enc, new_version, private_key)
    save_file(existing_entries, sync_config_enc, new_version, new_sig)


def load_private_key():
    if not os.path.exists(KEY_PRIVATE):
        print("Error: Private key not found.")
        sys.exit(1)

    password = getpass.getpass("Enter private key password: ").encode()

    try:
        with open(KEY_PRIVATE, "rb") as f:
            return serialization.load_pem_private_key(f.read(), password=password)
    except Exception:
        print("Error: Invalid password or corrupted key.")
        sys.exit(1)


def load_public_key():
    if not os.path.exists(KEY_PUBLIC):
        print("Error: Public key not found.")
        sys.exit(1)

    try:
        with open(KEY_PUBLIC, "rb") as f:
            return serialization.load_pem_public_key(f.read())
    except Exception:
        print("Error: Failed to load public key.")
        sys.exit(1)


# ---------- Crypto ----------

def derive_key(shared, salt):
    return HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        info=b'calsec-v2'
    ).derive(shared)


def canonical_file(entries, sync_config_enc, version):
    """Deterministic serialization of the full file content for signing."""
    return json.dumps(
        {"entries": entries, "sync_config": sync_config_enc, "version": version},
        sort_keys=True, separators=(',', ':')
    ).encode()


def sign_file(entries, sync_config_enc, version, private_key):
    data = canonical_file(entries, sync_config_enc, version)
    sig = private_key.sign(data, ec.ECDSA(hashes.SHA256()))
    return b64(sig)


def verify_file(entries, sync_config_enc, version, signature_b64, public_key):
    data = canonical_file(entries, sync_config_enc, version)
    try:
        public_key.verify(b64d(signature_b64), data, ec.ECDSA(hashes.SHA256()))
        return True
    except InvalidSignature:
        return False


def wrap_key(aes_key, public_key):
    eph = ec.generate_private_key(ec.SECP256R1())
    eph_pub_bytes = eph.public_key().public_bytes(
        serialization.Encoding.X962,
        serialization.PublicFormat.UncompressedPoint
    )

    # Random salt per key-wrapping operation for HKDF
    salt = os.urandom(32)
    shared = eph.exchange(ec.ECDH(), public_key)
    derived = derive_key(shared, salt)

    aesgcm = AESGCM(derived)
    iv = os.urandom(12)
    # AAD = ephemeral public key bytes — binds ciphertext to this specific ephemeral key
    wrapped = aesgcm.encrypt(iv, aes_key, eph_pub_bytes)

    return {
        "ephemeral_pub": b64(eph_pub_bytes),
        "iv_wrap": b64(iv),
        "wrapped_key": b64(wrapped),
        "hkdf_salt": b64(salt)
    }


def unwrap_key(entry, private_key):
    eph_pub_bytes = b64d(entry["ephemeral_pub"])
    eph_pub = ec.EllipticCurvePublicKey.from_encoded_point(
        ec.SECP256R1(),
        eph_pub_bytes
    )

    salt = b64d(entry["hkdf_salt"])
    shared = private_key.exchange(ec.ECDH(), eph_pub)
    derived = derive_key(shared, salt)

    aesgcm = AESGCM(derived)
    # AAD = ephemeral public key bytes — must match what was used during wrap_key
    return aesgcm.decrypt(
        b64d(entry["iv_wrap"]),
        b64d(entry["wrapped_key"]),
        eph_pub_bytes
    )


def encrypt_entry(entry, public_key):
    aes_key = AESGCM.generate_key(bit_length=256)
    aesgcm = AESGCM(aes_key)
    iv = os.urandom(12)

    plaintext = json.dumps(entry).encode()
    # AAD = entry ID bytes — binds ciphertext to this specific entry
    ciphertext = aesgcm.encrypt(iv, plaintext, entry["id"].encode())

    wrapped = wrap_key(aes_key, public_key)

    # Only id is stored in plaintext (required for delete).
    # All other data including timestamp is kept encrypted.
    return {
        "id": entry["id"],
        "iv": b64(iv),
        "ciphertext": b64(ciphertext),
        **wrapped
    }


def decrypt_entry(entry, private_key):
    aes_key = unwrap_key(entry, private_key)

    aesgcm = AESGCM(aes_key)
    # AAD = entry ID bytes — must match what was used during encrypt_entry
    plaintext = aesgcm.decrypt(
        b64d(entry["iv"]),
        b64d(entry["ciphertext"]),
        entry["id"].encode()
    )

    return json.loads(plaintext.decode())


# ---------- Input Validation ----------

def input_date():
    while True:
        value = input("Date (DD.MM.YYYY): ")
        try:
            return datetime.strptime(value, "%d.%m.%Y")
        except ValueError:
            print("Invalid date format.")


def input_time():
    while True:
        value = input("Time (HH:MM | all-day | unknown): ").strip().lower()

        if value in ["all-day", "unknown"]:
            return value, None

        try:
            t = datetime.strptime(value, "%H:%M")
            return value, t
        except ValueError:
            print("Invalid time format.")


def input_title():
    while True:
        title = input("Title: ").strip()
        if len(title) == 0:
            print("Title cannot be empty.")
        else:
            return title


# ---------- Core ----------

class CalendarApp:

    def __init__(self, private_key):
        self.private_key = private_key
        self.entries = []
        self._sync_config_enc = None
        self.version = 0
        self.signature = None
        self.buffer = []
        self._reload()

    def _reload(self):
        self.entries, self._sync_config_enc, self.version, self.signature = load_file()
        self.buffer = []
        self._verify_and_build_buffer()

    def _verify_and_build_buffer(self):
        pub = self.private_key.public_key()

        if self.signature is None:
            print("Warning: Calendar file is unsigned — entries may have been modified without authorization.")
        elif not verify_file(self.entries, self._sync_config_enc, self.version, self.signature, pub):
            print("Error: Calendar file signature is invalid. File may have been tampered with.")
            sys.exit(1)

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

    def _save_and_sync(self):
        new_version = self.version + 1
        new_sig = sign_file(self.entries, self._sync_config_enc, new_version, self.private_key)
        save_file(self.entries, self._sync_config_enc, new_version, new_sig)
        self._reload()
        sync(self.sync_config)

    def _find_buf(self, entry_id):
        return next((e for e in self.buffer if e["id"] == entry_id), None)

    def list(self):
        if not self.buffer:
            print("No entries found.")
            return

        for e in self.buffer:
            d = e["data"]
            n = len(d.get("comments", []))
            comment_info = f"  [{n} comment{'s' if n != 1 else ''}]" if n else ""
            print(f"  {d['id']}  {d['date']} {d['time']:>8}  {d['title']}{comment_info}")

    def view(self):
        entry_id = input("Entry ID: ").strip()
        buf = self._find_buf(entry_id)
        if not buf:
            print("Entry not found.")
            return

        d = buf["data"]
        print(f"\n  ID     : {d['id']}")
        print(f"  Title  : {d['title']}")
        print(f"  Date   : {d['date']}")
        print(f"  Time   : {d['time']}")
        comments = d.get("comments", [])
        if comments:
            print("  Comments:")
            for i, c in enumerate(comments, 1):
                print(f"    {i}. {c}")
        else:
            print("  Comments: none")

    def add(self, public_key):
        title = input_title()
        date_dt = input_date()
        time_str, time_obj = input_time()

        if time_obj:
            date_dt = date_dt.replace(hour=time_obj.hour, minute=time_obj.minute)

        comments = []
        while True:
            c = input("Comment (press Enter to finish): ").strip()
            if not c:
                break
            comments.append(c)

        timestamp = date_dt.timestamp()

        entry = {
            "id": str(uuid.uuid4()),
            "title": title,
            "date": date_dt.strftime("%d.%m.%Y"),
            "time": time_str,
            "timestamp": timestamp,
            "comments": comments,
        }

        encrypted = encrypt_entry(entry, public_key)

        pos = 0
        for i, e in enumerate(self.buffer):
            if timestamp < e["timestamp"]:
                pos = i
                break
            pos = i + 1

        self.entries.insert(pos, encrypted)
        self._save_and_sync()

        print("Entry added.")

    def delete(self, ids):
        if not ids:
            print("Error: No IDs provided.")
            return

        original_len = len(self.entries)
        self.entries = [e for e in self.entries if e["id"] not in ids]

        if len(self.entries) == original_len:
            print("No matching entries found.")
        else:
            self._save_and_sync()
            print("Entries deleted.")


# ---------- Menu ----------

def print_menu():
    print("\n  1  List entries")
    print("  2  Add entry")
    print("  3  Delete entry")
    print("  4  View entry")
    print("  0  Exit")


def run():
    if not os.path.exists(KEY_PRIVATE) or not os.path.exists(KEY_PUBLIC):
        print("No keys found.")
        answer = input("Generate new keypair now? [y/N] ").strip().lower()
        if answer != "y":
            return
        provision()

    priv = load_private_key()
    pub = load_public_key()
    app = CalendarApp(priv)

    while True:
        print_menu()

        try:
            choice = input("\n> ").strip()
        except EOFError:
            print("\nGoodbye.")
            break

        if choice in ("0", "exit", "quit"):
            print("Goodbye.")
            break
        elif choice == "1":
            app.list()
        elif choice == "2":
            app.add(pub)
        elif choice == "3":
            ids_input = input("ID(s) to delete (space-separated): ").strip()
            if ids_input:
                app.delete(ids_input.split())
        elif choice == "4":
            app.view()
        else:
            print("Unknown option.")


def main():
    try:
        run()
    except KeyboardInterrupt:
        print("\nGoodbye.")


if __name__ == "__main__":
    main()
