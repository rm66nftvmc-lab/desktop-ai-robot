"""Read-only database checks and cached, content-free maintenance metrics."""

from datetime import datetime, timezone
from pathlib import Path
import shutil
import sqlite3
import threading
import time

BRIDGE_VERSION = "0.3.0"
SCHEMA_VERSION = 1
LOG_MAX_BYTES = 2 * 1024 * 1024
LOG_BACKUPS = 3


def check_database(path: Path, *, budget_seconds=3) -> dict:
    result = {"state": "new", "schema_version": SCHEMA_VERSION,
              "checked_at": datetime.now(timezone.utc).isoformat()}
    if not path.exists():
        return result
    deadline = time.monotonic() + budget_seconds
    try:
        with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True,
                             timeout=min(1, budget_seconds)) as db:
            db.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version > SCHEMA_VERSION:
                raise RuntimeError("数据库由更新版本的 Bridge 创建，请使用匹配的新版本；未修改原数据库")
            rows = db.execute("PRAGMA quick_check(1)").fetchall()
            if rows != [("ok",)]:
                raise RuntimeError("数据库完整性检查失败，请保留原文件并检查磁盘；未自动重建数据库")
    except sqlite3.DatabaseError as exc:
        code = getattr(exc, "sqlite_errorcode", 0) & 0xFF
        if code in {sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED, sqlite3.SQLITE_INTERRUPT}:
            result["state"] = "deferred"
            return result
        raise RuntimeError("数据库无法通过只读检查，请保留原文件并检查磁盘；未自动重建数据库") from exc
    result["state"] = "ok"
    return result


class MaintenanceStatus:
    def __init__(self, data_dir: Path, database_check: dict):
        self.data_dir = data_dir
        self.database_check = database_check
        self.started = time.monotonic()
        self._lock = threading.Lock()
        self._sampled = -float("inf")
        self._metrics = {}

    def snapshot(self) -> dict:
        with self._lock:
            now = time.monotonic()
            if now - self._sampled >= 60:
                try:
                    free = shutil.disk_usage(self.data_dir).free
                    database = self.data_dir / "messages.sqlite3"
                    size = database.stat().st_size if database.is_file() else 0
                    log_size = sum(p.stat().st_size for p in self.data_dir.glob("bridge.*.log*") if p.is_file())
                    self._metrics = {"disk_free_bytes": free, "low_disk_space": free < 1024**3,
                                     "database_bytes": size, "log_bytes": log_size}
                except OSError:
                    self._metrics = {"disk_free_bytes": None, "low_disk_space": None,
                                     "database_bytes": None, "log_bytes": None}
                self._sampled = now
            return {"version": BRIDGE_VERSION, "uptime_seconds": int(now - self.started),
                    "database": dict(self.database_check), **self._metrics,
                    "log_max_bytes": LOG_MAX_BYTES, "log_backups": LOG_BACKUPS}
