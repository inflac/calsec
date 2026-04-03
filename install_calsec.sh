#!/bin/bash

# Calsec Installer for Tails
# Requires: dotfiles persistence enabled

set -e

INSTALL_DIR="$HOME/Persistent/programs/calsec"
CURRENT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"

echo "=== Calsec Installer ==="

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
mkdir -p "$HOME/.local/share/applications"

cat > "$HOME/.local/share/applications/calsec.desktop" <<EOF
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

chmod +x "$HOME/.local/share/applications/calsec.desktop"

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
    user_hash=$(echo -n "$email_clean" | sha256sum | cut -d ' ' -f1)

    local priv_key="$KEY_DIR/$user_hash.pem"
    local pub_key="$PUB_DIR/$user_hash.pub.pem"

    if [ -f "$priv_key" ]; then
        echo "Key already exists for this email: $priv_key"
        exit 1
    fi

    echo ""
    echo "Optional: Protect your private key with a password."
    echo "If you set one, you will need to enter it every time you start Calsec."
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
        echo "You can generate a key later from within Calsec."
        ;;
esac

echo ""
echo "Installation complete."
echo ""
echo "Next steps:"
echo "1. Send your public key + email to the admin (after key generation)"
echo "2. Start Calsec from the Applications menu"
