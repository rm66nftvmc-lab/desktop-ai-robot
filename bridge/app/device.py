"""Single-owner USB CDC worker for ESP32-S3 voice-device firmware."""

import json
import io
import math
import struct
import threading
import time
import wave

import serial
from serial.tools import list_ports

from . import faces, protocol
from .audio_output import AudioOutput


def open_device_port(name: str):
    """Set reset-sensitive control lines before opening the ESP32 USB port."""
    port = serial.Serial(port=None, baudrate=115200, timeout=0.005,
                         write_timeout=0.5, dsrdtr=False)
    port.dtr = False
    port.rts = False
    port.port = name
    try:
        port.open()
    except Exception:
        port.close()
        raise
    return port


def find_port() -> str | None:
    for port in list_ports.comports():
        if port.vid == 0x303A:
            return port.device
    return None


class DeviceLink:
    MAX_CAPTURE_BYTES = 60 * 16000 * 2

    def __init__(self, on_capture=None, on_listen_start=None, *, audio_output=None, on_disconnect=None):
        self.audio_output = audio_output if audio_output is not None else AudioOutput()
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._capture = bytearray()
        self._last_capture = b""
        self._on_capture = on_capture
        self._on_listen_start = on_listen_start
        self._on_disconnect = on_disconnect
        self._capture_generation = 0
        self._playback: bytes | None = None
        self._playback_offset = 0
        self._playback_generation = 0
        self._playback_open = False
        self._state = {
            "present": False,
            "connected": False,
            "port": None,
            "protocol": "v1",
            "listening": False,
            "playing": False,
            "audio_down_sent": 0,
            "audio_down_ack": 0,
            "audio_samples": 0,
            "audio_peak": 0,
            "audio_rms": 0.0,
            "last_capture_samples": 0,
            "capture_truncated": False,
            "firmware": None,
            "uptime_ms": None,
            "speaker_ready": None,
            "device_playing": None,
            "device_audio_rx": None,
            "device_audio_ack": None,
            "device_bad_crc": None,
            "reset_reason": None,
            "device_face": None,
            "device_frame": None,
            "screen_buffer": None,
            "screen_compose_us": None,
            "screen_push_us": None,
            "animation_enabled": None,
            "screen_presents": None,
            "screen_source_updates": None,
            "screen_cached_frames": None,
            "screen_ball_bytes": None,
            "screen_dirty_tiles": None,
            "screen_diff_buffer": None,
            "face": None,
            "last_error": None,
        }
        self._pending_face: int | None = None
        self._pending_animation: bool | None = None
        self._animation_requested = True
        self._animation_sent: bool | None = None
        self._quiet_playback = False
        self._desired_theme = 1
        self._pending_theme = 1
        self._state['display_theme'] = None
        self._state['desired_theme'] = 1

    def set_theme(self, theme: int) -> None:
        if type(theme) is not int or theme not in (1, 2):
            raise ValueError('Unknown display theme')
        with self._lock:
            self._desired_theme = self._pending_theme = theme
            self._state['desired_theme'] = theme

    def _send_pending_theme(self, port, sequence: int) -> int:
        with self._lock:
            theme = self._pending_theme
            if theme is None or not self._state['connected']:
                return sequence
            self._pending_theme = None
        port.write(protocol.encode(protocol.THEME, sequence, bytes([theme])))
        return (sequence + 1) & 0xFFFF

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="esp32-usb-link", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)

    def snapshot(self) -> dict:
        with self._lock:
            return dict(self._state)

    def set_face(self, face: int | None) -> None:
        """Queue the expression the robot should show next."""
        if face is None or not 0 <= face < faces.COUNT:
            return
        with self._lock:
            self._pending_face = face
            self._state["face"] = face

    def _send_pending_face(self, port, sequence: int) -> int:
        with self._lock:
            face = self._pending_face
            if face is None or not self._state["connected"]:
                return sequence
            self._pending_face = None
        port.write(protocol.encode(protocol.FACE, sequence, bytes([face])))
        return (sequence + 1) & 0xFFFF

    def set_animation(self, enabled: bool) -> None:
        with self._lock:
            self._animation_requested = enabled
            self._pending_animation = enabled

    def set_quiet_playback(self, enabled: bool) -> None:
        with self._lock:
            self._quiet_playback = enabled

    def _send_pending_animation(self, port, sequence: int) -> int:
        with self._lock:
            if not self._state["connected"]:
                return sequence
            speaking = self._state['playing'] or self._state['device_playing']
            enabled = self._animation_requested and not (self._quiet_playback and self._desired_theme == 1 and speaking)
            if enabled == self._animation_sent and self._pending_animation is None:
                return sequence
            self._pending_animation = None
            self._animation_sent = enabled
        port.write(protocol.encode(protocol.ANIMATION, sequence, bytes([enabled])))
        return (sequence + 1) & 0xFFFF

    def last_capture_wav(self) -> bytes | None:
        with self._lock:
            pcm = self._last_capture
        if not pcm:
            return None
        output = io.BytesIO()
        with wave.open(output, "wb") as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(16000)
            audio.writeframes(pcm)
        return output.getvalue()

    def stop_playback(self, *, expected_generation: int | None = None) -> int | None:
        """Invalidate earlier speech requests and stop the current stream."""
        with self._lock:
            if expected_generation is not None and expected_generation != self._playback_generation:
                return None
            if not self._state["connected"] or self._state["listening"]:
                return None
            self._playback_generation += 1
            self._playback = None
            self._playback_offset = 0
            self._playback_open = False
            self._state["playing"] = False
            self._state["last_error"] = None
            return self._playback_generation

    def is_current_generation(self, generation: int) -> bool:
        with self._lock:
            return self._playback_generation == generation

    def play_wav(self, wav: bytes, *, generation: int | None = None) -> bool:
        return self.append_wav(wav, generation=generation, start_only=True)

    def append_wav(self, wav: bytes, *, generation: int | None = None,
                   start_only: bool = False) -> bool:
        if not self.audio_output.enabled:
            return False
        try:
            with wave.open(io.BytesIO(wav), "rb") as audio:
                if (audio.getnchannels(), audio.getsampwidth(), audio.getframerate()) != (1, 2, 16000):
                    raise ValueError("Audio must be 16 kHz mono PCM16")
                pcm = audio.readframes(audio.getnframes())
        except (wave.Error, EOFError) as exc:
            raise ValueError("Invalid WAV") from exc
        if not pcm:
            raise ValueError("Empty WAV")
        with self._lock:
            if generation is not None and generation != self._playback_generation:
                return False
            if not self._state["connected"] or self._state["listening"]:
                return False
            if self._state["playing"]:
                if start_only:
                    return False
                if self._playback is None:
                    self._playback = pcm
                    self._playback_offset = 0
                else:
                    self._playback += pcm
            else:
                self._playback = pcm
                self._playback_offset = 0
            if not start_only:
                self._playback_open = True
            self._state["playing"] = True
        return True

    def finish_playback(self, generation: int) -> None:
        with self._lock:
            if generation == self._playback_generation:
                self._playback_open = False

    def _update(self, **fields) -> None:
        with self._lock:
            self._state.update(fields)

    def _connection_lost(self) -> None:
        with self._lock:
            self._animation_sent = None
            active = self._state["connected"] or self._state["listening"] or self._state["playing"]
            self._capture_generation += 1
            self._capture.clear()
            self._last_capture = b""
            self._playback_generation += 1
            self._playback = None
            self._playback_offset = 0
            self._playback_open = False
            self._state.update(connected=False, listening=False, playing=False, device_playing=False)
        if active and self._on_disconnect:
            self._on_disconnect()

    def _fail_playback(self, error: str) -> None:
        with self._lock:
            self._playback_generation += 1
            self._playback = None
            self._playback_open = False
            self._state.update(playing=False, last_error=error)
        self.set_face(faces.ERROR)

    def _handle(self, frame: protocol.Frame, port: serial.Serial, sequence: int) -> int:
        if frame.kind == protocol.HELLO:
            try:
                hello = json.loads(frame.payload)
            except (ValueError, UnicodeDecodeError):
                return sequence
            if hello.get("protocol") != 1:
                self._update(last_error="Unsupported device protocol")
                return sequence
            if self.snapshot()["connected"]:
                self._connection_lost()
            self._update(connected=True, firmware=hello.get("firmware"), last_error=None)
            self.set_face(faces.READY)
            with self._lock:
                self._pending_theme = self._desired_theme
            port.write(protocol.encode(protocol.WELCOME, sequence, b'{"protocol":1}'))
            return (sequence + 1) & 0xFFFF
        if frame.kind == protocol.STATUS:
            try:
                status = json.loads(frame.payload)
            except (ValueError, UnicodeDecodeError):
                return sequence
            self._update(
                listening=bool(status.get("listening", False)),
                uptime_ms=status.get("uptime_ms"),
                speaker_ready=status.get("speaker_ready"),
                device_playing=status.get("playing"),
                device_audio_rx=status.get("audio_rx"),
                device_audio_ack=status.get("audio_ack"),
                device_bad_crc=status.get("bad_crc"),
                reset_reason=status.get("reset_reason"),
                device_face=status.get("face"),
                device_frame=status.get("frame"),
                screen_buffer=status.get("screen_buffer"),
                screen_compose_us=status.get("compose_us"),
                screen_push_us=status.get("push_us"),
                animation_enabled=status.get("animation_enabled"),
                screen_presents=status.get("presents"),
                screen_source_updates=status.get("source_updates"),
                screen_cached_frames=status.get("cached_frames"),
                display_theme=status.get('display_theme'),
                pet_action=status.get('pet_action'), pet_frame=status.get('pet_frame'),
                pet_random_count=status.get('pet_random_count'), pet_decode_errors=status.get('pet_decode_errors'),
                screen_ball_bytes=status.get('ball_bytes'),
                screen_dirty_tiles=status.get('dirty_tiles'),
                screen_diff_buffer=status.get('diff_buffer'),
            )
        elif frame.kind == protocol.BUTTON and frame.payload:
            listening = frame.payload[0] == 1
            if listening:
                with self._lock:
                    self._capture_generation += 1
                    capture_generation = self._capture_generation
                    self._playback_generation += 1
                    self._playback = None
                    self._state["playing"] = False
                    self._capture.clear()
                    self._last_capture = b""
                    self._state.update(listening=True, audio_samples=0, audio_peak=0,
                                       audio_rms=0.0, capture_truncated=False)
                self.set_face(faces.LISTEN)
                if self._on_listen_start:
                    self._on_listen_start(capture_generation)
            else:
                with self._lock:
                    capture_generation = self._capture_generation
                    self._state["last_capture_samples"] = self._state["audio_samples"]
                    self._state["listening"] = False
                    self._last_capture = bytes(self._capture)
                    self._capture.clear()
                self.set_face(faces.THINK)
                if self._on_capture:
                    self._on_capture(self.last_capture_wav(), capture_generation)
        elif frame.kind == protocol.AUDIO_UP and len(frame.payload) % 2 == 0:
            samples = struct.unpack(f"<{len(frame.payload) // 2}h", frame.payload)
            if samples:
                peak = max(abs(value) for value in samples)
                rms = math.sqrt(sum(value * value for value in samples) / len(samples))
                with self._lock:
                    if self._state["listening"]:
                        self._state["audio_samples"] += len(samples)
                        self._state["audio_peak"] = max(self._state["audio_peak"], peak)
                        self._state["audio_rms"] = round(rms, 1)
                        remaining = self.MAX_CAPTURE_BYTES - len(self._capture)
                        self._capture.extend(frame.payload[:remaining])
                        if len(frame.payload) > remaining:
                            self._state["capture_truncated"] = True
        return sequence

    def _run(self) -> None:
        while not self._stop.is_set():
            name = find_port()
            self._update(present=bool(name), port=name)
            if not name:
                self._connection_lost()
                self.set_face(faces.SLEEP)
                self._stop.wait(1)
                continue
            try:
                with open_device_port(name) as port:
                    parser = protocol.FrameParser()
                    sequence = 0
                    # Some USB drivers reset the chip even with preconfigured
                    # control lines. Read HELLO during boot; an early write can
                    # time out and create an endless reopen/reset loop.
                    next_heartbeat = time.monotonic() + 3.0
                    in_flight = 0
                    playback_active = False
                    last_ack = 0.0
                    last_seen = time.monotonic()
                    with self._lock:
                        active_generation = self._playback_generation
                    while not self._stop.is_set():
                        now = time.monotonic()
                        sequence = self._send_pending_face(port, sequence)
                        sequence = self._send_pending_theme(port, sequence)
                        sequence = self._send_pending_animation(port, sequence)
                        if now >= next_heartbeat:
                            port.write(protocol.encode(protocol.HEARTBEAT, sequence))
                            sequence = (sequence + 1) & 0xFFFF
                            next_heartbeat = now + 1
                        for frame in parser.feed(port.read(4096)):
                            last_seen = time.monotonic()
                            sequence = self._handle(frame, port, sequence)
                            if frame.kind == protocol.BUTTON and frame.payload == b"\x01":
                                in_flight = 0
                                playback_active = False
                            elif frame.kind == protocol.ACK and in_flight:
                                in_flight -= 1
                                last_ack = time.monotonic()
                                with self._lock:
                                    self._state["audio_down_ack"] += 1
                                if frame.payload != b"\x01":
                                    self._fail_playback("扬声器缓冲写入失败，请重新朗读")
                                    in_flight = 0
                                    playback_active = False
                                    port.write(protocol.encode(protocol.AUDIO_END, sequence))
                                    sequence = (sequence + 1) & 0xFFFF
                        if time.monotonic() - last_seen > 8:
                            raise serial.SerialException("Device heartbeat timeout")
                        if playback_active and in_flight and time.monotonic() - last_ack > 5:
                            self._fail_playback("扬声器回执超时，请检查连接后重新朗读")
                            in_flight = 0
                            playback_active = False
                            port.write(protocol.encode(protocol.AUDIO_END, sequence))
                            sequence = (sequence + 1) & 0xFFFF
                        with self._lock:
                            generation = self._playback_generation
                        if generation != active_generation:
                            if in_flight:
                                continue
                            if playback_active:
                                port.write(protocol.encode(protocol.AUDIO_END, sequence))
                                sequence = (sequence + 1) & 0xFFFF
                                playback_active = False
                            active_generation = generation
                        while in_flight < 3:
                            with self._lock:
                                if self._playback_generation != active_generation:
                                    break
                                if self._playback is None:
                                    # Keep the I2S stream clocked while the next speech
                                    # segment is synthesized. A gap in USB audio frames
                                    # can otherwise sound like a crackle on the amplifier.
                                    chunk = (bytes(1024) if self._playback_open
                                             and playback_active and in_flight < 2 else None)
                                else:
                                    chunk = self._playback[self._playback_offset:self._playback_offset + 1024]
                                    self._playback_offset += len(chunk)
                                    if self._playback_offset >= len(self._playback):
                                        self._playback = None
                            if not chunk:
                                break
                            chunk = self.audio_output.scale_pcm(chunk)
                            port.write(protocol.encode(protocol.AUDIO_DOWN, sequence, chunk))
                            sequence = (sequence + 1) & 0xFFFF
                            with self._lock:
                                self._state["audio_down_sent"] += 1
                            if not playback_active:
                                last_ack = time.monotonic()
                                self.set_face(faces.SPEAK)
                            playback_active = True
                            in_flight += 1
                        if playback_active and not in_flight:
                            with self._lock:
                                more_audio = self._playback is not None or self._playback_open
                            if not more_audio:
                                port.write(protocol.encode(protocol.AUDIO_END, sequence))
                                sequence = (sequence + 1) & 0xFFFF
                                self._update(playing=False)
                                self.set_face(faces.READY)
                                playback_active = False
            except (serial.SerialException, OSError, ValueError) as exc:
                self._update(last_error=type(exc).__name__)
            finally:
                self._connection_lost()
                self.set_face(faces.SLEEP)
            self._stop.wait(1)
