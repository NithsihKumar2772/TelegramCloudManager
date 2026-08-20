@echo off
setlocal
py -3 -m pip install --upgrade pip
py -3 -m pip install -r requirements.txt
py -3 -m pip install --upgrade pyinstaller
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
pyinstaller --noconfirm --clean --onefile --windowed --name TelegramCloudManager src\main.py
echo.
echo BUILD COMPLETE:
echo dist\TelegramCloudManager.exe
pause
