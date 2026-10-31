import threading
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from bridge.app.speech_cleanup import SpeechCleanup
from bridge.app.speech import SpeechWorker
from bridge.app.main import create_app


@pytest.fixture(scope='module')
def cleanup():
    result = SpeechCleanup()
    result.prepare()
    return result


@pytest.mark.parametrize('spoken,expected', [
    ('請幫我查一下明天的天氣。', '请帮我查一下明天的天气。'),
    ('我想我想查一下天氣', '我想查一下天气'),
    ('請幫我，請幫我打開 Bridge', '请帮我打开 Bridge'),
    ('提醒我明天，不對，是後天開會。', '提醒我后天开会。'),
    ('設定3分鐘，不對，是5分鐘的計時。', '设定5分钟的计时。'),
    ('買三個，說錯了，是四個蘋果', '买四个苹果'),
    ('明天，不對，是後天，不對，是大後天出發', '大后天出发'),
])
def test_explicit_repairs(cleanup, spoken, expected):
    result = cleanup.process(spoken)
    assert result.original == spoken
    assert result.text == expected


@pytest.mark.parametrize('spoken', [
    '不要不要打开灯', '非常非常好', '看看这个', '一一对应，密码112233',
    '不要明天，不对，是后天去', '我不去，明天，不对，是后天去',
    '明天，不对，是后天开会吗？', '3分，不对，是5分钟',
    '-3度，不对，是4度', '负三度，不对，是四度', 'x3点，不对，是4点',
    '去上海，不对，是杭州', '不是打开，是关掉', '明天还是后天我不确定',
    '嗯，这是我的回答。', 'Hello hello, open Bridge API 3.14',
    '把“明天，不對，是後天”原样保存', '执行 `echo 繁體`',
    'https://example.com/繁體', r'C:\資料\測試.txt',
])
def test_preserves_ambiguous_intent_emphasis_literals_and_numbers(cleanup, spoken):
    assert cleanup.process(spoken).text == spoken


def test_simplified_mode_and_rule_failure_keep_original_meaning(cleanup, monkeypatch):
    raw = '我想我想明天，不對，是後天出發'
    expected = '我想我想明天，不对，是后天出发'
    assert cleanup.process(raw, 'simplified').text == expected
    def fail(*args):
        raise RuntimeError('private detail')
    monkeypatch.setattr('bridge.app.speech_cleanup.light_cleanup', fail)
    result = cleanup.process(raw)
    assert result.text == expected
    assert result.warning and 'private' not in result.warning


def test_recognition_callback_uses_cleaned_text_and_retains_generation(tmp_path, monkeypatch):
    done = threading.Event()
    received = []
    worker = SpeechWorker(tmp_path, on_transcript=lambda *args: (received.append(args), done.set()))
    monkeypatch.setattr(worker, '_load_model', lambda: SimpleNamespace(
        transcribe=lambda *a, **k: ([SimpleNamespace(text='請幫我，請幫我查天氣')], None)))
    worker.start()
    try:
        worker.enqueue(bytes(16044), 17)
        assert done.wait(3)
        assert received == [('请帮我查天气', 17)]
        assert worker.transcripts()[0]['original_text'] == '請幫我，請幫我查天氣'
        assert worker.snapshot()['last_text'] == '请帮我查天气'
    finally:
        worker.stop()


def test_settings_auth_origin_validation_and_persistence(tmp_path):
    token = 'test-cleanup-access-token'
    app = create_app(tmp_path, token=token)
    client = TestClient(app, base_url='http://127.0.0.1')
    path = '/api/speech/cleanup'
    assert app.state.speech.snapshot()['cleanup_mode'] == 'light'
    assert client.post(path, json={'mode':'simplified'}).status_code == 401
    assert client.get('/api/transcripts').status_code == 401
    client.post('/api/login', json={'token':token})
    assert client.post(path, json={'mode':'simplified'}, headers={'origin':'https://example.com'}).status_code == 403
    assert client.post(path, json={'mode':'rewrite'}).status_code == 422
    assert client.post(path, json={'mode':'simplified'}).json() == {'mode':'simplified'}
    assert create_app(tmp_path, token=token).state.speech.snapshot()['cleanup_mode'] == 'simplified'
    assert client.post(path, json={'mode':'light'}).status_code == 200


def test_missing_converter_does_not_lose_the_transcript(monkeypatch):
    cleanup = SpeechCleanup()
    def unavailable():
        raise ImportError('private path')
    monkeypatch.setattr(cleanup, 'prepare', unavailable)
    result = cleanup.process('請保留原文')
    assert result.text == '請保留原文'
    assert result.warning and 'private' not in result.warning
