import time
import threading

from bridge.app import faces
from bridge.app.device import DeviceLink
from bridge.app.hermes import HermesWorker
from bridge.app.protocol import BUTTON, Frame
from bridge.app.storage import add_message, initialize, list_messages
from bridge.app.voice import VoiceConversation


class FakeHermes:
    def __init__(self):
        self.jobs = []
        self.cancelled = []
        self.approval = None
        self.decisions = []

    def enqueue(self, message_id, text, *, new_session=False):
        self.jobs.append((message_id, text, new_session))
        return True

    def cancel(self, message_id):
        self.cancelled.append(message_id)

    def pending_approval(self):
        return self.approval

    def approve(self, request_id, choice):
        if not self.approval or self.approval["request_id"] != request_id:
            return False
        self.decisions.append((request_id, choice))
        self.approval = None
        return True


class FakeDevice:
    def __init__(self):
        self.generation = 0
        self.audio = []
        self.faces = []

    def stop_playback(self):
        self.generation += 1
        return self.generation

    def set_face(self, face):
        self.faces.append(face)

    def is_current_generation(self, generation):
        return generation == self.generation

    def append_wav(self, wav, *, generation):
        if not self.is_current_generation(generation):
            return False
        self.audio.append(wav)
        return True

    def finish_playback(self, generation):
        pass


def test_muted_voice_still_sends_text_and_does_not_replay_old_queue(tmp_path, monkeypatch):
    database = tmp_path / "messages.sqlite3"
    initialize(database)
    device, hermes = FakeDevice(), FakeHermes()
    voice = VoiceConversation(database, tmp_path, device, hermes)
    monkeypatch.setattr("bridge.app.voice.synthesize_chunks", lambda text, _dir, cancelled: [text.encode()])
    voice.on_listen_start(1)
    voice.on_transcript("你好", 1)
    message_id = hermes.jobs[-1][0]
    voice.on_reply(message_id, "旧回复")
    voice.audio_output.update(muted=True)
    voice.on_output_muted()
    voice.on_reply(message_id, "静音回复")
    assert voice.snapshot()["state"] == "text_only"
    voice.audio_output.update(muted=False)
    voice.start()
    voice.on_reply(message_id, "新回复")
    try:
        deadline = time.monotonic() + 1
        while not device.audio and time.monotonic() < deadline:
            time.sleep(0.01)
        assert device.audio == ["新回复".encode()]
    finally:
        voice.stop()


def routed_voice(tmp_path):
    database = tmp_path / 'messages.sqlite3'
    initialize(database)
    hermes, harness, device = FakeHermes(), FakeHermes(), FakeDevice()
    voice = VoiceConversation(database, tmp_path, device, hermes,
        workers={'hermes': hermes, 'deepseek_harness': harness})
    return voice, hermes, harness, device


def test_harness_capture_freezes_target_and_automatically_reads_its_reply(tmp_path, monkeypatch):
    voice, hermes, harness, device = routed_voice(tmp_path)
    voice.set_target('deepseek_harness', 'harness-session')
    voice.on_listen_start(1)
    voice.set_target('hermes', 'other-session')
    voice.on_transcript('发给Harness', 1)
    assert hermes.jobs == []
    message_id = harness.jobs[0][0]
    import sqlite3
    with sqlite3.connect(voice.database) as db:
        assert db.execute('SELECT source,conversation_id,input_method FROM messages WHERE id=?',
                          (message_id,)).fetchone() == ('deepseek_harness', 'harness-session', 'voice')
    monkeypatch.setattr('bridge.app.voice.synthesize_chunks', lambda text, _dir, cancelled: [text.encode()])
    voice.on_reply(message_id, '错误来源')
    assert voice.snapshot()['state'] == 'waiting_for_agent'
    voice.on_reply(message_id, 'Harness回答', source='deepseek_harness')
    voice.start()
    try:
        deadline = time.monotonic() + 1
        while not device.audio and time.monotonic() < deadline:
            time.sleep(.01)
        assert device.audio == ['Harness回答'.encode()]
    finally:
        voice.stop()


