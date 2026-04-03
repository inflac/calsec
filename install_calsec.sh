#!/bin/bash

# This script installs the calsec application on a Tails system.
# It should be run as the 'amnesia' user and will copy the necessary files to the persistence directory.

persistence_dir="/live/persistence/TailsData_unlocked"
current_dir="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"


# Make sure we are running as 'amnesia'
if test "$(whoami)" != "amnesia"
then
    echo "You must run this program as 'amnesia' user."
    exit 1
fi

# Check if the persistence directory exists
if [ ! -d "$persistence_dir" ]; then
    echo "Persistence directory not found. Please make sure you have set up persistence and unlocked it."
    exit 1
fi

echo "Installing calsec into '$persistence_dir/calsec'..."

# Create the calsec directory in the persistence directory
mkdir -p "$persistence_dir/calsec"
# Copy the necessary files to the persistence directory
cp "$current_dir/calsec" "$persistence_dir/calsec/"
cp "$current_dir/icon.png" "$persistence_dir/calsec/"
# Set the correct permissions for the calsec executable
chmod +x "$persistence_dir/calsec/calsec"

echo "Creating desktop entry for calsec..."

mkdir -p "$HOME/.local/share/applications"
cp "$current_dir/calsec.desktop" "$HOME/.local/share/applications/"
chmod +x ~/.local/share/applications/calsec.desktop

echo "Installation complete. You can find calsec in the Applications menu under 'Calsec' or run it from the terminal with 'calsec'."
