#!/bin/bash
set -euo pipefail

echo "Cleaning previous builds..."
rm -rf build dist

echo "Installing dependencies..."
pip3 install -r requirements.txt
pip3 install pyinstaller

echo "Building executable..."
pyinstaller --onefile --windowed --clean --noconfirm src/main.py --name provisioner

echo "Done."
