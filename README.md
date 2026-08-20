# TelegramCloudManager – Project 01 MVP

A separate Windows desktop app that connects **directly to Telegram using MTProto/Telethon**.

It does NOT modify Telegram Drive and does NOT put Air Cluster/WebDAV in the transfer path.

## Included in this MVP

- Telegram login with `api_id`, `api_hash`, phone, code and optional 2FA password
- Google-Drive-style nested folder tree
- Local SQLite folder/file/part database
- Direct Telegram uploads to Saved Messages
- Automatic splitting above the configured part size
- Parts hidden from the UI and represented as one logical file
- Download + reassembly
- SHA-256 verification
- Basic search
- Windows EXE build with PyInstaller
- GitHub Actions workflow that builds the Windows EXE online

## Important limitations of this first build

This is the foundation, not the final production version. It does NOT yet include:
- Windows Explorer `E:` virtual filesystem
- parallel multipart transfers
- resumable transfers after application restart
- thumbnails/media preview
- ZIP/RAR/7z browser
- advanced search filters
- installer wizard/updater
- end-to-end encryption

Those should be added after the direct Telegram connection and logical-file engine are proven.

## Telegram API credentials

Create a Telegram application at:

https://my.telegram.org

You need your own `api_id` and `api_hash`.

Do NOT put these credentials in GitHub source code. Enter them in the app at runtime.

## Run locally

Python 3.10+ recommended:

```text
pip install -r requirements.txt
python src/main.py
```

Optional speed package:

```text
pip install cryptg
```

## Build Windows EXE locally

Run:

```text
build_windows.bat
```

The EXE will be:

```text
dist\TelegramCloudManager.exe
```

## Build online with GitHub

1. Create a GitHub repository.
2. Upload this project.
3. Open **Actions**.
4. Select **Build Windows EXE**.
5. Run the workflow.
6. Download the `TelegramCloudManager-windows` artifact.
7. Extract it and run `TelegramCloudManager.exe`.

The workflow does not contain your Telegram credentials.

## Data

App data is stored under:

`%LOCALAPPDATA%\TelegramCloudManager\`

The Telethon session file is sensitive. Never share it.

## Architecture

```text
TelegramCloudManager
  |
  +-- Tkinter desktop UI
  +-- SQLite logical folder/file database
  +-- Telethon direct MTProto client
  +-- Split/reassemble engine
  |
  +-- Telegram Saved Messages
```

The next major stage is a Windows virtual filesystem (`Telegram Cloud (E:)`) over this logical database/transfer engine.