def test_next_recording_cancels_original_agent_and_ignores_late_reply(tmp_path):
    voice, hermes, harness, _ = routed_voice(tmp_path)
    voice.set_target('deepseek_harness', 'harness-session')
    voice.on_listen_start(1)
    voice.on_transcript('旧任务', 1)
    old_id = harness.jobs[0][0]
    voice.set_target('hermes', 'hermes-session')
    voice.on_listen_start(2)
    assert harness.cancelled == [old_id]
    assert hermes.cancelled == []
    voice.on_transcript('过期转写', 1)
    voice.on_reply(old_id, '迟到回答', source='deepseek_harness')
    assert voice._jobs.empty()
    voice.on_transcript('新任务', 2)
    assert hermes.jobs[0][1] == '新任务'


def test_harness_selection_cannot_approve_other_hermes_session(tmp_path):
    voice, hermes, harness, _ = routed_voice(tmp_path)
    hermes.approval = {'request_id': 'secret-approval', 'conversation_id': 'hermes-session'}
    voice.set_target('deepseek_harness', 'harness-session')
    voice.on_listen_start(1)
    voice.on_transcript('同意审批', 1)
    assert hermes.decisions == []
    assert harness.jobs[0][1] == '同意审批'
    voice.set_target('hermes', 'different-hermes-session')
    voice.on_listen_start(2)
    voice.on_transcript('同意审批', 2)
    assert hermes.decisions == []


def test_unsupported_or_missing_session_never_falls_back_to_hermes(tmp_path):
    voice, hermes, harness, _ = routed_voice(tmp_path)
    for generation, source in enumerate(['doubao_web', 'deepseek_harness'], start=1):
        voice.set_target(source, None)
        voice.on_listen_start(generation)
        voice.on_transcript('你好', generation)
        assert voice.snapshot()['state'] == 'error'
    assert not hermes.jobs and not harness.jobs


def test_harness_mute_and_selected_route_survive_restart(tmp_path):
    voice, hermes, harness, device = routed_voice(tmp_path)
    voice.set_target('deepseek_harness', 'session-one')
    restored = VoiceConversation(voice.database, tmp_path, device, hermes,
        workers={'hermes': hermes, 'deepseek_harness': harness})
    assert restored.snapshot()['target'] == {'source': 'deepseek_harness', 'session_id': 'session-one'}
    restored.audio_output.update(muted=True)
    restored.on_listen_start(1)
    restored.on_transcript('静音测试', 1)
    restored.on_reply(harness.jobs[-1][0], '仅文字', source='deepseek_harness')
    assert restored.snapshot()['state'] == 'text_only'
    assert restored._jobs.empty()


def test_voice_turn_queues_hermes_and_reads_only_current_reply(tmp_path, monkeypatch):
    database = tmp_path / "messages.sqlite3"
    initialize(database)
    hermes = FakeHermes()
    device = FakeDevice()
    voice = VoiceConversation(database, tmp_path, device, hermes)
    monkeypatch.setattr("bridge.app.voice.synthesize_chunks", lambda text, _dir, cancelled: [text.encode()])

    voice.on_listen_start(1)
    voice.on_transcript("第一轮", 1)
    first_id = hermes.jobs[-1][0]
    voice.on_listen_start(2)
    assert hermes.cancelled == [first_id]
    voice.on_transcript("迟到的识别", 1)
    voice.on_transcript("第二轮", 2)
    second_id = hermes.jobs[-1][0]
    voice.on_reply(first_id, "旧回复")
    voice.on_reply(second_id, "新回复")
    voice.start()
    try:
        deadline = time.monotonic() + 1
        while not device.audio and time.monotonic() < deadline:
            time.sleep(0.01)
        assert device.audio == ["新回复".encode()]
        assert voice.snapshot()["state"] == "sent_to_device"
        assert [(item["text"], item["input_method"]) for item in list_messages(database, "hermes")] == [
            ("第一轮", "voice"), ("第二轮", "voice")]
    finally:
        voice.stop()


