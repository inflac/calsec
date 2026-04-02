#!/usr/bin/env python3

import os
import sys

try:
    import requests
except ImportError:
    print("Error: 'requests' library not installed. Run: pip install requests")
    sys.exit(1)

DATA_FILE = "calendar.json"


def _webdav_url(config):
    return (
        f"{config['url']}/remote.php/dav/files/"
        f"{config['user']}{config['remote_path']}"
    )


def sync(config):
    """Upload calendar.json to Nextcloud. config is a plain dict or None."""
    if config is None:
        return

    if not os.path.exists(DATA_FILE):
        print(f"Sync: {DATA_FILE} not found, skipping.")
        return

    try:
        with open(DATA_FILE, "rb") as f:
            data = f.read()
    except Exception:
        print("Sync error: Failed to read calendar file.")
        return

    url = _webdav_url(config)
    auth = (config["user"], config["password"])

    try:
        response = requests.put(
            url,
            data=data,
            auth=auth,
            headers={"Content-Type": "application/json"},
            timeout=30,
        )
    except requests.exceptions.SSLError:
        print("Sync error: SSL certificate verification failed.")
        return
    except requests.exceptions.ConnectionError:
        print("Sync error: Could not connect to Nextcloud.")
        return
    except requests.exceptions.Timeout:
        print("Sync error: Connection timed out.")
        return

    if response.status_code in (200, 201, 204):
        print(f"Synced to {config['url']} ({response.status_code}).")
    elif response.status_code == 401:
        print("Sync error: Authentication failed. Check username and app password.")
    elif response.status_code == 403:
        print("Sync error: Access denied. Check remote path and permissions.")
    elif response.status_code == 404:
        print("Sync error: Remote directory does not exist.")
    else:
        print(f"Sync error: Unexpected response {response.status_code}.")
