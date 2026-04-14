@echo off
setlocal

if not exist logs mkdir logs
echo [%date% %time%] make_release.bat started>>logs\app.log

call scripts\build.bat
if errorlevel 1 (
  echo Build failed.
  echo [%date% %time%] Build failed in make_release.bat>>logs\app.log
  exit /b 1
)

echo Preparing release folder...
if exist release\Windows rmdir /s /q release\Windows
mkdir release\Windows
mkdir release\Windows\data
mkdir release\Windows\logs

copy /Y dist\Provisioner.exe release\Windows\Provisioner.exe >nul
if errorlevel 1 (
  echo [%date% %time%] ERROR: dist\Provisioner.exe missing or copy failed.>>logs\app.log
  exit /b 1
)
copy /Y README.txt release\Windows\README.txt >nul

echo Creating ZIP archive...
powershell -NoProfile -Command "if (Test-Path 'release\Provisioner-Windows.zip') { Remove-Item 'release\Provisioner-Windows.zip' -Force }; Compress-Archive -Path 'release\Windows\*' -DestinationPath 'release\Provisioner-Windows.zip' -Force"

echo Release ready: release\Windows
echo Zip ready: release\Provisioner-Windows.zip
echo [%date% %time%] Release build success: release\Windows and ZIP created.>>logs\app.log
endlocal

