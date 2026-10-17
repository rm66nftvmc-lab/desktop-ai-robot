"""The robot's expressions, and the frame that tells it which one to wear.

The face indices are shared between three places that can drift apart: this
module, the generated ``voice-device/src/faces.h``, and the firmware that draws
them. These tests pin the first two together so a mismatch fails in CI instead
of showing the wrong feeling on the device.
"""

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from bridge.app import faces, protocol
from bridge.app.device import DeviceLink
from bridge.app.main import SOURCES, create_app

FACES_HEADER = Path(__file__).resolve().parents[2] / "voice-device" / "src" / "faces.h"


class FakePort:
    def __init__(self):
        self.writes: list[bytes] = []

    def write(self, data: bytes) -> int:
        self.writes.append(data)
        return len(data)


class FakeHermes:
    executable = "hermes-test"

    def __init__(self):
        self.jobs = []

    def start(self):
        pass

    def stop(self):
        pass

    def snapshot(self):
        return {"available": True, "pending": 0, "running": False, "last_error": None}

    def enqueue(self, message_id, text, *, new_session=False):
        self.jobs.append((message_id, text, new_session))
        return True


# --------------------------------------------------------------- index agreement
def test_bridge_face_order_matches_the_generated_header():
    entries = re.findall(r"FACE_ID_(\w+)\s*=\s*(\d+)", FACES_HEADER.read_text(encoding="utf-8"))
    assert entries, "faces.h has no FACE_ID_ enum; re-run scripts/build_faces.py"
    assert [name for name, _ in entries] == list(faces.NAMES)
    assert [int(index) for _, index in entries] == list(range(faces.COUNT))


def test_every_face_has_artwork_in_the_header():
    text = FACES_HEADER.read_text(encoding="utf-8")
    for name in faces.NAMES:
        assert f"FACE_{name}[]" in text


# --------------------------------------------------------------- lookup + resolve
def test_face_lookup_ignores_unknown_and_untidy_names():
    assert faces.face_id("think") == faces.THINK
    assert faces.face_id(" SPEAK ") == faces.SPEAK
    assert faces.face_id("smug") is None


def test_a_fault_outranks_everything_else():
    assert faces.resolve(connected=True, error=True, approval=True, listening=True) == faces.ERROR


def test_a_pending_approval_outranks_routine_activity():
    assert faces.resolve(connected=True, approval=True, playing=True) == faces.APPROVE
    assert faces.resolve(connected=True, listening=True, thinking=True) == faces.LISTEN
    assert faces.resolve(connected=True, playing=True, thinking=True) == faces.SPEAK


def test_disconnected_always_looks_asleep():
    assert faces.resolve(connected=False, listening=True) == faces.SLEEP


def test_idle_connected_robot_looks_ready():
    assert faces.resolve(connected=True) == faces.READY
    assert faces.resolve(connected=True, thinking=True) == faces.THINK


# --------------------------------------------------------------- frame on the wire
def test_face_frame_round_trips_through_the_parser():
    encoded = protocol.encode(protocol.FACE, 9, bytes([faces.SPEAK]))
    (frame,) = protocol.FrameParser().feed(encoded)
    assert frame.kind == protocol.FACE
    assert frame.sequence == 9
    assert frame.payload == bytes([faces.SPEAK])


def test_set_face_sends_one_frame_and_clears_the_queue():
    link = DeviceLink()
    link._state["connected"] = True
    link.set_face(faces.THINK)

    port = FakePort()
    assert link._send_pending_face(port, 7) == 8
    (frame,) = protocol.FrameParser().feed(b"".join(port.writes))
    assert (frame.kind, frame.sequence, frame.payload) == (protocol.FACE, 7, bytes([faces.THINK]))
    assert link.snapshot()["face"] == faces.THINK

    # Nothing is pending any more, so the next pass writes nothing.
    assert link._send_pending_face(port, 8) == 8
    assert len(port.writes) == 1


def test_a_face_waits_for_the_handshake_instead_of_being_dropped():
    link = DeviceLink()
    link.set_face(faces.READY)
    port = FakePort()

    assert link._send_pending_face(port, 3) == 3
    assert port.writes == []

    link._state["connected"] = True
    assert link._send_pending_face(port, 3) == 4
    assert len(port.writes) == 1


def test_out_of_range_faces_are_ignored_rather_than_guessed():
    link = DeviceLink()
    for invalid in (-1, faces.COUNT, 99, None):
        link.set_face(invalid)
    assert link.snapshot()["face"] is None


# --------------------------------------------------------------- scope: no DeepSeek
def test_deepseek_web_is_no_longer_a_target():
    assert "deepseek_web" not in SOURCES
    assert "doubao_web" in SOURCES


def test_the_api_refuses_the_removed_target(tmp_path):
    client = TestClient(create_app(tmp_path, token="test-access-token-for-bridge",
                                   hermes_worker=FakeHermes()),
                        base_url="http://127.0.0.1")
    client.post("/api/login", json={"token": "test-access-token-for-bridge"})
    assert client.post("/api/messages", json={"source": "deepseek_web", "text": "hello"}).status_code == 400
    assert client.post("/api/messages", json={"source": "doubao_web", "text": "hello"}).status_code == 200
    assert client.get("/api/status").json()["delivery"] == {"hermes": "connected", "doubao_web": "not_configured"}
