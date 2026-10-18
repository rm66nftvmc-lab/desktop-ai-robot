"""Adapter to the installed DeepSeek Harness runtime and its durable sessions."""

import copy
import http.cookiejar
import json
import os
import re
import socket
import subprocess
import time
import threading
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from threading import RLock

import yaml

from .hermes import HermesWorker
from .storage import get_setting, deleted_session_ids
from .answer_stream import HarnessTextStream, CancellationUnconfirmed

BASE = "http://127.0.0.1:3081"


def request_turn(records, request_id, baseline):
    active = False
    ended = False
    for record in records:
        event = record.get('event', {})
        if event.get('seq', -1) <= baseline:
            continue
        data = event.get('data', {})
        if event.get('type') == 'user/message' and data.get('source', {}).get('kind', 'user') == 'user':
            active = data.get('source', {}).get('rpcId') == request_id
        elif event.get('type') == 'turn/end' and active:
            active, ended = False, True
    return active, ended


def completed_reply(records, request_id, baseline):
    admitted = False
    answer = None
    for record in records:
        event = record.get('event', {})
        if event.get('seq', -1) <= baseline:
            continue
        data = event.get('data', {})
        if event.get('type') == 'user/message' and data.get('source', {}).get('kind', 'user') == 'user':
            admitted = data.get('source', {}).get('rpcId') == request_id
            answer = None
        if not admitted:
            continue
        if event.get('type') == 'assistant/message':
            text = ''.join(block.get('text', '') for block in data.get('message', {}).get('content', [])
                           if block.get('type') == 'text')
            if text.strip():
                answer = text.strip()
        if event.get('type') == 'turn/end':
            reason = data.get('reason', {})
            if reason.get('kind') != 'completed':
                raise RuntimeError('Harness 本轮未完成：' + str(reason.get('kind', 'unknown')))
            if answer:
                return answer
    return None


def backend_overlay(path: Path) -> list:
    # Desktop uses YAML 1.2: keys such as reasoning effort 'off' are strings.
    class Loader(yaml.SafeLoader):
        pass
    Loader.yaml_implicit_resolvers = copy.deepcopy(Loader.yaml_implicit_resolvers)
    for key, values in Loader.yaml_implicit_resolvers.items():
        Loader.yaml_implicit_resolvers[key] = [
            (tag, rx) for tag, rx in values if tag != 'tag:yaml.org,2002:bool']
    Loader.add_implicit_resolver('tag:yaml.org,2002:bool',
                                re.compile(r'^(?:true|false|True|False)$'), list('tTfF'))
    entries = yaml.load(path.read_text(encoding='utf-8'), Loader=Loader)
    return [entry for entry in entries if entry.get('id') in {'agent-default-model', 'llm-pi-ai'}]


