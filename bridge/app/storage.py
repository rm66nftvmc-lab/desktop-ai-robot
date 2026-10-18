"""Local conversation inbox, separated by source."""

import sqlite3
from pathlib import Path
from .maintenance import SCHEMA_VERSION


def initialize(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as db:
        if db.execute("PRAGMA user_version").fetchone()[0] > SCHEMA_VERSION:
            raise RuntimeError("数据库版本高于当前 Bridge，已停止写入")
        db.execute(
            """CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,
                text TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user',
                input_method TEXT NOT NULL DEFAULT 'text',
                delivery TEXT NOT NULL DEFAULT 'not_configured',
                reply_to INTEGER,
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
            )"""
        )
        db.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        columns = {row[1] for row in db.execute("PRAGMA table_info(messages)")}
        for name, declaration in (
            ("role", "TEXT NOT NULL DEFAULT 'user'"),
            ("input_method", "TEXT NOT NULL DEFAULT 'text'"),
            ("delivery", "TEXT NOT NULL DEFAULT 'not_configured'"),
            ("reply_to", "INTEGER"),
            ("conversation_id", "TEXT"),
        ):
            if name not in columns:
                db.execute(f"ALTER TABLE messages ADD COLUMN {name} {declaration}")
        # A Bridge restart cannot safely resume an in-flight Hermes turn.
        db.execute("UPDATE messages SET delivery = 'interrupted' "
                   "WHERE source IN ('hermes', 'deepseek_harness') AND delivery IN ('queued', 'running')")
        db.execute("UPDATE messages SET delivery='stop_failed' WHERE delivery='stopping'")
        db.execute("CREATE TABLE IF NOT EXISTS conversations (id TEXT PRIMARY KEY, source TEXT NOT NULL, "
                   "native_id TEXT, title TEXT NOT NULL, created_at REAL NOT NULL)")
        db.execute("CREATE TABLE IF NOT EXISTS deleted_sessions (source TEXT NOT NULL, native_id TEXT NOT NULL, "
                   "PRIMARY KEY (source, native_id))")
        db.execute(f"PRAGMA user_version={SCHEMA_VERSION}")


def add_message(path: Path, source: str, text: str, *, role: str = "user",
                delivery: str = "not_configured", reply_to: int | None = None,
                input_method: str = "text", conversation_id: str | None = None) -> dict:
    with sqlite3.connect(path) as db:
        cursor = db.execute(
            "INSERT INTO messages (source, text, role, delivery, reply_to, input_method, conversation_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (source, text, role, delivery, reply_to, input_method, conversation_id),
        )
        row = db.execute(
            "SELECT id, source, text, role, delivery, reply_to, created_at, input_method "
            "FROM messages WHERE id = ?",
            (cursor.lastrowid,),
        ).fetchone()
    return dict(zip(("id", "source", "text", "role", "delivery", "reply_to", "created_at", "input_method"), row))


def set_delivery(path: Path, message_id: int, delivery: str) -> None:
    with sqlite3.connect(path) as db:
        db.execute("UPDATE messages SET delivery = ? WHERE id = ?", (delivery, message_id))


def get_setting(path: Path, key: str) -> str | None:
    with sqlite3.connect(path) as db:
        row = db.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row[0] if row else None


def deleted_session_ids(path: Path, source: str) -> set[str]:
    with sqlite3.connect(path) as db:
        return {row[0] for row in db.execute(
            'SELECT native_id FROM deleted_sessions WHERE source=?', (source,))}


def set_setting(path: Path, key: str, value: str) -> None:
    with sqlite3.connect(path) as db:
        db.execute("INSERT INTO settings (key, value) VALUES (?, ?) "
                   "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, value))


def list_messages(path: Path, source: str, limit: int = 50) -> list[dict]:
    with sqlite3.connect(path) as db:
        rows = db.execute(
            "SELECT id, source, text, role, delivery, reply_to, created_at, input_method FROM messages "
            "WHERE source = ? ORDER BY id DESC LIMIT ?",
            (source, limit),
        ).fetchall()
    keys = ("id", "source", "text", "role", "delivery", "reply_to", "created_at", "input_method")
    return [dict(zip(keys, row)) for row in reversed(rows)]
