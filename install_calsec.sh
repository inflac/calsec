#!/bin/bash

# CalSec Installer for Tails
# Requires: dotfiles persistence enabled

set -e

INSTALL_DIR="$HOME/Persistent/programs/calsec"
CURRENT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"

echo "=== CalSec Installer ==="

# --- User check ---
if [ "$(whoami)" != "amnesia" ]; then
    echo "Please run as 'amnesia' user."
    exit 1
fi

# --- Persistent home check ---
if [ ! -d "$HOME/Persistent" ]; then
    echo "~/Persistent not found. Enable persistence in Tails first."
    exit 1
fi

# --- Uninstall option ---
if [[ "$1" == "--uninstall" || "$1" == "-u" ]]; then
    echo "[*] Uninstalling CalSec..."
    echo ""
    read -p "Also delete all keys (keys/ and pubkeys/)? [y/N]: " del_keys
    del_keys=${del_keys:-N}
    echo ""
    if [[ "$del_keys" == "y" || "$del_keys" == "Y" ]]; then
        read -p "WARNING: Keys cannot be recovered. Really delete all keys? [y/N]: " confirm_keys
        confirm_keys=${confirm_keys:-N}
        [[ "$confirm_keys" != "y" && "$confirm_keys" != "Y" ]] && del_keys=N
    fi

    read -p "Proceed with uninstall? [y/N]: " confirm
    confirm=${confirm:-N}
    if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
        echo "Uninstall cancelled."
        exit 0
    fi

    # Remove binary and icon
    for f in "$INSTALL_DIR/calsec" "$INSTALL_DIR/icon.png"; do
        [ -f "$f" ] && rm -f "$f" && echo "  Removed: $f"
    done

    # Optionally remove keys
    if [[ "$del_keys" == "y" || "$del_keys" == "Y" ]]; then
        [ -d "$INSTALL_DIR/keys" ]    && rm -rf "$INSTALL_DIR/keys"    && echo "  Removed: $INSTALL_DIR/keys"
        [ -d "$INSTALL_DIR/pubkeys" ] && rm -rf "$INSTALL_DIR/pubkeys" && echo "  Removed: $INSTALL_DIR/pubkeys"
    else
        echo "  Kept: $INSTALL_DIR/keys and $INSTALL_DIR/pubkeys"
    fi

    # Remove desktop entry (persistent file + session symlink)
    for DESKTOP_FILE in \
        "$HOME/Persistent/.local/share/applications/calsec.desktop" \
        "$HOME/.local/share/applications/calsec.desktop"; do
        [ -e "$DESKTOP_FILE" ] && rm -f "$DESKTOP_FILE" && echo "  Removed: $DESKTOP_FILE"
    done

    # Remove install dir if now empty
    if [ -d "$INSTALL_DIR" ]; then
        remaining=$(find "$INSTALL_DIR" -mindepth 1 | wc -l)
        if [ "$remaining" -eq 0 ]; then
            rmdir "$INSTALL_DIR"
            echo "  Removed: $INSTALL_DIR"
        else
            echo "  Kept: $INSTALL_DIR (still contains files)"
        fi
    fi

    echo ""
    echo "CalSec uninstalled."
    exit 0
fi

echo "[*] Installing to $INSTALL_DIR ..."

# --- Create structure ---
mkdir -p "$INSTALL_DIR/keys"
mkdir -p "$INSTALL_DIR/pubkeys"

# --- Copy files ---
cp "$CURRENT_DIR/calsec" "$INSTALL_DIR/"
cp "$CURRENT_DIR/icon.png" "$INSTALL_DIR/"
chmod +x "$INSTALL_DIR/calsec"

# --- Desktop entry ---
echo "[*] Creating desktop entry..."
DESKTOP_PERSIST_DIR="$HOME/Persistent/.local/share/applications"
DESKTOP_DIR="$HOME/.local/share/applications"
mkdir -p "$DESKTOP_PERSIST_DIR"
mkdir -p "$DESKTOP_DIR"

cat > "$DESKTOP_PERSIST_DIR/calsec.desktop" <<EOF
[Desktop Entry]
Name=CalSec
Comment=Zero trust calendar tool
Exec=$INSTALL_DIR/calsec
Icon=$INSTALL_DIR/icon.png
Type=Application
Categories=Utility;
Terminal=false
StartupNotify=true
EOF

chmod +x "$DESKTOP_PERSIST_DIR/calsec.desktop"

# Symlink into current session so the entry is available immediately
ln -sf "$DESKTOP_PERSIST_DIR/calsec.desktop" "$DESKTOP_DIR/calsec.desktop"

# --- Key generation (optional) ---
generate_key() {
    local KEY_DIR="$INSTALL_DIR/keys"
    local PUB_DIR="$INSTALL_DIR/pubkeys"

    echo ""
    echo "=== Key Generation ==="

    read -p "Enter your email: " email

    if [[ -z "$email" ]]; then
        echo "Email required."
        exit 1
    fi

    local email_clean
    email_clean=$(echo "$email" | tr '[:upper:]' '[:lower:]' | tr -d ' ')

    local user_hash
    local localpart
    localpart=$(echo "$email_clean" | cut -d '@' -f1)
    user_hash=$(echo -n "$localpart" | sha256sum | cut -d ' ' -f1 | cut -c1-16)

    local priv_key="$KEY_DIR/$user_hash.pem"
    local pub_key="$PUB_DIR/$user_hash.pub.pem"

    if [ -f "$priv_key" ]; then
        echo "Key already exists for this email: $priv_key"
        exit 1
    fi

    echo ""
    echo "Optional: Protect your private key with a password."
    echo "If you set one, you will need to enter it every time you start CalSec."
    echo ""

    read -p "Set a password? (y/n): " use_pw

    if [[ "$use_pw" == "y" || "$use_pw" == "Y" ]]; then
        read -s -p "Enter password: " pw1
        echo ""
        read -s -p "Confirm password: " pw2
        echo ""

        if [[ "$pw1" != "$pw2" ]]; then
            echo "Passwords do not match."
            exit 1
        fi

        if [[ -z "$pw1" ]]; then
            echo "Empty password not allowed."
            exit 1
        fi

        echo "[*] Generating password-protected keypair..."
        openssl ecparam -name prime256v1 -genkey -noout \
            | openssl ec -aes256 -out "$priv_key" -passout pass:"$pw1"
    else
        echo "[*] Generating keypair (no password)..."
        openssl ecparam -name prime256v1 -genkey -noout -out "$priv_key"
    fi

    openssl ec -in "$priv_key" -pubout -out "$pub_key" 2>/dev/null

    chmod 600 "$priv_key"

    echo ""
    echo "Keypair created."
    echo ""
    echo "Private key: $priv_key"
    echo ""
    echo "Send this PUBLIC KEY to the admin:"
    echo "  $pub_key"
    echo ""
    echo "And tell them your email: $email_clean"
}

echo ""
read -p "Generate keypair now? [y/N]: " choice
choice=${choice:-N}

case "$choice" in
    y|Y)
        generate_key
        ;;
    *)
        echo ""
        echo "You can generate a key later from within CalSec."
        ;;
esac

echo ""
echo "Installation complete."
echo ""
echo "Next steps:"
echo "1. Send your public key + email to the admin (after key generation)"
echo "2. Start CalSec from the Applications menu"
