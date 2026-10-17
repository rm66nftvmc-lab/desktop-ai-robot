import io
import struct
import wave

from bridge.app.device import DeviceLink
from bridge.app.protocol import AUDIO_UP, BUTTON, Frame


def test_animation_pause_is_queued_until_connected_without_stopping_audio():
    from bridge.app.protocol import ANIMATION, FrameParser

    device = DeviceLink()
    port = io.BytesIO()
    device.set_animation(False)
    assert device._send_pending_animation(port, 8) == 8
    assert not port.getvalue()
    device._update(connected=True, playing=True)
    assert device._send_pending_animation(port, 8) == 9
    assert FrameParser().feed(port.getvalue()) == [Frame(ANIMATION, 8, b'\x00')]
    assert device.snapshot()['playing'] is True
    assert device._send_pending_animation(port, 9) == 9


def test_button_capture_produces_local_pcm_wav():
    device = DeviceLink()
    device._handle(Frame(BUTTON, 1, b"\x01"), None, 0)
    device._handle(Frame(AUDIO_UP, 2, struct.pack("<3h", -100, 0, 200)), None, 0)
    device._handle(Frame(BUTTON, 3, b"\x00"), None, 0)

    state = device.snapshot()
    assert state["listening"] is False
    assert state["last_capture_samples"] == 3
    assert state["audio_peak"] == 200
    with wave.open(io.BytesIO(device.last_capture_wav()), "rb") as audio:
        assert (audio.getnchannels(), audio.getframerate(), audio.getsampwidth()) == (1, 16000, 2)
        assert audio.readframes(3) == struct.pack("<3h", -100, 0, 200)


def test_playback_accepts_only_ready_device_and_pcm16():
    device = DeviceLink()
    output = io.BytesIO()
    with wave.open(output, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16000)
        audio.writeframes(struct.pack("<2h", 100, -100))
    wav = output.getvalue()
    assert device.play_wav(wav) is False
    device._update(connected=True)
    assert device.play_wav(wav) is True
    assert device.play_wav(wav) is False


def test_new_speech_invalidates_previous_playback_without_disconnect():
    device = DeviceLink()
    output = io.BytesIO()
    with wave.open(output, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16000)
        audio.writeframes(struct.pack("<8h", *range(8)))
    wav = output.getvalue()
    device._update(connected=True)
    assert device.play_wav(wav)

    first = device.stop_playback()
    assert first is not None
    assert device.snapshot()["connected"] is True
    assert device.snapshot()["playing"] is False
    assert device.play_wav(wav, generation=first)

    second = device.stop_playback()
    assert second != first
    assert device.play_wav(wav, generation=first) is False
    assert device.play_wav(wav, generation=second) is True


def test_streamed_speech_appends_and_only_finishes_current_generation():
    device = DeviceLink()
    output = io.BytesIO()
    with wave.open(output, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16000)
        audio.writeframes(struct.pack("<2h", 100, -100))
    wav = output.getvalue()
    device._update(connected=True)
    generation = device.stop_playback()
    assert device.append_wav(wav, generation=generation)
    assert device.append_wav(wav, generation=generation)
    assert device._playback == struct.pack("<4h", 100, -100, 100, -100)
    assert device._playback_open is True
    device.finish_playback(generation)
    assert device._playback_open is False
    newer = device.stop_playback()
    device.finish_playback(generation)
    assert newer != generation
    assert device.append_wav(wav, generation=generation) is False
