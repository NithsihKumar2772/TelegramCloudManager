from __future__ import annotations
import sqlite3
from pathlib import Path

class Database:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init()

    def _init(self):
        self.conn.executescript("""
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS folders(
            id INTEGER PRIMARY KEY,
            parent_id INTEGER,
            name TEXT NOT NULL,
            notes TEXT DEFAULT '',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(parent_id,name),
            FOREIGN KEY(parent_id) REFERENCES folders(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS files(
            id INTEGER PRIMARY KEY,
            folder_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            size INTEGER NOT NULL,
            sha256 TEXT,
            mime TEXT,
            status TEXT DEFAULT 'complete',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(folder_id) REFERENCES folders(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS file_parts(
            id INTEGER PRIMARY KEY,
            file_id INTEGER NOT NULL,
            part_no INTEGER NOT NULL,
            size INTEGER NOT NULL,
            telegram_chat_id INTEGER NOT NULL,
            telegram_message_id INTEGER NOT NULL,
            sha256 TEXT,
            FOREIGN KEY(file_id) REFERENCES files(id) ON DELETE CASCADE,
            UNIQUE(file_id,part_no)
        );
        """)

        row = self.conn.execute(
            "SELECT id FROM folders WHERE parent_id IS NULL AND name='My Drive'"
        ).fetchone()
        if not row:
            self.conn.execute(
                "INSERT INTO folders(parent_id,name) VALUES(NULL,'My Drive')"
            )
        self.conn.commit()

    def root_id(self):
        return self.conn.execute(
            "SELECT id FROM folders WHERE parent_id IS NULL AND name='My Drive'"
        ).fetchone()["id"]

    def children(self, parent_id):
        return self.conn.execute(
            "SELECT * FROM folders WHERE parent_id=? ORDER BY name COLLATE NOCASE",
            (parent_id,)
        ).fetchall()

    def create_folder(self, parent_id, name):
        cur = self.conn.execute(
            "INSERT INTO folders(parent_id,name) VALUES(?,?)",
            (parent_id, name.strip())
        )
        self.conn.commit()
        return cur.lastrowid

    def files(self, folder_id, search=""):
        if search:
            return self.conn.execute(
                "SELECT * FROM files WHERE folder_id=? AND name LIKE ? "
                "ORDER BY name COLLATE NOCASE",
                (folder_id, f"%{search}%")
            ).fetchall()

        return self.conn.execute(
            "SELECT * FROM files WHERE folder_id=? ORDER BY name COLLATE NOCASE",
            (folder_id,)
        ).fetchall()

    def insert_file(self, folder_id, name, size, sha256, mime, status="uploading"):
        cur = self.conn.execute(
            "INSERT INTO files(folder_id,name,size,sha256,mime,status) "
            "VALUES(?,?,?,?,?,?)",
            (folder_id, name, size, sha256, mime, status)
        )
        self.conn.commit()
        return cur.lastrowid

    def set_file_status(self, file_id, status):
        self.conn.execute(
            "UPDATE files SET status=? WHERE id=?",
            (status, file_id)
        )
        self.conn.commit()

    def add_part(self, file_id, part_no, size, chat_id, message_id, sha256):
        self.conn.execute(
            "INSERT INTO file_parts("
            "file_id,part_no,size,telegram_chat_id,telegram_message_id,sha256"
            ") VALUES(?,?,?,?,?,?)",
            (file_id, part_no, size, chat_id, message_id, sha256)
        )
        self.conn.commit()

    def parts(self, file_id):
        return self.conn.execute(
            "SELECT * FROM file_parts WHERE file_id=? ORDER BY part_no",
            (file_id,)
        ).fetchall()

    def get_file(self, file_id):
        return self.conn.execute(
            "SELECT * FROM files WHERE id=?",
            (file_id,)
        ).fetchone()

    def close(self):
        self.conn.close()
