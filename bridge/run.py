"""Loopback-only production launcher with bounded Bridge logging."""

import argparse
from pathlib import Path

from .app.maintenance import LOG_BACKUPS, LOG_MAX_BYTES
from .app.security import resolve_data_dir, record_or_verify_data_dir, anchor_path


def logging_config(data_dir: Path, *, max_bytes=LOG_MAX_BYTES, backups=LOG_BACKUPS):
    return {
        "version": 1, "disable_existing_loggers": False,
        "formatters": {"standard": {"format": "%(asctime)s %(levelname)s %(name)s %(message)s"}},
        "handlers": {"runtime": {
            "class": "logging.handlers.RotatingFileHandler", "formatter": "standard",
            "filename": str(data_dir / "bridge.runtime.log"), "encoding": "utf-8",
            "maxBytes": max_bytes, "backupCount": backups,
        }},
        "root": {"handlers": ["runtime"], "level": "INFO"},
        "loggers": {name: {"handlers": ["runtime"], "level": "INFO", "propagate": False}
                    for name in ("uvicorn", "uvicorn.error", "uvicorn.access")},
    }


def rotate_startup_logs(data_dir: Path):
    # Only these two owned files are rotated, after the old Bridge has stopped.
    for name in ("bridge.stdout.log", "bridge.stderr.log"):
        path = data_dir / name
        if not path.is_file() or not path.stat().st_size:
            continue
        for index in range(LOG_BACKUPS, 0, -1):
            old = path if index == 1 else path.with_name(f"{name}.{index - 1}")
            new = path.with_name(f"{name}.{index}")
            if old.is_symlink() or new.is_symlink():
                raise RuntimeError("Refusing to rotate symlinked Bridge startup logs")
            if old.exists():
                old.replace(new)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8787)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("port must be in 1..65535")
    directory, source = resolve_data_dir()
    record_or_verify_data_dir(directory, source, anchor_path())
    import uvicorn
    uvicorn.run("bridge.app.main:app", host="127.0.0.1", port=args.port,
                log_config=logging_config(directory), access_log=False)


if __name__ == "__main__":
    main()
