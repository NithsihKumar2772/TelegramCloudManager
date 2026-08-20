from __future__ import annotations

import json
import os
import shutil
import tempfile
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from db import Database
from telegram_backend import TelegramBackend
from transfer import (
    DEFAULT_PART_SIZE,
    mime_for,
    reassemble,
    sha256_file,
    split_file,
)

APP_DIR = (
    Path(os.environ.get("LOCALAPPDATA", str(Path.home())))
    / "TelegramCloudManager"
)
APP_DIR.mkdir(parents=True, exist_ok=True)

CONFIG_PATH = APP_DIR / "config.json"
SESSION_PATH = APP_DIR / "telegram"
DB_PATH = APP_DIR / "TelegramCloud.db"
CACHE_DIR = APP_DIR / "cache"


def human_size(n):
    value = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{n} B"


class App(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title("Telegram Cloud Manager")
        self.geometry("1180x720")
        self.minsize(900, 600)

        self.db = Database(DB_PATH)
        self.backend = TelegramBackend(SESSION_PATH)

        self.current_folder = self.db.root_id()
        self.folder_nodes = {}

        self.api_id = ""
        self.api_hash = ""
        self.phone = ""
        self.part_size = DEFAULT_PART_SIZE

        self.load_config()
        self.build_ui()
        self.load_tree()

        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def load_config(self):
        if not CONFIG_PATH.exists():
            return

        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            self.api_id = data.get("api_id", "")
            self.api_hash = data.get("api_hash", "")
            self.phone = data.get("phone", "")
            self.part_size = int(
                data.get("part_size", DEFAULT_PART_SIZE)
            )
        except Exception:
            pass

    def save_config(self):
        CONFIG_PATH.write_text(
            json.dumps(
                {
                    "api_id": self.api_id,
                    "api_hash": self.api_hash,
                    "phone": self.phone,
                    "part_size": self.part_size,
                },
                indent=2,
            ),
            encoding="utf-8",
        )

    def build_ui(self):
        top = ttk.Frame(self, padding=8)
        top.pack(fill="x")

        ttk.Button(
            top, text="Telegram Login", command=self.login_dialog
        ).pack(side="left")

        ttk.Button(
            top, text="New Folder", command=self.new_folder
        ).pack(side="left", padx=5)

        ttk.Button(
            top, text="Upload", command=self.upload
        ).pack(side="left", padx=5)

        ttk.Button(
            top, text="Download", command=self.download
        ).pack(side="left", padx=5)

        ttk.Button(
            top, text="Settings", command=self.settings_dialog
        ).pack(side="left", padx=5)

        self.status = tk.StringVar(value="Not connected")
        ttk.Label(top, textvariable=self.status).pack(side="right")

        panes = ttk.PanedWindow(self, orient="horizontal")
        panes.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        left = ttk.Frame(panes)
        right = ttk.Frame(panes)

        panes.add(left, weight=1)
        panes.add(right, weight=3)

        self.tree = ttk.Treeview(left, show="tree")
        self.tree.pack(side="left", fill="both", expand=True)

        tree_scroll = ttk.Scrollbar(
            left, orient="vertical", command=self.tree.yview
        )
        tree_scroll.pack(side="right", fill="y")
        self.tree.configure(yscrollcommand=tree_scroll.set)
        self.tree.bind("<<TreeviewSelect>>", self.on_folder_select)

        search = ttk.Frame(right)
        search.pack(fill="x", pady=(0, 6))

        ttk.Label(search, text="Search:").pack(side="left")

        self.search_var = tk.StringVar()
        ttk.Entry(
            search, textvariable=self.search_var
        ).pack(side="left", fill="x", expand=True, padx=5)

        ttk.Button(
            search, text="Search", command=self.refresh_files
        ).pack(side="left")

        columns = ("name", "size", "status", "sha")

        self.files_view = ttk.Treeview(
            right, columns=columns, show="headings"
        )

        self.files_view.heading("name", text="Name")
        self.files_view.heading("size", text="Size")
        self.files_view.heading("status", text="Status")
        self.files_view.heading("sha", text="SHA-256")

        self.files_view.column("name", width=380)
        self.files_view.column("size", width=120)
        self.files_view.column("status", width=100)
        self.files_view.column("sha", width=300)

        self.files_view.pack(side="left", fill="both", expand=True)

        file_scroll = ttk.Scrollbar(
            right,
            orient="vertical",
            command=self.files_view.yview,
        )
        file_scroll.pack(side="right", fill="y")

        self.files_view.configure(
            yscrollcommand=file_scroll.set
        )

        self.files_view.bind(
            "<Double-1>",
            lambda _event: self.download()
        )

    def load_tree(self):
        self.tree.delete(*self.tree.get_children())
        self.folder_nodes.clear()

        root_id = self.db.root_id()

        root_node = self.tree.insert(
            "",
            "end",
            text="☁ My Drive",
            open=True,
            values=(root_id,),
        )

        self.folder_nodes[root_id] = root_node
        self.add_children(root_id, root_node)

        self.tree.selection_set(root_node)
        self.refresh_files()

    def add_children(self, parent_id, parent_node):
        for row in self.db.children(parent_id):
            node = self.tree.insert(
                parent_node,
                "end",
                text="📁 " + row["name"],
                values=(row["id"],),
            )
            self.folder_nodes[row["id"]] = node
            self.add_children(row["id"], node)

    def on_folder_select(self, _event=None):
        selected = self.tree.selection()
        if not selected:
            return

        values = self.tree.item(selected[0], "values")
        if values:
            self.current_folder = int(values[0])
            self.refresh_files()

    def refresh_files(self):
        self.files_view.delete(*self.files_view.get_children())

        search = self.search_var.get().strip()

        for row in self.db.files(self.current_folder, search):
            self.files_view.insert(
                "",
                "end",
                iid=str(row["id"]),
                values=(
                    row["name"],
                    human_size(row["size"]),
                    row["status"],
                    (row["sha256"] or "")[:24],
                ),
            )

    def new_folder(self):
        name = simpledialog.askstring(
            "New Folder",
            "Folder name:",
            parent=self,
        )

        if not name or not name.strip():
            return

        try:
            self.db.create_folder(
                self.current_folder,
                name.strip(),
            )
            self.load_tree()
            self.status.set("Folder created")
        except Exception as exc:
            messagebox.showerror("Folder", str(exc))

    def login_dialog(self):
        win = tk.Toplevel(self)
        win.title("Telegram Login")
        win.transient(self)
        win.grab_set()

        fields = {}

        labels = [
            ("API ID", self.api_id),
            ("API Hash", self.api_hash),
            ("Phone", self.phone),
            ("Code", ""),
            ("2FA Password", ""),
        ]

        for row, (label, value) in enumerate(labels):
            ttk.Label(win, text=label).grid(
                row=row,
                column=0,
                padx=8,
                pady=6,
                sticky="w",
            )

            entry = ttk.Entry(
                win,
                width=44,
                show="*" if label == "2FA Password" else "",
            )

            entry.insert(0, value)
            entry.grid(
                row=row,
                column=1,
                padx=8,
                pady=6,
            )

            fields[label] = entry

        def send_code():
            try:
                api_id = int(fields["API ID"].get().strip())
                api_hash = fields["API Hash"].get().strip()
                phone = fields["Phone"].get().strip()

                self.backend.configure(api_id, api_hash)
                authorized = self.backend.connect().result(timeout=30)

                if authorized:
                    self.api_id = str(api_id)
                    self.api_hash = api_hash
                    self.phone = phone
                    self.save_config()
                    self.status.set("Connected ✓")
                    messagebox.showinfo(
                        "Telegram",
                        "Already authorized.",
                        parent=win,
                    )
                    return

                self.backend.send_code(phone).result(timeout=30)

                self.status.set("Code sent")
                messagebox.showinfo(
                    "Telegram",
                    "Telegram login code sent.",
                    parent=win,
                )
            except Exception as exc:
                messagebox.showerror(
                    "Telegram Login",
                    str(exc),
                    parent=win,
                )

        def sign_in():
            try:
                api_id = int(fields["API ID"].get().strip())
                api_hash = fields["API Hash"].get().strip()
                phone = fields["Phone"].get().strip()
                code = fields["Code"].get().strip()
                password = fields["2FA Password"].get()

                self.backend.configure(api_id, api_hash)
                self.backend.connect().result(timeout=30)

                ok = self.backend.sign_in(
                    phone,
                    code,
                    password,
                ).result(timeout=60)

                if ok:
                    self.api_id = str(api_id)
                    self.api_hash = api_hash
                    self.phone = phone
                    self.save_config()

                    self.status.set("Connected ✓")

                    messagebox.showinfo(
                        "Telegram",
                        "Login successful.",
                        parent=win,
                    )

                    win.destroy()

            except Exception as exc:
                messagebox.showerror(
                    "Telegram Login",
                    str(exc),
                    parent=win,
                )

        ttk.Button(
            win,
            text="Send Code",
            command=send_code,
        ).grid(row=5, column=0, padx=8, pady=10)

        ttk.Button(
            win,
            text="Sign In",
            command=sign_in,
        ).grid(row=5, column=1, padx=8, pady=10, sticky="e")

    def settings_dialog(self):
        value = simpledialog.askinteger(
            "Part Size",
            "Part size in GB (recommended 1 or 2):",
            initialvalue=max(
                1,
                round(self.part_size / 1_000_000_000),
            ),
            minvalue=1,
            maxvalue=4,
        )

        if value:
            self.part_size = value * 1_000_000_000
            self.save_config()

    def ensure_connected(self):
        if not self.api_id or not self.api_hash:
            self.login_dialog()
            return False

        try:
            self.backend.configure(
                int(self.api_id),
                self.api_hash,
            )

            authorized = self.backend.connect().result(
                timeout=30
            )

            if not authorized:
                self.login_dialog()
                return False

            self.status.set("Connected ✓")
            return True

        except Exception as exc:
            messagebox.showerror(
                "Telegram",
                str(exc),
            )
            return False

    def upload(self):
        if not self.ensure_connected():
            return

        paths = filedialog.askopenfilenames(
            title="Select files"
        )

        for selected in paths:
            threading.Thread(
                target=self.upload_worker,
                args=(Path(selected),),
                daemon=True,
            ).start()

    def upload_worker(self, path: Path):
        file_id = None

        try:
            self.set_status_threadsafe(
                f"Preparing {path.name}..."
            )

            original_size = path.stat().st_size
            original_sha = sha256_file(path)

            file_id = self.db.insert_file(
                self.current_folder,
                path.name,
                original_size,
                original_sha,
                mime_for(path),
                "uploading",
            )

            temp = Path(
                tempfile.mkdtemp(
                    prefix="tcm_upload_",
                    dir=CACHE_DIR,
                )
            )

            try:
                parts = split_file(
                    path,
                    temp,
                    self.part_size,
                )

                for index, (
                    part_path,
                    part_size,
                    part_sha,
                ) in enumerate(parts, start=1):

                    self.set_status_threadsafe(
                        f"Uploading {path.name} — "
                        f"part {index}/{len(parts)}"
                    )

                    caption = (
                        f"[TCM] {path.name} | "
                        f"file={file_id} | "
                        f"part={index}/{len(parts)} | "
                        f"sha256={part_sha}"
                    )

                    message = self.backend.upload_part(
                        part_path,
                        caption,
                    ).result(
                        timeout=24 * 60 * 60
                    )

                    chat_id = int(
                        getattr(message, "chat_id", 0) or 0
                    )

                    self.db.add_part(
                        file_id,
                        index,
                        part_size,
                        chat_id,
                        int(message.id),
                        part_sha,
                    )

                    if part_path != path:
                        part_path.unlink(
                            missing_ok=True
                        )

                self.db.set_file_status(
                    file_id,
                    "complete",
                )

                self.after(0, self.refresh_files)
                self.set_status_threadsafe(
                    f"Uploaded: {path.name}"
                )

            finally:
                shutil.rmtree(
                    temp,
                    ignore_errors=True,
                )

        except Exception as exc:
            if file_id is not None:
                try:
                    self.db.set_file_status(
                        file_id,
                        "failed",
                    )
                except Exception:
                    pass

            self.after(
                0,
                lambda error=str(exc): messagebox.showerror(
                    "Upload failed",
                    error,
                ),
            )

            self.set_status_threadsafe(
                "Upload failed"
            )

    def download(self):
        selected = self.files_view.selection()

        if not selected:
            messagebox.showinfo(
                "Download",
                "Select a file first.",
            )
            return

        row = self.db.get_file(
            int(selected[0])
        )

        if not row:
            return

        destination = filedialog.asksaveasfilename(
            initialfile=row["name"],
            title="Save file",
        )

        if not destination:
            return

        if not self.ensure_connected():
            return

        threading.Thread(
            target=self.download_worker,
            args=(row["id"], Path(destination)),
            daemon=True,
        ).start()

    def download_worker(self, file_id, destination: Path):
        try:
            row = self.db.get_file(file_id)
            parts = self.db.parts(file_id)

            if not parts:
                raise RuntimeError(
                    "No Telegram parts are stored for this file."
                )

            temp = Path(
                tempfile.mkdtemp(
                    prefix="tcm_download_",
                    dir=CACHE_DIR,
                )
            )

            try:
                downloaded_parts = []

                for part in parts:
                    part_path = (
                        temp / f"part_{part['part_no']:04d}"
                    )

                    self.set_status_threadsafe(
                        f"Downloading {row['name']} — "
                        f"part {part['part_no']}/{len(parts)}"
                    )

                    self.backend.download_message(
                        part["telegram_chat_id"],
                        part["telegram_message_id"],
                        part_path,
                    ).result(
                        timeout=24 * 60 * 60
                    )

                    if sha256_file(part_path) != part["sha256"]:
                        raise RuntimeError(
                            f"Checksum mismatch on part "
                            f"{part['part_no']}."
                        )

                    downloaded_parts.append(
                        part_path
                    )

                reassemble(
                    downloaded_parts,
                    destination,
                )

                if sha256_file(destination) != row["sha256"]:
                    destination.unlink(
                        missing_ok=True
                    )
                    raise RuntimeError(
                        "Final SHA-256 mismatch. "
                        "The downloaded file was removed."
                    )

                self.set_status_threadsafe(
                    f"Downloaded: {destination.name}"
                )

                self.after(
                    0,
                    lambda: messagebox.showinfo(
                        "Download",
                        f"Completed:\n{destination}",
                    ),
                )

            finally:
                shutil.rmtree(
                    temp,
                    ignore_errors=True,
                )

        except Exception as exc:
            self.after(
                0,
                lambda error=str(exc): messagebox.showerror(
                    "Download failed",
                    error,
                ),
            )
            self.set_status_threadsafe(
                "Download failed"
            )

    def set_status_threadsafe(self, text):
        self.after(
            0,
            lambda value=text: self.status.set(value),
        )

    def on_close(self):
        try:
            self.backend.disconnect()
        except Exception:
            pass

        try:
            self.db.close()
        except Exception:
            pass

        self.destroy()


if __name__ == "__main__":
    App().mainloop()
