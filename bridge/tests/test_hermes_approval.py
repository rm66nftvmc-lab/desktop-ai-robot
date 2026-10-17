import threading
import time

from bridge.app.hermes import HermesWorker
from bridge.app.storage import add_message, get_setting, initialize, list_messages


class FakeRunsAPI:
    def __init__(self):
        self.approved = threading.Event()
        self.started = []
        self.decisions = []

    def start_run(self, text, session):
        self.started.append((text, session))
        return "run_" + "a" * 32

    def status(self, run_id):
        if not self.approved.is_set():
            return {"status": "waiting_for_approval", "approval": {
                "request_id": "request-1", "command": "echo hello", "description": "运行测试命令"}}
        return {"status": "completed", "output": "操作完成", "session_id": "run_" + "a" * 32}

    def approve(self, run_id, request_id, choice):
        self.decisions.append((run_id, request_id, choice))
        self.approved.set()

    def stop(self, run_id):
        self.approved.set()


def test_run_waits_for_one_time_approval_and_records_reply(tmp_path):
    database = tmp_path / "messages.sqlite3"
    initialize(database)
    api = FakeRunsAPI()
    worker = HermesWorker(database, hermes_home=tmp_path, api_client=api)
    seen = []
    worker.on_approval = lambda message_id, pending: seen.append((message_id, pending))
    item = add_message(database, "hermes", "请检查", delivery="queued")
    worker.start()
    try:
        assert worker.enqueue(item["id"], item["text"])
        deadline = time.monotonic() + 2
        while worker.pending_approval() is None and time.monotonic() < deadline:
            time.sleep(0.01)
        pending = worker.pending_approval()
        assert pending and pending["command"] == "echo hello"
        assert seen[0][0] == item["id"]
        assert worker.approve("wrong-request", "once") is False
        assert api.decisions == []
        assert worker.approve("request-1", "once") is True
        while list_messages(database, "hermes")[-1]["delivery"] != "completed" and time.monotonic() < deadline:
            time.sleep(0.01)
        rows = list_messages(database, "hermes")
        assert [row["text"] for row in rows] == ["请检查", "操作完成"]
        assert api.decisions[0][2] == "once"
        assert worker.pending_approval() is None
        assert get_setting(database, "hermes_session_id") == "run_" + "a" * 32
    finally:
        worker.stop()
