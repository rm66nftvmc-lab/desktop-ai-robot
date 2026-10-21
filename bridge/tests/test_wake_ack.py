from bridge.app.audio_output import AudioOutput
from bridge.app.wake_ack import WakeAcknowledgement
import io
import wave


def cue():
    result = io.BytesIO()
    with wave.open(result, 'wb') as audio:
        audio.setnchannels(1); audio.setsampwidth(2); audio.setframerate(16000)
        audio.writeframes(b'\x00\x00'*800 + b'\x00\x04'*1600 + b'\x00\x00'*3200)
    return result.getvalue()


class Device:
    def __init__(self):
        self.state = {'connected': True, 'playing': False, 'device_playing': False}
        self.generation = 0
        self.clips = []

    def snapshot(self):
        return dict(self.state)

    def stop_playback(self, expected_generation=None):
        if expected_generation is not None and expected_generation != self.generation:
            return None
        self.generation += 1
        self.state['playing'] = False
        return self.generation

    def is_current_generation(self, generation):
        return generation == self.generation

    def append_wav(self, clip, generation):
        self.clips.append(clip)
        self.state['playing'] = True
        return True

    def finish_playback(self, generation):
        pass


def test_ack_uses_current_voice_cache_and_waits_for_device_playback(tmp_path, monkeypatch):
    device, clock, voice, calls = Device(), [1.0], ['paimon'], []
    def synthesize(text, data_dir, cancelled):
        calls.append((text, voice[0]))
        return [cue()]
    def sleep(duration):
        clock[0] += duration
        device.state['playing'] = False
        device.state['device_playing'] = clock[0] < 1.5
    monkeypatch.setattr('bridge.app.wake_ack.selected_voice', lambda _: voice[0])
    monkeypatch.setattr('bridge.app.wake_ack.synthesize_chunks', synthesize)
    monkeypatch.setattr('bridge.app.wake_ack.time.monotonic', lambda: clock[0])
    monkeypatch.setattr('bridge.app.wake_ack.time.sleep', sleep)
    ack = WakeAcknowledgement(tmp_path, device, AudioOutput())
    assert ack(lambda: False)
    assert clock[0] >= 1.8  # Hardware is quiet plus an echo tail, not just queued.
    assert ack(lambda: False)
    assert calls == [('在呢！', 'paimon')]
    voice[0] = 'cosyvoice'
    assert ack(lambda: False)
    assert calls[-1] == ('在呢！', 'cosyvoice')


def test_muted_or_cancelled_ack_never_synthesizes(tmp_path, monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError('Unexpected synthesis')
    monkeypatch.setattr('bridge.app.wake_ack.synthesize_chunks', fail)
    output, device = AudioOutput(), Device()
    ack = WakeAcknowledgement(tmp_path, device, output)
    output.update(muted=True)
    assert ack(lambda: False)
    assert not ack(lambda: True)
    assert not device.clips


def test_warmup_persists_short_cue_and_restart_needs_no_synthesis(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr('bridge.app.wake_ack.selected_voice', lambda _: 'paimon')
    monkeypatch.setattr('bridge.app.wake_ack.synthesize_chunks',
                        lambda *args, **kwargs: calls.append(args[0]) or [cue()])
    ack = WakeAcknowledgement(tmp_path, Device(), AudioOutput())
    ack.warm()
    ack._warm_thread.join(2)
    assert ack.snapshot()['ready'] and calls == ['在呢！']
    assert not ack.device.clips  # Warmup must never play sound.
    with wave.open(io.BytesIO(ack._clips[0]), 'rb') as audio:
        assert audio.getnframes() < 5600  # Long blank tail removed without cutting speech.
    restored = WakeAcknowledgement(tmp_path, Device(), AudioOutput())
    assert restored.prepare()
    assert calls == ['在呢！']


def test_acknowledged_audio_end_does_not_wait_for_stale_status(tmp_path, monkeypatch):
    clock, device = [1.0], Device()
    monkeypatch.setattr('bridge.app.wake_ack.selected_voice', lambda _: 'paimon')
    monkeypatch.setattr('bridge.app.wake_ack.synthesize_chunks', lambda *a, **k: [cue()])
    monkeypatch.setattr('bridge.app.wake_ack.time.monotonic', lambda: clock[0])
    def sleep(duration):
        clock[0] += duration
        device.state.update(playing=False, device_playing=True,
                            playback_finished_generation=device.generation)
    monkeypatch.setattr('bridge.app.wake_ack.time.sleep', sleep)
    ack = WakeAcknowledgement(tmp_path, device, AudioOutput())
    assert ack(lambda: False)
    assert clock[0] < 1.5  # The 300 ms echo guard remains; no 3-second STATUS wait.


def test_preparation_retries_a_cue_with_an_internal_pause(tmp_path, monkeypatch):
    result = io.BytesIO()
    with wave.open(result, 'wb') as audio:
        audio.setnchannels(1); audio.setsampwidth(2); audio.setframerate(16000)
        audio.writeframes(b'\x00\x04'*3200 + b'\x00\x00'*4000 + b'\x00\x04'*3200)
    awkward = result.getvalue()
    calls = []
    def synthesize(text, *args, **kwargs):
        calls.append(text)
        return [awkward if len(calls) == 1 else cue()]
    monkeypatch.setattr('bridge.app.wake_ack.selected_voice', lambda _: 'paimon')
    monkeypatch.setattr('bridge.app.wake_ack.synthesize_chunks', synthesize)
    ack = WakeAcknowledgement(tmp_path, Device(), AudioOutput())
    assert ack.prepare()
    assert calls == ['在呢！', '在呢！']
    assert ack._rhythm(ack._clips[0])[1] == 0
    assert not ack.device.clips


def test_recording_after_acknowledgement_ignores_only_completed_stream_status():
    from bridge.app.device import DeviceLink
    device = DeviceLink()
    device._update(connected=True, wake_protocol=1, device_playing=True)
    assert not device.request_capture(1)
    device._update(playback_finished_generation=device._playback_generation)
    assert device.request_capture(1)
    # A newly started stream must not inherit the previous completion marker.
    device.stop_playback()
    device._update(playing=True)
    assert not device.request_capture(1)


def test_rejected_capture_after_cue_rearms_instead_of_sticking_in_error(tmp_path):
    from bridge.app.wake import WakeWorker
    from bridge.app.storage import initialize
    database = tmp_path/'messages.sqlite3'
    initialize(database)
    class BusyDevice(Device):
        def configure_wake(self, *args):
            pass
        def request_capture(self, *args):
            return False
    wake = WakeWorker(database, tmp_path, BusyDevice(), acknowledge=lambda cancelled: True)
    wake._enabled, wake._state = True, 'acknowledging'
    wake._acknowledge_wake()
    assert wake.snapshot()['state'] == 'armed'
    assert wake.snapshot()['last_error']
