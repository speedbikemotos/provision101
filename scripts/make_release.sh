#!/bin/bash
set -euo pipefail

./scripts/build.sh

echo "Preparing release folder..."
rm -rf release/Linux
mkdir -p release/Linux/data release/Linux/logs

cp dist/provisioner release/Linux/provisioner
cp README.txt release/Linux/README.txt
chmod +x release/Linux/provisioner

echo "Creating tar.gz archive..."
mkdir -p release
tar -czf release/provisioner-linux.tar.gz -C release Linux

echo "Release ready: release/Linux"
echo "Archive ready: release/provisioner-linux.tar.gz"

