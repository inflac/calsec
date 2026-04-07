#!/usr/bin/env python3

import os

import i18n
from storage import DATA_FILE

_TOR_PROXIES = {
    "http":  "socks5h://127.0.0.1:9050",
    "https": "socks5h://127.0.0.1:9050",
}


def _calendar_url(config: dict) -> str:
    """Build the full calendar.json URL from the stored folder URL."""
    return config["webdav_url"].rstrip("/") + "/calendar.json"


def sync_push(config) -> str:
    """Upload calendar.json to a WebDAV URL via PUT. Returns a status message."""
    if config is None:
        return None

    try:
        import requests
    except ImportError:
        return i18n._("sync_err_no_requests")

    if not os.path.exists(DATA_FILE):
        return i18n._("sync_file_not_found").format(file=DATA_FILE)

    try:
        with open(DATA_FILE, "rb") as f:
            data = f.read()
    except Exception:
        return i18n._("sync_err_read_failed")

    url  = _calendar_url(config)
    auth = (config["auth_user"], config["password"])

    try:
        response = requests.put(
            url, data=data, auth=auth,
            headers={"Content-Type": "application/json"},
            proxies=_TOR_PROXIES,
            timeout=30,
        )
    except requests.exceptions.MissingSchema:
        return i18n._("sync_err_invalid_url").format(url=url)
    except requests.exceptions.SSLError:
        return i18n._("sync_err_ssl")
    except requests.exceptions.ConnectionError:
        return i18n._("sync_err_connection")
    except requests.exceptions.Timeout:
        return i18n._("sync_err_timeout")

    if response.status_code in (200, 201, 204):
        return i18n._("sync_push_ok").format(code=response.status_code)
    elif response.status_code == 401:
        return i18n._("sync_err_auth")
    elif response.status_code == 403:
        return i18n._("sync_err_access_denied")
    elif response.status_code == 404:
        return i18n._("sync_err_path_not_found")
    else:
        return i18n._("sync_err_unexpected").format(code=response.status_code)


def sync_pull(config) -> tuple:
    """Download calendar.json from a WebDAV URL via GET.
    Returns (data_dict, message). data_dict is None on failure."""
    if config is None:
        return None, i18n._("sync_not_configured")

    try:
        import requests
    except ImportError:
        return None, i18n._("sync_err_no_requests")

    url  = _calendar_url(config)
    auth = (config["auth_user"], config["password"])

    try:
        response = requests.get(url, auth=auth, proxies=_TOR_PROXIES, timeout=30)
    except requests.exceptions.MissingSchema:
        return None, i18n._("sync_err_invalid_url").format(url=url)
    except requests.exceptions.SSLError:
        return None, i18n._("sync_err_ssl")
    except requests.exceptions.ConnectionError:
        return None, i18n._("sync_err_connection")
    except requests.exceptions.Timeout:
        return None, i18n._("sync_err_timeout")

    if response.status_code == 200:
        try:
            import json as _json
            return _json.loads(response.content.decode("utf-8-sig")), i18n._("sync_pull_ok")
        except Exception:
            ct      = response.headers.get("Content-Type", i18n._("sync_unknown"))
            snippet = response.text[:300].replace("\n", " ")
            return None, i18n._("sync_err_invalid_json").format(ct=ct, snippet=snippet)
    elif response.status_code == 401:
        return None, i18n._("sync_err_auth")
    elif response.status_code == 404:
        return None, i18n._("sync_err_no_remote")
    else:
        return None, i18n._("sync_err_unexpected").format(code=response.status_code)
