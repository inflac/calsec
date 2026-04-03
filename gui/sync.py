#!/usr/bin/env python3

import os

from storage import DATA_FILE


def sync_push(config) -> str:
    """Upload calendar.json to a WebDAV URL via PUT. Returns a status message."""
    if config is None:
        return None

    try:
        import requests
    except ImportError:
        return "Sync error: 'requests' library not installed."

    if not os.path.exists(DATA_FILE):
        return f"Sync: {DATA_FILE} not found, skipping."

    try:
        with open(DATA_FILE, "rb") as f:
            data = f.read()
    except Exception:
        return "Sync error: Failed to read calendar file."

    url  = config["webdav_url"]
    auth = (config["auth_user"], config["password"])

    try:
        response = requests.put(
            url, data=data, auth=auth,
            headers={"Content-Type": "application/json"},
            timeout=30,
        )
    except requests.exceptions.MissingSchema:
        return (f"Sync error: Ungültige URL '{url}' — "
                "URL muss mit http:// oder https:// beginnen.")
    except requests.exceptions.SSLError:
        return "Sync error: SSL certificate verification failed."
    except requests.exceptions.ConnectionError:
        return "Sync error: Could not connect to server."
    except requests.exceptions.Timeout:
        return "Sync error: Connection timed out."

    if response.status_code in (200, 201, 204):
        return f"Synced ({response.status_code})."
    elif response.status_code == 401:
        return "Sync error: Authentication failed."
    elif response.status_code == 403:
        return "Sync error: Access denied."
    elif response.status_code == 404:
        return "Sync error: Remote path does not exist."
    else:
        return f"Sync error: Unexpected response {response.status_code}."


def sync_pull(config) -> tuple:
    """Download calendar.json from a WebDAV URL via GET.
    Returns (data_dict, message). data_dict is None on failure."""
    if config is None:
        return None, "Kein Sync konfiguriert."

    try:
        import requests
    except ImportError:
        return None, "Sync error: 'requests' library not installed."

    url  = config["webdav_url"]
    auth = (config["auth_user"], config["password"])

    try:
        response = requests.get(url, auth=auth, timeout=30)
    except requests.exceptions.MissingSchema:
        return (None, f"Sync error: Ungültige URL '{url}' — "
                "URL muss mit http:// oder https:// beginnen.")
    except requests.exceptions.SSLError:
        return None, "Sync error: SSL certificate verification failed."
    except requests.exceptions.ConnectionError:
        return None, "Sync error: Could not connect to server."
    except requests.exceptions.Timeout:
        return None, "Sync error: Connection timed out."

    if response.status_code == 200:
        try:
            import json as _json
            return _json.loads(response.content.decode("utf-8-sig")), "Synchronisiert."
        except Exception:
            ct = response.headers.get("Content-Type", "unbekannt")
            snippet = response.text[:300].replace("\n", " ")
            return None, (f"Sync error: Ungültiges JSON in der Antwort.\n"
                          f"Content-Type: {ct}\n"
                          f"Antwort: {snippet}")
    elif response.status_code == 401:
        return None, "Sync error: Authentication failed."
    elif response.status_code == 404:
        return None, "Kein Remote-Kalender gefunden."
    else:
        return None, f"Sync error: Unexpected response {response.status_code}."
