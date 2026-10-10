#!/usr/bin/env python3

import os
from typing import NamedTuple

import i18n
from storage import DATA_FILE

_TOR_PROXIES = {
    "http":  "socks5h://127.0.0.1:9050",
    "https": "socks5h://127.0.0.1:9050",
}


class FetchResult(NamedTuple):
    """Result of downloading calendar.json.

    status: "ok" (data is set), "missing" (no remote file yet) or "error".
    etag:   the server's ETag for the downloaded file, if it sent one.
    """
    status: str
    data: dict | None
    etag: str | None
    msg: str


class PushResult(NamedTuple):
    """Result of uploading calendar.json.

    status: "ok", "conflict" (the remote file changed since it was read) or "error".
    """
    status: str
    msg: str


def _calendar_url(config: dict) -> str:
    """Build the full calendar.json URL from the stored folder URL."""
    return config["webdav_url"].rstrip("/") + "/calendar.json"


def _etag(response) -> str | None:
    headers = getattr(response, "headers", None) or {}
    return headers.get("ETag") or headers.get("etag")


def fetch(config) -> FetchResult:
    """Download calendar.json from a WebDAV URL via GET, including its ETag."""
    if config is None:
        return FetchResult("error", None, None, i18n._("sync_not_configured"))

    try:
        import requests
    except ImportError:
        return FetchResult("error", None, None, i18n._("sync_err_no_requests"))

    url  = _calendar_url(config)
    auth = (config["auth_user"], config["password"])

    try:
        response = requests.get(url, auth=auth, proxies=_TOR_PROXIES, timeout=30)
    except requests.exceptions.MissingSchema:
        return FetchResult("error", None, None,
                           i18n._("sync_err_invalid_url").format(url=url))
    except requests.exceptions.SSLError:
        return FetchResult("error", None, None, i18n._("sync_err_ssl"))
    except requests.exceptions.ConnectionError:
        return FetchResult("error", None, None, i18n._("sync_err_connection"))
    except requests.exceptions.Timeout:
        return FetchResult("error", None, None, i18n._("sync_err_timeout"))

    if response.status_code == 200:
        try:
            import json as _json
            data = _json.loads(response.content.decode("utf-8-sig"))
        except Exception:
            ct      = response.headers.get("Content-Type", i18n._("sync_unknown"))
            snippet = response.text[:300].replace("\n", " ")
            return FetchResult("error", None, None,
                               i18n._("sync_err_invalid_json").format(ct=ct, snippet=snippet))
        return FetchResult("ok", data, _etag(response), i18n._("sync_pull_ok"))
    elif response.status_code == 401:
        return FetchResult("error", None, None, i18n._("sync_err_auth"))
    elif response.status_code == 404:
        return FetchResult("missing", None, None, i18n._("sync_err_no_remote"))
    else:
        return FetchResult("error", None, None,
                           i18n._("sync_err_unexpected").format(code=response.status_code))


def push(config, body: bytes, if_match: str | None = None,
         create_only: bool = False) -> PushResult:
    """Upload body as calendar.json via PUT.

    if_match:    only replace the remote file if it still has this ETag.
    create_only: only upload if no remote file exists yet.
    Either condition failing yields status "conflict" (HTTP 412).
    """
    if config is None:
        return PushResult("error", i18n._("sync_not_configured"))

    try:
        import requests
    except ImportError:
        return PushResult("error", i18n._("sync_err_no_requests"))

    url  = _calendar_url(config)
    auth = (config["auth_user"], config["password"])
    headers = {"Content-Type": "application/json"}
    if if_match:
        headers["If-Match"] = if_match
    elif create_only:
        headers["If-None-Match"] = "*"

    try:
        response = requests.put(
            url, data=body, auth=auth,
            headers=headers,
            proxies=_TOR_PROXIES,
            timeout=30,
        )
    except requests.exceptions.MissingSchema:
        return PushResult("error", i18n._("sync_err_invalid_url").format(url=url))
    except requests.exceptions.SSLError:
        return PushResult("error", i18n._("sync_err_ssl"))
    except requests.exceptions.ConnectionError:
        return PushResult("error", i18n._("sync_err_connection"))
    except requests.exceptions.Timeout:
        return PushResult("error", i18n._("sync_err_timeout"))

    if response.status_code in (200, 201, 204):
        return PushResult("ok", i18n._("sync_push_ok").format(code=response.status_code))
    elif response.status_code == 412:
        return PushResult("conflict", i18n._("sync_err_conflict"))
    elif response.status_code == 401:
        return PushResult("error", i18n._("sync_err_auth"))
    elif response.status_code == 403:
        return PushResult("error", i18n._("sync_err_access_denied"))
    elif response.status_code == 404:
        return PushResult("error", i18n._("sync_err_path_not_found"))
    else:
        return PushResult("error",
                          i18n._("sync_err_unexpected").format(code=response.status_code))


def sync_push(config) -> tuple:
    """Upload the local calendar.json unconditionally.
    Returns (ok, message). ok is False on failure."""
    if config is None:
        return False, i18n._("sync_not_configured")

    try:
        import requests  # noqa: F401
    except ImportError:
        return False, i18n._("sync_err_no_requests")

    if not os.path.exists(DATA_FILE):
        return False, i18n._("sync_file_not_found").format(file=DATA_FILE)

    try:
        with open(DATA_FILE, "rb") as f:
            data = f.read()
    except Exception:
        return False, i18n._("sync_err_read_failed")

    result = push(config, data)
    return result.status == "ok", result.msg


def sync_pull(config) -> tuple:
    """Download calendar.json from a WebDAV URL via GET.
    Returns (data_dict, message). data_dict is None on failure."""
    result = fetch(config)
    return result.data, result.msg
