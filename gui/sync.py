#!/usr/bin/env python3

import os

from storage import DATA_FILE


def sync(config):
    """Upload calendar.json to Nextcloud. config is a plain dict or None."""
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

    url = (
        f"{config['url']}/remote.php/dav/files/"
        f"{config['user']}{config['remote_path']}"
    )
    auth = (config["user"], config["password"])

    try:
        response = requests.put(
            url,
            data=data,
            auth=auth,
            headers={"Content-Type": "application/json"},
            timeout=30,
        )
    except requests.exceptions.MissingSchema:
        return (
            f"Sync error: Ungültige URL '{config['url']}' — "
            "URL muss mit http:// oder https:// beginnen."
        )
    except requests.exceptions.SSLError:
        return "Sync error: SSL certificate verification failed."
    except requests.exceptions.ConnectionError:
        return "Sync error: Could not connect to Nextcloud."
    except requests.exceptions.Timeout:
        return "Sync error: Connection timed out."

    if response.status_code in (200, 201, 204):
        return f"Synced to {config['url']} ({response.status_code})."
    elif response.status_code == 401:
        return "Sync error: Authentication failed."
    elif response.status_code == 403:
        return "Sync error: Access denied."
    elif response.status_code == 404:
        return "Sync error: Remote directory does not exist."
    else:
        return f"Sync error: Unexpected response {response.status_code}."
