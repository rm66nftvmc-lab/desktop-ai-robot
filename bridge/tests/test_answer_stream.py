import io
import json
import threading
import time

import pytest
from fastapi.testclient import TestClient
from bridge.app.answer_stream import HarnessTextStream, CancellationUnconfirmed
from bridge.app.device import DeviceLink
from bridge.app.hermes import HermesWorker
from bridge.app.hermes_api import HermesRunsClient
from bridge.app.harness import HarnessWorker
from bridge.app.main import create_app
from bridge.app.protocol import Frame, FrameParser, HELLO, THEME
from bridge.app.storage import initialize, add_message


def record(seq, kind, data):
    return {'type': 'event', 'event': {'seq': seq, 'type': kind, 'data': data}}


def test_harness_replay_and_live_text_ignore_reasoning_tools_and_other_prompts():
    output = []
    stream = HarnessTextStream('ours', 3, output.append)
    stream.accept({'type': 'snapshot', 'records': [record(4, 'user/message', {'source': {'rpcId': 'ours'}})],
        'assistantStream': {'revision': 8, 'activeAttempt': {'startedAfterSeq': 4, 'stream': [
            {'type': 'text-chunks', 'index': 1, 'texts': ['hello', ' world']},
            {'type': 'chunk', 'chunk': {'type': 'reasoning-delta', 'text': 'secret'}}]}}})
    assert output == ['hello world']
    for revision, chunk in [(9, {'type': 'text-delta', 'index': 1, 'text': '!'}),
                             (10, {'type': 'tool-call-delta', 'text': 'private'})]:
        stream.accept({'type': 'assistant-stream', 'frame': {'type': 'chunk', 'revision': revision, 'chunk': chunk}})
    assert output[-1] == 'hello world!'
    stream.accept(record(5, 'turn/end', {}))
    stream.accept(record(6, 'user/message', {'source': {'rpcId': 'other'}}))
    stream.accept({'type': 'assistant-stream', 'frame': {'type': 'chunk', 'revision': 11,
        'chunk': {'type': 'text-delta', 'text': 'other user'}}})
    assert 'other user' not in ''.join(output)
    with pytest.raises(ValueError, match='revision gap'):
        stream.accept({'type': 'assistant-stream', 'frame': {'revision': 13}})


def test_queued_cancel_and_late_delta_are_scoped(tmp_path):
    db = tmp_path/'messages.sqlite3'; initialize(db)
    first = add_message(db, 'hermes', 'hello', conversation_id='one', delivery='queued')['id']
    second = add_message(db, 'hermes', 'other', conversation_id='two', delivery='queued')['id']
    worker = HermesWorker(db, hermes_home=tmp_path, api_client=object())
    worker.enqueue(first, 'hello'); worker.enqueue(second, 'other')
    worker._current_message_id = first
    with worker._lock: worker._task_locked(first, state='running')
    worker._publish(first, 'part')
    worker._publish(second, 'must not appear')
    assert worker.cancel(first)
    worker._publish(first, 'late part')
    assert worker.progress_snapshot('one')[0]['text'] == 'part'
    assert worker.progress_snapshot('two')[0]['text'] == ''
    assert worker.cancel(second)
    assert worker.progress_snapshot('two')[0]['state'] == 'interrupted'
    assert not worker.cancel(second)


