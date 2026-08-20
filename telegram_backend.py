from __future__ import annotations
import asyncio
import threading
from concurrent.futures import Future
from pathlib import Path

from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError

class TelegramBackend:
    def __init__(self, session_path: Path):
        self.session_path = str(session_path)
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        self.client = None
        self.api_id = None
        self.api_hash = None

    def _run(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def _submit(self, coroutine) -> Future:
        return asyncio.run_coroutine_threadsafe(coroutine, self.loop)

    def configure(self, api_id: int, api_hash: str):
        self.api_id = int(api_id)
        self.api_hash = api_hash.strip()

    def connect(self):
        return self._submit(self._connect())

    async def _connect(self):
        if self.client is None:
            self.client = TelegramClient(
                self.session_path,
                self.api_id,
                self.api_hash
            )
        if not self.client.is_connected():
            await self.client.connect()
        return await self.client.is_user_authorized()

    def send_code(self, phone: str):
        return self._submit(self.client.send_code_request(phone))

    def sign_in(self, phone: str, code: str, password: str = ""):
        return self._submit(self._sign_in(phone, code, password))

    async def _sign_in(self, phone, code, password):
        try:
            await self.client.sign_in(phone=phone, code=code)
        except SessionPasswordNeededError:
            if not password:
                raise RuntimeError(
                    "Telegram 2-step verification password is required."
                )
            await self.client.sign_in(password=password)
        return await self.client.is_user_authorized()

    def upload_part(self, path: Path, caption: str):
        return self._submit(
            self.client.send_file(
                "me",
                str(path),
                caption=caption,
                force_document=True
            )
        )

    def download_message(self, chat_id: int, message_id: int, output: Path):
        return self._submit(self._download(chat_id, message_id, output))

    async def _download(self, chat_id, message_id, output):
        msg = await self.client.get_messages(chat_id, ids=message_id)
        if not msg:
            raise RuntimeError(f"Telegram message not found: {message_id}")
        return await self.client.download_media(msg, file=str(output))

    def disconnect(self):
        try:
            if self.client:
                self._submit(self.client.disconnect()).result(timeout=15)
        finally:
            self.loop.call_soon_threadsafe(self.loop.stop)
