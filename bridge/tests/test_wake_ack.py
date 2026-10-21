from bridge.app.audio_output import AudioOutput
from bridge.app.wake_ack import WakeAcknowledgement


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
        return [voice[0].encode()]
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
    assert calls == [('我在呢', 'paimon')]
    voice[0] = 'cosyvoice'
    assert ack(lambda: False)
    assert calls[-1] == ('我在呢', 'cosyvoice')


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
