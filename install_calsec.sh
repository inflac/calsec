#!/bin/bash

# Calsec Installer for Tails
# Installs app + sets up directories + optional key generation

set -e

PERSISTENCE_DIR="/live/persistence/TailsData_unlocked"
INSTALL_DIR="$PERSISTENCE_DIR/calsec"
CURRENT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"

echo "=== Calsec Installer ==="

# --- User check ---
if [ "$(whoami)" != "amnesia" ]; then
    echo "❌ Please run as 'amnesia' user."
    exit 1
fi

# --- Persistence check ---
if [ ! -d "$PERSISTENCE_DIR" ]; then
    echo "❌ Persistence not found or not unlocked."
    exit 1
fi

echo "[*] Installing to $INSTALL_DIR ..."

# --- Create structure ---
mkdir -p "$INSTALL_DIR"
mkdir -p "$INSTALL_DIR/keys"
mkdir -p "$INSTALL_DIR/pubkeys"

# --- Copy files ---
cp "$CURRENT_DIR/calsec" "$INSTALL_DIR/"
cp "$CURRENT_DIR/icon.png" "$INSTALL_DIR/"

chmod +x "$INSTALL_DIR/calsec"

# --- Desktop entry ---
echo "[*] Creating desktop entry..."

DESKTOP_FILE="$HOME/Persistent/.local/share/applications/calsec.desktop"
mkdir -p "$HOME/Persistent/.local/share/applications"

cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Name=Calsec
Exec=$INSTALL_DIR/calsec
Icon=$INSTALL_DIR/icon.png
Type=Application
Categories=Utility;
EOF

chmod +x "$DESKTOP_FILE"

# --- Key generator script ---
echo "[*] Installing key generator..."

cat > "$INSTALL_DIR/generate_key.sh" <<'EOF'
#!/bin/bash

set -e

BASE_DIR="/live/persistence/TailsData_unlocked/calsec"
KEY_DIR="$BASE_DIR/keys"
PUB_DIR="$BASE_DIR/pubkeys"

mkdir -p "$KEY_DIR"
mkdir -p "$PUB_DIR"

echo "=== Calsec Key Generator ==="

read -p "Enter your email: " email

if [[ -z "$email" ]]; then
    echo "❌ Email required."
    exit 1
fi

# normalize email
email_clean=$(echo "$email" | tr '[:upper:]' '[:lower:]' | tr -d ' ')

# hash = filename
user_hash=$(echo -n "$email_clean" | sha256sum | cut -d ' ' -f1)

priv_key="$KEY_DIR/$user_hash.pem"
pub_key="$PUB_DIR/$user_hash.pub.pem"

if [ -f "$priv_key" ]; then
    echo "⚠ Key already exists for this email!"
    echo "$priv_key"
    exit 1
fi

echo ""
echo "🔐 Optional: Protect your private key with a password."
echo "If you set one, you will need to enter it EVERY TIME you start Calsec."
echo ""

read -p "Do you want to set a password? (y/n): " use_pw

if [[ "$use_pw" == "y" || "$use_pw" == "Y" ]]; then
    echo ""
    read -s -p "Enter password: " pw1
    echo ""
    read -s -p "Confirm password: " pw2
    echo ""

    if [[ "$pw1" != "$pw2" ]]; then
        echo "❌ Passwords do not match."
        exit 1
    fi

    if [[ -z "$pw1" ]]; then
        echo "❌ Empty password not allowed."
        exit 1
    fi

    echo "[*] Generating password-protected keypair..."

    openssl ecparam -name prime256v1 -genkey -noout \
        | openssl ec -aes256 -out "$priv_key" -passout pass:"$pw1"

else
    echo "[*] Generating keypair (no password)..."

    openssl ecparam -name prime256v1 -genkey -noout -out "$priv_key"
fi

# public key always same
openssl ec -in "$priv_key" -pubout -out "$pub_key" 2>/dev/null || \
openssl ec -in "$priv_key" -pubout -out "$pub_key"

chmod 600 "$priv_key"

echo ""
echo "✅ Keypair created!"
echo ""
echo "Private key stored at:"
echo "  $priv_key"
echo ""
echo "➡ Send this PUBLIC KEY to the admin:"
echo "  $pub_key"
echo ""
echo "➡ And tell them your email:"
echo "  $email_clean"
EOF

chmod +x "$INSTALL_DIR/generate_key.sh"

# --- Ask user to generate key ---
echo ""
read -p "Generate keypair now? [Y/n]: " choice
choice=${choice:-Y}

case "$choice" in
    y|Y )
        echo ""
        echo "[*] Starting key generation..."
        "$INSTALL_DIR/generate_key.sh"
        ;;
    * )
        echo ""
        echo "You can generate a key later with:"
        echo "  $INSTALL_DIR/generate_key.sh"
        ;;
esac

# --- Done ---
echo ""
echo "✅ Installation complete!"
echo ""
echo "Next steps:"
echo "1. If not already done, generate your key:"
echo "   $INSTALL_DIR/generate_key.sh"
echo ""
echo "2. Send your PUBLIC KEY + email to the admin"
echo ""
echo "3. Start Calsec from the Applications menu"