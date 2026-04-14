@echo off
echo Cleaning previous builds...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo Installing dependencies...
pip install -r requirements.txt
pip install pyinstaller

echo Building executable...
pyinstaller --onefile --windowed --clean --noconfirm src/main.py --name Provisioner

echo Done.
