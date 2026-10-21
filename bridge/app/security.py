"""Local access token and short-lived browser sessions."""

import hmac
import os
import secrets
import threading
import time
from collections.abc import Mapping
from pathlib import Path

SESSION_SECONDS = 12 * 60 * 60
MAX_LOGIN_FAILURES = 5
LOGIN_LOCK_SECONDS = 5 * 60

DATA_DIR_ENV = "ROBOT_DATA_DIR"
ANCHOR_ENV = "ROBOT_DATA_ANCHOR"
ALLOW_INIT_ENV = "ROBOT_ALLOW_INIT"


class DataDirConflict(RuntimeError):
    """The resolved store disagrees with the one this machine is anchored to."""


def resolve_data_dir(environ: Mapping[str, str] | None = None) -> tuple[Path, str]:
    """Resolve the store directory and say where the answer came from.

    ``ROBOT_DATA_DIR`` pins the directory explicitly, so a launcher (scheduled
    task, shortcut, service wrapper) can always point at the same store no
    matter which user context resolves ``LOCALAPPDATA``.
    """
    env = os.environ if environ is None else environ
    pinned = (env.get(DATA_DIR_ENV) or "").strip()
    if pinned:
        path = Path(pinned)
        if not path.is_absolute():
            raise DataDirConflict(f"{DATA_DIR_ENV} must be an absolute path, got {pinned!r}")
        return path, "env"
    base = env.get("LOCALAPPDATA")
    if base:
        return Path(base) / "DesktopAiRobot", "localappdata"
    return Path.home() / ".desktop-ai-robot", "home"


def default_data_dir() -> Path:
    return resolve_data_dir()[0]


def anchor_path(environ: Mapping[str, str] | None = None) -> Path:
    """Machine-wide pointer to the one real store directory."""
    env = os.environ if environ is None else environ
    override = (env.get(ANCHOR_ENV) or "").strip()
    if override:
        return Path(override)
    program_data = env.get("PROGRAMDATA") or env.get("ALLUSERSPROFILE")
    base = Path(program_data) if program_data else Path.home()
    return base / "DesktopAiRobot" / "data-dir.txt"


def _env_flag(name: str, environ: Mapping[str, str] | None = None) -> bool:
    env = os.environ if environ is None else environ
    return (env.get(name) or "").strip().lower() in {"1", "true", "yes", "on"}


def record_or_verify_data_dir(data_dir: Path, source: str, anchor: Path,
                              environ: Mapping[str, str] | None = None) -> dict:
    """Anchor the store on first run, then refuse to diverge from it.

    Without this, a process started in a different context (scheduled task
    running as another account, elevated shell, service wrapper) resolves a
    different ``LOCALAPPDATA``, silently mints a second access token and a
    second empty message database, and the user's own key stops working.
    """
    data_dir.mkdir(parents=True, exist_ok=True)
    resolved = str(data_dir.resolve())
    record = {"path": resolved, "source": source, "anchor": str(anchor), "consistent": True}

    recorded = ""
    if anchor.is_file():
        try:
            recorded = anchor.read_text(encoding="utf-8").strip()
        except OSError:
            recorded = ""
    if recorded:
        if Path(recorded).resolve() == Path(resolved):
            return record
        if not _env_flag(ALLOW_INIT_ENV, environ):
            raise DataDirConflict(
                f"Bridge data directory mismatch. This machine is anchored to {recorded}, "
                f"but this process resolved {resolved} (source={source}). Refusing to start so "
                f"the message database cannot fork. Set {DATA_DIR_ENV} to the anchored path, "
                f"or set {ALLOW_INIT_ENV}=1 once to adopt {resolved} as the new store.")
        record["adopted"] = True
    try:
        anchor.parent.mkdir(parents=True, exist_ok=True)
        anchor.write_text(resolved + "\n", encoding="utf-8")
    except OSError:
        record["anchored"] = False
        return record
    record["anchored"] = True
    return record


def load_or_create_token(data_dir: Path) -> str:
    data_dir.mkdir(parents=True, exist_ok=True)
    path = data_dir / "access-token.txt"
    if not path.exists():
        token = secrets.token_urlsafe(32)
        try:
            with path.open("x", encoding="utf-8") as stream:
                stream.write(token + "\n")
        except FileExistsError:
            pass
        if os.name != "nt":
            path.chmod(0o600)
    return path.read_text(encoding="utf-8").strip()


class Sessions:
    def __init__(self, access_token: str):
        self.access_token = access_token
        self._expires: dict[str, float] = {}
        self._failed: dict[str, tuple[int, float]] = {}
        self._lock = threading.Lock()
        self._voice_sessions: set[str] = set()
        self._voice_grant: str | None = None

    def voice_grant(self) -> str | None:
        with self._lock:
            self._voice_sessions = {key for key in self._voice_sessions
                                    if self._expires.get(key, 0) > time.time()}
            if not self._voice_sessions:
                self._voice_grant = None
            return self._voice_grant

    def authorize_voice(self, session: str | None) -> bool:
        with self._lock:
            if not session or self._expires.get(session, 0) <= time.time():
                return False
            active = {key for key in self._voice_sessions if self._expires.get(key, 0) > time.time()}
            if not active:
                self._voice_grant = secrets.token_urlsafe(24)
            self._voice_sessions = active | {session}
            return True

    def login(self, presented: str, client_id: str = "local") -> str | None:
        with self._lock:
            failures, locked_until = self._failed.get(client_id, (0, 0.0))
            now = time.monotonic()
            if locked_until > now:
                return None
            if not hmac.compare_digest(presented, self.access_token):
                failures = failures + 1 if locked_until == 0.0 else 1
                self._failed[client_id] = (
                    failures, now + LOGIN_LOCK_SECONDS if failures >= MAX_LOGIN_FAILURES else 0.0)
                return None
            self._failed.pop(client_id, None)
            session = secrets.token_urlsafe(32)
            self._expires[session] = time.time() + SESSION_SECONDS
            return session

    def valid(self, session: str | None) -> bool:
        if not session:
            return False
        with self._lock:
            expires = self._expires.get(session, 0)
            if expires <= time.time():
                self._expires.pop(session, None)
                return False
            return True

    def logout(self, session: str | None) -> None:
        if session:
            with self._lock:
                self._expires.pop(session, None)
                self._voice_sessions.discard(session)