def test_theme_persistence_auth_origin_validation_and_reconnect(tmp_path):
    app = create_app(tmp_path, token='test-access-token')
    client = TestClient(app, base_url='http://127.0.0.1')
    assert client.post('/api/device/theme', json={'theme': 'qiuqiu'}).status_code == 401
    client.post('/api/login', json={'token': 'test-access-token'})
    assert client.post('/api/device/theme', json={'theme': 'qiuqiu'}, headers={'origin':'https://bad.test'}).status_code == 403
    assert client.post('/api/device/theme', json={'theme': 'invalid'}).status_code == 422
    assert client.post('/api/device/theme', json={'theme': 'original'}).status_code == 422
    assert client.post('/api/device/theme', json={'theme': 'qiuqiu'}).status_code == 200
    device = create_app(tmp_path, token='test-access-token').state.device
    port = io.BytesIO()
    assert device._send_pending_theme(port, 1) == 1  # Offline selection is retained.
    device._handle(Frame(HELLO, 0, b'{"protocol":1,"firmware":"voice-device-1.9"}'), port, 1)
    device._send_pending_theme(port, 2)
    assert FrameParser().feed(port.getvalue())[-1] == Frame(THEME, 2, b'\x01')
    port = io.BytesIO()
    device._handle(Frame(HELLO, 0, b'{"protocol":1}'), port, 3)
    device._send_pending_theme(port, 4)
    assert FrameParser().feed(port.getvalue())[-1] == Frame(THEME, 4, b'\x01')
    with pytest.raises(ValueError): device.set_theme(0)
    assert device.snapshot()['desired_theme'] == 1
    with pytest.raises(ValueError): device.set_theme(3)
    from bridge.app.storage import set_setting, get_setting
    database = tmp_path / 'messages.sqlite3'
    set_setting(database, 'display_theme', 'original')
    upgraded = create_app(tmp_path, token='test-access-token').state.device
    assert upgraded.snapshot()['desired_theme'] == 1
    assert get_setting(database, 'display_theme') == 'qiuqiu'


def test_stop_api_cannot_cancel_a_different_conversation_or_agent(tmp_path):
    app = create_app(tmp_path, token='test-access-token')
    db = tmp_path/'messages.sqlite3'
    mid = add_message(db, 'hermes', 'hello', conversation_id='one', delivery='queued')['id']
    app.state.hermes.api_client = object()
    app.state.hermes.enqueue(mid, 'hello')
    client = TestClient(app, base_url='http://127.0.0.1')
    body = {'source': 'hermes', 'session_id':'one', 'message_id':mid}
    assert client.post('/api/messages/stop', json=body).status_code == 401
    client.post('/api/login', json={'token':'test-access-token'})
    assert client.post('/api/messages/stop', json={**body,'session_id':'two'}).status_code == 404
    assert client.post('/api/messages/stop', json={**body,'source':'deepseek_harness'}).status_code == 404
    assert client.post('/api/messages/stop', json=body, headers={'origin':'https://bad.test'}).status_code == 403
    assert client.post('/api/messages/stop', json=body).json()['accepted']
    assert client.get('/api/tasks?source=hermes&session_id=one').json()['items'][0]['state'] == 'interrupted'
    assert client.get('/api/tasks?source=hermes&session_id=two').json()['items'] == []


def test_hermes_sse_deduplicates_and_excludes_non_text(tmp_path):
    key=tmp_path/'key'; key.write_text('x'*32)
    client=HermesRunsClient(key)
    events=[{'seq':1,'event':'message.delta','delta':'Hello'},
            {'seq':1,'event':'message.delta','delta':'duplicate'},
            {'seq':2,'event':'reasoning.delta','delta':'private'},
            {'seq':3,'event':'message.delta','delta':' world'}]
    class Response(io.BytesIO):
        pass
    class Opener:
        def open(self, req, timeout):
            assert req.get_header('Last-event-id') == '-1'
            return Response(''.join('data: '+json.dumps(e)+'\n\n' for e in events).encode())
    client._opener=Opener(); output=[]
    client.follow_text('run_'+'a'*32,output.append,threading.Event())
    assert output == ['Hello','Hello world']


