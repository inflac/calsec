"""Onboarding text an admin sends to a new user."""

import i18n


def build_onboarding_text(identifier: str, sync_config: dict, fingerprint: str) -> str:
    """Return a standardized onboarding message for a user."""
    if not sync_config:
        raise RuntimeError(i18n._("app_err_sync_config_unavailable"))
    return (
        "CalSec Onboarding\n\n"
        f"Identifier: {identifier}\n\n"
        "1. Install CalSec.\n"
        "2. Generate your local keypair.\n"
        "3. Send your public key and identifier to the admin.\n"
        "4. Wait until the admin confirms that your user has been added.\n"
        "5. Enter the following sync data in CalSec:\n\n"
        f"WebDAV URL: {sync_config['webdav_url']}\n"
        f"Username: {sync_config['auth_user']}\n"
        f"App Password: {sync_config['password']}\n\n"
        "6. On the first calendar download, compare this signing fingerprint exactly:\n\n"
        f"{fingerprint}\n\n"
        "If the fingerprint does not match exactly, stop and contact the admin.\n"
        "Never share your private key."
    )

