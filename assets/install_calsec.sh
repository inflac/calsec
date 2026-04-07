#!/bin/bash

# CalSec Installer for Tails
# Requires: Persistent Storage enabled, with "Dotfiles" feature active

set -e

INSTALL_DIR="$HOME/Persistent/programs/calsec"
CURRENT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
SCRIPT_NAME="$(basename "${BASH_SOURCE[0]}")"

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

# --- Dotfiles persistence check ---
if [ ! -d "/live/persistence/TailsData_unlocked/dotfiles" ]; then
    echo "WARNING: Dotfiles persistence not found at /live/persistence/TailsData_unlocked/dotfiles"
    echo "         Enable the 'Dotfiles' feature in Tails Persistent Storage settings,"
    echo "         otherwise the application menu entry will be lost after reboot."
    echo ""
fi

# --- Menu ---
echo ""
is_installed=false
[ -f "$INSTALL_DIR/calsec" ] && is_installed=true

echo "What would you like to do?"
echo "  1) Install"
if $is_installed; then
    echo "  2) Uninstall"
fi
echo "  0) Cancel"
echo ""
read -p "Choice: " menu_choice

case "$menu_choice" in
    1)
        : # fall through to install
        ;;
    2)
        if ! $is_installed; then
            echo "Invalid choice."
            exit 1
        fi

        echo ""
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

        # Remove binary, icon, installer and calendar.json
        for f in "$INSTALL_DIR/calsec" "$INSTALL_DIR/icon.png" "$INSTALL_DIR/$SCRIPT_NAME" "$INSTALL_DIR/calendar.json"; do
            [ -f "$f" ] && rm -f "$f" && echo "  Removed: $f"
        done

        # Optionally remove keys
        if [[ "$del_keys" == "y" || "$del_keys" == "Y" ]]; then
            [ -d "$INSTALL_DIR/keys" ]    && rm -rf "$INSTALL_DIR/keys"    && echo "  Removed: $INSTALL_DIR/keys"
            [ -d "$INSTALL_DIR/pubkeys" ] && rm -rf "$INSTALL_DIR/pubkeys" && echo "  Removed: $INSTALL_DIR/pubkeys"
        else
            echo "  Kept: $INSTALL_DIR/keys and $INSTALL_DIR/pubkeys"
        fi

        # Remove desktop entry (dotfiles persistent file + session symlink)
        for DESKTOP_FILE in \
            "/live/persistence/TailsData_unlocked/dotfiles/.local/share/applications/calsec.desktop" \
            "$HOME/.local/share/applications/calsec.desktop"; do
            [ -e "$DESKTOP_FILE" ] && rm -f "$DESKTOP_FILE" && echo "  Removed: $DESKTOP_FILE"
        done

        # Remove from GNOME dash
        current=$(gsettings get org.gnome.shell favorite-apps 2>/dev/null || echo "[]")
        if [[ "$current" == *"calsec.desktop"* ]]; then
            new=$(echo "$current" | sed "s/, 'calsec.desktop'//;s/'calsec.desktop', //;s/'calsec.desktop'//")
            gsettings set org.gnome.shell favorite-apps "$new" 2>/dev/null && \
                echo "  Removed from dash." || \
                echo "  Could not remove from dash (GNOME not running?)."
        fi

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
        ;;
    0)
        echo "Cancelled."
        exit 0
        ;;
    *)
        echo "Invalid choice."
        exit 1
        ;;
esac

# --- Install ---
echo ""
echo "[*] Installing to $INSTALL_DIR ..."

# --- Create structure ---
mkdir -p "$INSTALL_DIR/keys"
mkdir -p "$INSTALL_DIR/pubkeys"

# --- Copy files ---
cp "$CURRENT_DIR/calsec-linux" "$INSTALL_DIR/calsec"
cp "$CURRENT_DIR/icon.png" "$INSTALL_DIR/"
cp "$CURRENT_DIR/$SCRIPT_NAME" "$INSTALL_DIR/"
chmod +x "$INSTALL_DIR/calsec"
chmod +x "$INSTALL_DIR/$SCRIPT_NAME"

# --- Desktop entry ---
echo "[*] Creating desktop entry..."
DESKTOP_PERSIST_DIR="/live/persistence/TailsData_unlocked/dotfiles/.local/share/applications"
DESKTOP_DIR="$HOME/.local/share/applications"
mkdir -p "$DESKTOP_PERSIST_DIR"
mkdir -p "$DESKTOP_DIR"

cat > "$DESKTOP_PERSIST_DIR/calsec.desktop" <<EOF
[Desktop Entry]
Name=CalSec
Comment=Zero trust calendar tool
Exec=torsocks $INSTALL_DIR/calsec
Icon=$INSTALL_DIR/icon.png
Type=Application
Categories=Utility;
Terminal=false
StartupNotify=true
StartupWMClass=calsec
EOF

chmod +x "$DESKTOP_PERSIST_DIR/calsec.desktop"

# Symlink into current session so the entry is available immediately without reboot
ln -sf "$DESKTOP_PERSIST_DIR/calsec.desktop" "$DESKTOP_DIR/calsec.desktop"

# --- Add to GNOME dash ---
current=$(gsettings get org.gnome.shell favorite-apps 2>/dev/null || echo "[]")
if [[ "$current" != *"calsec.desktop"* ]]; then
    new=$(echo "$current" | sed "s/]/, 'calsec.desktop']/")
    gsettings set org.gnome.shell favorite-apps "$new" 2>/dev/null && \
        echo "[*] CalSec to dash added." || \
        echo "[!] Could not add to dash (GNOME not running?)."
fi

# --- Key generation (optional) ---
generate_key() {
    local KEY_DIR="$INSTALL_DIR/keys"
    local PUB_DIR="$INSTALL_DIR/pubkeys"

    echo ""
    echo "=== Key Generation ==="

    read -p "Enter your identifier: " identifier

    local identifier_clean
    identifier_clean=$(printf "%s" "$identifier" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')

    if [[ -z "$identifier_clean" ]]; then
        echo "Identifier required."
        exit 1
    fi

    local user_hash
    user_hash=$(printf "%s" "$identifier_clean" | sha256sum | cut -d ' ' -f1 | cut -c1-32)

    local priv_key="$KEY_DIR/$user_hash.pem"
    local pub_key="$PUB_DIR/$user_hash.pub.pem"

    if [ -f "$priv_key" ]; then
        echo "Key already exists for this identifier: $priv_key"
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
    echo "And tell them your identifier: $identifier_clean"
}

echo ""
echo "If this device is for the admin's first setup, do NOT generate a keypair now."
echo "Choose 'No' and let CalSec create the admin key on first launch."
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
echo "1. Send your public key + identifier to the admin (after key generation)"
echo "2. Start CalSec from the Applications menu"
