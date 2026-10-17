import numpy as np
import pytest

from bridge.app.audio_output import AudioOutput


def test_output_scales_signed_pcm_and_persists(tmp_path):
    output = AudioOutput(tmp_path)
    pcm = np.array([-32768, -1000, 0, 1000, 32767], dtype='<i2').tobytes()
    assert output.scale_pcm(pcm) == pcm
    output.update(volume=50)
    assert np.frombuffer(output.scale_pcm(pcm), dtype='<i2').tolist() == [-16384, -500, 0, 500, 16384]
    output.update(muted=True)
    assert output.scale_pcm(pcm) == bytes(len(pcm))
    assert AudioOutput(tmp_path).snapshot() == {'volume': 50, 'muted': True, 'enabled': False}
    output.update(muted=False, volume=0)
    assert not output.enabled
    for invalid in (-1, 101, True, 0.5):
        with pytest.raises(ValueError):
            output.update(volume=invalid)