class HarnessClient:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.exe = Path(os.environ.get('ROBOT_HARNESS_EXE',
                                      r'D:\deepseek harness桌面端\DeepSeek Harness.exe'))
        self._process = None
        self._lock = RLock()
        self._opener = None

    @property
    def installed(self):
        return self.exe.is_file()

    def start(self):
        if not self.installed:
            return
        if self._process and self._process.poll() is None:
            return
        try:
            with socket.create_connection(('127.0.0.1', 3081), timeout=0.3):
                return
        except OSError:
            pass
        self.data_dir.mkdir(parents=True, exist_ok=True)
        overlay = self.data_dir / 'harness-bridge.patch.yml'
        entries = backend_overlay(Path.home() / '.dsh/profiles/desktop/cordis.patch.yml')
        temporary = overlay.with_suffix('.yml.tmp')
        temporary.write_text(yaml.safe_dump(entries, allow_unicode=True), encoding='utf-8')
        temporary.replace(overlay)
        args = [str(self.exe), '--expose-internals',
                str(self.exe.parent / 'resources/app.asar/dsh/node_modules/@deepseek-ai/dsh-desktop-host/lib/cli.js'),
                '--profile', 'web', '--patch', str(overlay), '--no-open',
                '--host', '127.0.0.1', '--port', '3081']
        with (self.data_dir / 'harness-bridge.log').open('ab') as log:
            self._process = subprocess.Popen(
                args, env={**os.environ, 'ELECTRON_RUN_AS_NODE': '1'},
                cwd=Path(__file__).resolve().parents[2], stdout=log, stderr=log,
                stdin=subprocess.DEVNULL, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))

    def stop(self):
        if self._process and self._process.poll() is None:
            self._process.terminate()

    def _login(self):
        log = (self.data_dir / 'harness-bridge.log').read_text(encoding='utf-8', errors='replace')
        tokens = re.findall(r'http://127\.0\.0\.1:3081/\?token=([^\s]+)', log)
        if not tokens:
            raise RuntimeError('Harness 本地服务尚未启动完成')
        self._opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}),
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        with self._opener.open(BASE + '/?token=' + tokens[-1], timeout=10) as response:
            response.read(1)

    def rpc(self, method, request=None):
        with self._lock:
            self.start()
            if self._opener is None:
                self._login()
            field = '_request' if method == 'session/list' else 'request'
            body = {'type': 'client-request', 'rpcId': str(uuid.uuid4()),
                    'method': method, 'payload': {'args': {field: request or {}}}}
            req = urllib.request.Request(BASE + '/api/' + method,
                data=json.dumps(body).encode(), headers={
                    'Content-Type': 'application/json', 'Origin': BASE})
            try:
                with self._open_authenticated(req) as response:
                    result = json.loads(response.read())['result']
            except urllib.error.HTTPError as exc:
                if exc.code == 401:
                    self._opener = None
                raise RuntimeError(f'Harness 本地接口请求失败（HTTP {exc.code}）') from exc
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                self._opener = None
                raise RuntimeError('Harness 连接中断；本次请求不会自动重发，请核对会话后重试') from exc
            if not result['ok']:
                error = result.get('error', {})
                if error.get('code') == 'session/writer-held':
                    raise RuntimeError('原会话正被 Harness 桌面端占用；请退出桌面端后继续，或明确选择新建会话')
                raise RuntimeError(f"Harness {error.get('code', 'error')}: {error.get('message', '')}")
            return result.get('value')

    def _open_authenticated(self, request):
        # A 401 proves the request was rejected before execution. Refresh the
        # cookie once; never retry timeouts or ambiguous failed writes.
        try:
            return self._opener.open(request, timeout=20)
        except urllib.error.HTTPError as exc:
            if exc.code != 401:
                raise
            exc.close()
            self._opener = None
            self._login()
            return self._opener.open(request, timeout=20)

    def follow_text(self, session, request_id, baseline, publish, stopped):
        from websockets.sync.client import connect
        while not stopped.is_set():
            try:
                with self._lock:
                    if self._opener is None:
                        self._login()
                    request = urllib.request.Request(BASE + '/')
                    for handler in self._opener.handlers:
                        if isinstance(handler, urllib.request.HTTPCookieProcessor):
                            handler.cookiejar.add_cookie_header(request)
                    cookie = request.get_header('Cookie', '')
                parser = HarnessTextStream(request_id, baseline, publish)
                with connect('ws://127.0.0.1:3081/api/remote.mux', origin=BASE,
                             additional_headers={'Cookie': cookie}, proxy=None,
                             open_timeout=3, close_timeout=.2, max_size=8*1024*1024) as connection:
                    identity = uuid.uuid4().hex
                    connection.send(json.dumps({'type': 'open', 'streamId': identity, 'endpoint': 'session/follow',
                        'payload': {'args': {'request': {'address': {'kind': 'session', 'sessionId': session},
                            'maxMessages': 100, 'assistantStream': True}}}}))
                    while not stopped.is_set():
                        try:
                            message = json.loads(connection.recv(timeout=.5))
                        except TimeoutError:
                            continue
                        if message.get('streamId') != identity:
                            continue
                        if message.get('type') == 'item':
                            parser.accept(message.get('value', {}))
                        elif message.get('type') in {'end', 'error'}:
                            return
            except Exception:
                # Read-only reconnect: the next opening snapshot reconstructs
                # text; never replay session/prompt on a stream failure.
                stopped.wait(.5)
    def _plugin_post(self, path, payload):
        """POST to an authenticated host plugin route using the Harness cookie."""
        with self._lock:
            self.start()
            if self._opener is None:
                self._login()
            req = urllib.request.Request(BASE + path,
                data=json.dumps(payload).encode(), headers={
                    'Content-Type': 'application/json', 'Origin': BASE})
            try:
                with self._open_authenticated(req) as response:
                    envelope = json.loads(response.read())
            except urllib.error.HTTPError as exc:
                if exc.code == 401:
                    self._opener = None
                try:
                    envelope = json.loads(exc.read())
                except (ValueError, TypeError):
                    if exc.code == 404:
                        raise RuntimeError(
                            'Harness 永久删除扩展尚未加载（HTTP 404）；未归档，会话未删除。'
                            '请运行 scripts\\install_dsh_plugin.ps1 安装仓库内附带的插件，'
                            '然后重启 Bridge。'
                        ) from exc
                    raise RuntimeError(f'Harness 删除接口请求失败（HTTP {exc.code}）') from exc
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                raise RuntimeError('无法连接 Harness 本地删除接口；会话未确认删除') from exc

            if not isinstance(envelope, dict) or envelope.get('ok') is not True:
                error = envelope.get('error', {}) if isinstance(envelope, dict) else {}
                code = error.get('code', 'error') if isinstance(error, dict) else 'error'
                message = error.get('message', '') if isinstance(error, dict) else ''
                if code == 'session-open':
                    raise RuntimeError('这个会话仍被 Harness 占用，暂时无法安全删除；请等回复完成后重试。')
                if code == 'session-not-found':
                    raise RuntimeError('Harness 中找不到这个会话，它可能已被删除。')
                if code == 'unsafe-target':
                    raise RuntimeError('Harness 拒绝删除这个会话，因为其本地存储路径未通过安全校验。')
                raise RuntimeError(f'Harness 删除接口失败（{code}）：{message or "未提供错误详情"}')
            value = envelope.get('value')
            if not isinstance(value, dict):
                raise RuntimeError('Harness 删除接口返回了无法识别的结果')
            return value

    def delete_session_permanently(self, session_id):
        """Delete a session through the host plugin and immediately purge its staging move."""
        removed = self._plugin_post('/api/session.delete', {'sessionId': session_id})
        if removed.get('sessionId') != session_id:
            raise RuntimeError('Harness 删除接口未确认目标会话；会话未确认删除')

        try:
            purged = self._plugin_post('/api/session.purge', {'sessionId': session_id})
            if session_id not in purged.get('purged', []):
                raise RuntimeError('Harness 未确认已永久清除目标会话')
        except Exception as purge_error:
            try:
                restored = self._plugin_post('/api/session.restore', {'sessionId': session_id})
                if restored.get('sessionId') != session_id:
                    raise RuntimeError('恢复接口未确认目标会话')
            except Exception as restore_error:
                raise RuntimeError(
                    '永久删除未完成，且会话未能自动恢复；请暂时不要重复操作并检查 Harness 会话列表。'
                ) from restore_error
            raise RuntimeError(f'永久删除失败，已将会话恢复到列表：{purge_error}') from purge_error
        return {'session_id': session_id, 'permanently_deleted': True}