def test_button_start_invalidates_previous_voice_reply():
    starts = []
    captures = []
    device = DeviceLink(lambda wav, generation: captures.append(generation), starts.append)
    device._handle(Frame(BUTTON, 1, b"\x01"), None, 0)
    device._handle(Frame(BUTTON, 2, b"\x00"), None, 0)
    device._handle(Frame(BUTTON, 3, b"\x01"), None, 0)
    assert starts == [1, 2]
    assert captures == [1]  # Empty recording must also end recognition with an error.


def test_cancelled_hermes_turn_does_not_publish_late_reply(tmp_path):
    database = tmp_path / "messages.sqlite3"
    initialize(database)
    item = add_message(database, "hermes", "旧语音", delivery="queued", input_method="voice")
    worker = HermesWorker(database, hermes_home=tmp_path)
    worker.executable = "fake-hermes"
    entered = threading.Event()
    release = threading.Event()

    def slow_ask(_text, _session):
        entered.set()
        assert release.wait(1)
        return "迟到的回复"

    worker._ask = slow_ask
    worker.start()
    try:
        assert worker.enqueue(item["id"], item["text"])
        assert entered.wait(1)
        worker.cancel(item["id"])
        release.set()
        deadline = time.monotonic() + 1
        while list_messages(database, "hermes")[-1]["delivery"] != "interrupted" and time.monotonic() < deadline:
            time.sleep(0.01)
        rows = list_messages(database, "hermes")
        assert len(rows) == 1
        assert rows[0]["delivery"] == "interrupted"
    finally:
        release.set()
        worker.stop()


def test_voice_approval_requires_exact_phrase_and_keeps_original_turn(tmp_path):
    database = tmp_path / "messages.sqlite3"
    initialize(database)
    hermes = FakeHermes()
    voice = VoiceConversation(database, tmp_path, FakeDevice(), hermes)
    voice.on_listen_start(1)
    voice.on_transcript("请检查文件", 1)
    original_id = hermes.jobs[-1][0]
    hermes.approval = {"request_id": "approval-1", "command": "example", "description": "检查文件"}
    voice.on_listen_start(2)
    assert hermes.cancelled == []
    voice.on_transcript("同意执行", 2)
    assert hermes.decisions == []
    assert voice.snapshot()["state"] == "approval_pending"
    voice.on_listen_start(3)
    voice.on_transcript("同意审批。", 3)
    assert hermes.decisions == [("approval-1", "once")]
    assert hermes.jobs == [(original_id, "请检查文件", False)]
    assert voice.snapshot()["state"] == "waiting_for_hermes"


def test_voice_approval_can_deny(tmp_path):
    database = tmp_path / "messages.sqlite3"
    initialize(database)
    hermes = FakeHermes()
    hermes.approval = {"request_id": "approval-2"}
    device = FakeDevice()
    voice = VoiceConversation(database, tmp_path, device, hermes)
    voice.on_listen_start(1)
    voice.on_transcript("拒绝审批", 1)
    assert hermes.decisions == [("approval-2", "deny")]
    assert hermes.jobs == []
    # A denial is not a fault, but the robot should stop wearing the approval face.
    assert device.faces == [faces.READY]


def test_the_robot_wears_the_approval_face_until_the_user_decides(tmp_path):
    database = tmp_path / "messages.sqlite3"
    initialize(database)
    hermes = FakeHermes()
    device = FakeDevice()
    voice = VoiceConversation(database, tmp_path, device, hermes)
    voice.on_listen_start(1)
    voice.on_transcript("请检查文件", 1)
    message_id = hermes.jobs[-1][0]
    device.faces.clear()

    voice.on_approval(message_id, {"request_id": "a1", "description": "检查文件"})
    assert device.faces == [faces.APPROVE]

    voice.on_hermes_error(message_id, "Hermes 断线")
    assert device.faces == [faces.APPROVE, faces.ERROR]