@pytest.mark.parametrize('queued', [True, False])
def test_harness_cancel_removes_own_queue_or_waits_for_own_turn_end(tmp_path, monkeypatch, queued):
    db=tmp_path/'messages.sqlite3'; initialize(db)
    class Client:
        installed=True
        exe=tmp_path/'harness.exe'
        calls=[]
        def rpc(self, method, body=None):
            self.calls.append((method,body))
            if method=='session/prompt': self.request=body['requestId']; worker._cancelled.add(1); return {}
            if method=='session/projections':
                return {'asOfSeq':5 if hasattr(self,'request') else 0,
                        'values':{'inbox':{'next-turn':[{'id':'our-item','source':{'rpcId':self.request}}] if queued and hasattr(self,'request') else []}}}
            if method=='session/page':
                records=[record(1,'user/message',{'source':{'rpcId':self.request}})]
                if hasattr(self,'cancelled'): records.append(record(5,'turn/end',{'reason':{'kind':'cancelled'}}))
                return {'records':records}
            if method=='session/cancel': self.cancelled=True
            return {}
    client=Client(); worker=HarnessWorker(db,tmp_path,client=client); worker._current_message_id=1
    monkeypatch.setattr('bridge.app.harness.time.sleep',lambda _:None)
    with pytest.raises(RuntimeError, match='取消|停止'):
        worker._ask('hello','test')
    methods=[c[0] for c in client.calls]
    assert ('session/updateQueue' in methods) == queued
    assert ('session/cancel' in methods) != queued


def test_unconfirmed_remote_stop_is_not_reported_as_success_or_spoken(tmp_path):
    db=tmp_path/'messages.sqlite3'; initialize(db)
    mid=add_message(db,'hermes','hello',delivery='queued')['id']
    entered,release=threading.Event(),threading.Event()
    replies=[]
    worker=HermesWorker(db,hermes_home=tmp_path,api_client=object(),on_reply=lambda *args:replies.append(args))
    def ask(*args):
        entered.set(); release.wait(2)
        raise CancellationUnconfirmed('Remote stop unconfirmed')
    worker._ask=ask
    worker.enqueue(mid,'hello'); worker.start()
    try:
        assert entered.wait(2)
        assert worker.cancel(mid)
        release.set()
        deadline=time.monotonic()+2
        while time.monotonic()<deadline and worker.progress_snapshot(None)[0]['state']!='stop_failed':
            time.sleep(.01)
        assert worker.progress_snapshot(None)[0]['state']=='stop_failed'
        assert replies==[]
    finally:
        release.set(); worker.stop()


def test_voice_cancel_suppresses_late_reply_but_does_not_cancel_other_agent(tmp_path):
    from bridge.app.voice import VoiceConversation
    db=tmp_path/'messages.sqlite3'; initialize(db)
    worker=HermesWorker(db,hermes_home=tmp_path,api_client=object())
    voice=VoiceConversation(db,tmp_path,DeviceLink(),worker)
    voice._message_id=7; voice._message_source='hermes'; voice._state='waiting_for_agent'
    voice.on_answer_cancelled(7,'deepseek_harness')
    assert voice._message_id==7
    voice.on_answer_cancelled(7,'hermes')
    voice.on_reply(7,'Late answer')
    assert voice._message_id is None
    assert voice._jobs.empty()


def test_session_metadata_is_saved_before_completed_reply_becomes_visible(tmp_path, monkeypatch):
    from bridge.app.storage import get_setting
    db=tmp_path/'messages.sqlite3'; initialize(db)
    mid=add_message(db,'hermes','hello',delivery='queued')['id']
    worker=HermesWorker(db,hermes_home=tmp_path,api_client=object())
    observed=[]; done=threading.Event()
    def ask(*args):
        worker._last_run_session='settled-session'
        return 'answer'
    def publish(*args,**kwargs):
        observed.append(get_setting(db,'hermes_session_id'))
        result=add_message(*args,**kwargs); done.set(); return result
    worker._ask=ask
    monkeypatch.setattr('bridge.app.hermes.add_message',publish)
    worker.enqueue(mid,'hello'); worker.start()
    try:
        assert done.wait(2)
        assert observed==['settled-session']
    finally: worker.stop()