class HarnessWorker(HermesWorker):
    source = 'deepseek_harness'
    session_setting = 'deepseek_harness_session_id'

    def __init__(self, database: Path, data_dir: Path, client=None):
        super().__init__(database)
        self.client = client or HarnessClient(data_dir)
        self.executable = str(self.client.exe) if self.client.installed else None
        self._sessions = []
        self._checked_at = 0
        self._available = False

    def _refresh(self):
        if time.monotonic() - self._checked_at < 3:
            return
        self._checked_at = time.monotonic()
        try:
            self._sessions = self.client.rpc('session/list')['items']
            removed = deleted_session_ids(self.database, self.source)
            self._sessions = [item for item in self._sessions if item['sessionId'] not in removed]
            self._available = True
        except (OSError, RuntimeError, ValueError, KeyError):
            self._available = False

    def _preferred_session_info(self):
        self._refresh()
        selected = get_setting(self.database, self.session_setting)
        candidates = [s for s in self._sessions if not s.get('blank')
                      and not s.get('projections', {}).get('values', {}).get('subagent')
                      and not s.get('archived')]
        # The runtime lists top-level sessions; preserve the latest desktop work.
        candidates.sort(key=lambda s: s.get('updatedAt', 0), reverse=True)
        current = candidates[0] if candidates else None
        saved = next((s for s in candidates if s['sessionId'] == selected), None)
        if saved and (not current or saved.get('updatedAt', 0) >= current.get('updatedAt', 0)):
            current = saved
        if not current:
            return None
        return {'id': current['sessionId'], 'title': 'DeepSeek Harness 最近会话',
                'last_activity_at': current.get('updatedAt', 0)}

    def snapshot(self):
        result = super().snapshot()
        result.update(available=self._available, mode='harness-local-api',
                      running=self._current_message_id is not None)
        return result

    def _ask(self, text, session):
        if session:
            state = self.client.rpc('session/projections', {'sessionId': session})
            baseline = state['asOfSeq']
        else:
            session = self.client.rpc('session/create', {})['sessionId']
            baseline = -1
        self._last_run_session = session
        request_id = str(uuid.uuid4())
        with self._lock:
            message_id = self._current_message_id
            if message_id in self._cancelled:
                raise RuntimeError('Harness 请求在发送前已取消')
        self.client.rpc('session/prompt', {'sessionId': session, 'requestId': request_id,
            'content': [{'type': 'text', 'text': text}], 'mode': 'queue',
            'clientTimeZone': 'Asia/Shanghai'})
        deadline = time.monotonic() + 300
        stopped = threading.Event()
        follower = None
        if hasattr(self.client, 'follow_text'):
            follower = threading.Thread(target=self.client.follow_text,
                args=(session, request_id, baseline, lambda value: self._publish(message_id, value), stopped), daemon=True)
            follower.start()
        cancel_sent = False
        terminal = False
        try:
            while time.monotonic() < deadline:
                with self._lock:
                    cancelled = self._stop.is_set() or message_id in self._cancelled
                state = self.client.rpc('session/projections', {'sessionId': session})
                page = self.client.rpc('session/page', {
                    'address': {'kind': 'session', 'sessionId': session},
                    'throughSeq': state['asOfSeq'], 'maxMessages': 100}) if state['asOfSeq'] > baseline else {'records': []}
                active, terminal = request_turn(page['records'], request_id, baseline)
                if cancelled and not cancel_sent:
                    inbox = state.get('values', {}).get('inbox', {})
                    pending = next((item for kind in ('next-turn', 'next-step') for item in inbox.get(kind, [])
                                    if item.get('source', {}).get('rpcId') == request_id), None)
                    if pending:
                        try:
                            self.client.rpc('session/updateQueue', {'sessionId': session, 'itemId': pending['id'],
                                                                   'action': {'kind': 'remove'}})
                        except RuntimeError as exc:
                            if 'queue-item-not-found' in str(exc):
                                continue  # Claimed concurrently: re-read ownership before cancelling.
                            raise
                        terminal = True
                        raise RuntimeError('Harness 排队请求已取消')
                    if active:
                        self.client.rpc('session/cancel', {'sessionId': session})
                        cancel_sent = True
                    elif terminal:
                        raise RuntimeError('Harness 请求已结束')
                if cancelled and terminal:
                    raise RuntimeError('Harness 请求已停止')
                answer = completed_reply(page['records'], request_id, baseline)
                if answer:
                    return answer
                time.sleep(.5)
            raise RuntimeError('Harness 回复超时；请在 Harness 本地界面检查任务状态')
        except Exception as exc:
            with self._lock:
                cancelled = message_id in self._cancelled
            if cancelled and not terminal:
                raise CancellationUnconfirmed('未能确认 Harness 已停止，任务可能仍在运行，请在 Harness 中检查') from exc
            raise
        finally:
            stopped.set()
            if follower:
                follower.join(timeout=.1)
