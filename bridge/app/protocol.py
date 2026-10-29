"""Version 1 USB CDC framing shared with voice-device firmware.

Wire format: A5 5A | type:u8 | seq:u16le | length:u16le | payload | crc16:u16le.
CRC-16/CCITT-FALSE covers type through payload, with init=0xFFFF.
"""

from dataclasses import dataclass
import struct

MAGIC = b"\xA5\x5A"
MAX_PAYLOAD = 1024

STATUS = 0x01
DISPLAY = 0x02
AUDIO_UP = 0x03
AUDIO_DOWN = 0x04
HEARTBEAT = 0x05
BUTTON = 0x06
LEVEL = 0x07
ACK = 0x08
HELLO = 0x09
WELCOME = 0x0A
AUDIO_END = 0x0B
FACE = 0x0C
ANIMATION = 0x0D
THEME = 0x0E
SCREEN_TEST = 0x0F  # Local serial diagnostic: 0 normal, 1 hold, 2 repeat pose, 3 compute without LCD writes.
NETWORK_STATUS = 0x14  # Separate diagnostic packet keeps the original STATUS below 1024 bytes.
WAKE_CONFIG = 0x15
WAKE_AUDIO = 0x16
CAPTURE_CONTROL = 0x17  # 1 start, 0 finish, 2 cancel; BUTTON confirms the result.
STEREO_UP = 0x18  # Interleaved PCM16 slots, 16 kHz; only after capability negotiation.
STEREO_WAKE = 0x19
OPEN_BRIDGE = 0x1A  # Physical long press: open local Bridge in Edge; never grants access.


@dataclass(frozen=True)
class Frame:
    kind: int
    sequence: int
    payload: bytes


def crc16(data: bytes) -> int:
    crc = 0xFFFF
    for value in data:
        crc ^= value << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


def encode(kind: int, sequence: int, payload: bytes = b"") -> bytes:
    if not 0 <= kind <= 255 or not 0 <= sequence <= 65535:
        raise ValueError("Frame type or sequence out of range")
    if len(payload) > MAX_PAYLOAD:
        raise ValueError("Frame payload too large")
    body = struct.pack("<BHH", kind, sequence, len(payload)) + payload
    return MAGIC + body + struct.pack("<H", crc16(body))


class FrameParser:
    def __init__(self):
        self.buffer = bytearray()
        self.bad_crc = 0
        self.bad_length = 0

    def feed(self, data: bytes) -> list[Frame]:
        self.buffer.extend(data)
        frames = []
        while True:
            start = self.buffer.find(MAGIC)
            if start < 0:
                self.buffer[:] = self.buffer[-1:] if self.buffer.endswith(MAGIC[:1]) else b""
                return frames
            if start:
                del self.buffer[:start]
            if len(self.buffer) < 9:
                return frames
            kind, sequence, length = struct.unpack_from("<BHH", self.buffer, 2)
            if length > MAX_PAYLOAD:
                self.bad_length += 1
                del self.buffer[0]
                continue
            size = 9 + length
            if len(self.buffer) < size:
                return frames
            expected = struct.unpack_from("<H", self.buffer, size - 2)[0]
            actual = crc16(self.buffer[2:size - 2])
            if expected != actual:
                self.bad_crc += 1
                del self.buffer[0]
                continue
            frames.append(Frame(kind, sequence, bytes(self.buffer[7:size - 2])))
            del self.buffer[:size]
