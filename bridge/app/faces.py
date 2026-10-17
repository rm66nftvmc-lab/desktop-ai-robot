"""The expressions the robot shows on its screen.

The robot keeps eight run-length encoded faces in flash (see
``scripts/build_faces.py`` and ``voice-device/src/faces.h``), so it can react
without a network and keeps its expression across a power cut.

The order here must match ``FACE_ID_*`` in the generated header. Nothing is
allowed to drift silently: ``bridge/tests/test_faces.py`` parses that header and
fails if the two lists disagree.
"""

from __future__ import annotations

BOOT = 0
READY = 1
SLEEP = 2
LISTEN = 3
THINK = 4
SPEAK = 5
APPROVE = 6
ERROR = 7

#: Declaration order in faces.h.
NAMES: tuple[str, ...] = ("BOOT", "READY", "SLEEP", "LISTEN", "THINK", "SPEAK", "APPROVE", "ERROR")
COUNT = len(NAMES)

BY_NAME: dict[str, int] = {name: index for index, name in enumerate(NAMES)}


def face_id(name: str) -> int | None:
    """Look a face up by name; unknown names are ignored rather than guessed."""
    return BY_NAME.get(name.strip().upper())


def resolve(*, connected: bool, listening: bool = False, playing: bool = False,
            thinking: bool = False, approval: bool = False, error: bool = False) -> int:
    """Pick the expression for the current state.

    Ordered by how much the user needs to see it: a fault or a pending approval
    outranks a routine state, because those are the two the user has to act on.
    """
    if error:
        return ERROR
    if not connected:
        return SLEEP
    if approval:
        return APPROVE
    if listening:
        return LISTEN
    if playing:
        return SPEAK
    if thinking:
        return THINK
    return READY
