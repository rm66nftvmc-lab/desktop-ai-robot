"""Safe subprocess invocation helpers for Windows command shims."""

import os
import re
import subprocess
from pathlib import Path


_SAFE_CLI_ARGUMENT = re.compile(r"^[A-Za-z0-9_.:-]+$")


def command_invocation(executable: str, arguments: list[str]) -> tuple[object, dict]:
    """Return subprocess args/options, correctly handling Windows .cmd shims.

    User content must be passed on stdin, never in ``arguments``. Restricting
    shim arguments prevents shell metacharacters from entering cmd.exe.
    """
    path = Path(executable)
    if os.name == "nt" and path.suffix.lower() in {".cmd", ".bat"}:
        if any(not _SAFE_CLI_ARGUMENT.fullmatch(str(arg)) for arg in arguments):
            raise ValueError("Unsafe argument for Windows command shim")
        return subprocess.list2cmdline([str(path), *map(str, arguments)]), {"shell": True}
    return [str(path), *map(str, arguments)], {}
