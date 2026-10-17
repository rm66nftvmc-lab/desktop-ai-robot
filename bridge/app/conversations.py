"""Native conversation catalogs and local drafts; no writes to agent databases."""

import json
import os
import sqlite3
import subprocess
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .storage import get_setting
from .process_utils import command_invocation


def message_route(database, message_id, fallback):
    with sqlite3.connect(database) as db:
        row = db.execute('SELECT conversation_id FROM messages WHERE id=?', (message_id,)).fetchone()
        conversation = row[0] if row else None
        if not conversation:
            return fallback, None
        draft = db.execute('SELECT native_id FROM conversations WHERE id=?', (conversation,)).fetchone()
        return (draft[0] if draft else conversation), conversation


def bind_draft(database, conversation, native_id):
    if conversation and native_id:
        with sqlite3.connect(database) as db:
            db.execute('UPDATE conversations SET native_id=? WHERE id=?', (native_id, conversation))


def text_content(content):
    if isinstance(content, str):
        try:
            parsed = json.loads(content)
        except (ValueError, TypeError):
            return content
        if not isinstance(parsed, list):
            return content
        content = parsed
    if isinstance(content, list):
        return '\n'.join(b.get('text', '') for b in content
                         if isinstance(b, dict) and b.get('type') == 'text')
    return ''


def iso_time(value):
    if isinstance(value, str):
        return value
    value = value or 0
    if value > 1e11:
        value /= 1000
    return datetime.fromtimestamp(value, timezone.utc).isoformat()


class Conversations:
    def __init__(self, database: Path, hermes, harness):
        self.database, self.hermes, self.harness = database, hermes, harness

    @staticmethod
    def check_source(source):
        if source not in {'hermes', 'deepseek_harness'}:
            raise ValueError('此目标不支持会话管理')

    def _native(self, source):
        if source == 'hermes':
            path = self.hermes.hermes_home / 'state.db'
            if not path.is_file():
                return []
            with sqlite3.connect(f'file:{path.as_posix()}?mode=ro', uri=True, timeout=2) as db:
                rows = db.execute("SELECT id,title,last_activity_at FROM sessions "
                    "WHERE COALESCE(archived,0)=0 AND COALESCE(hidden,0)=0 "
                    "AND COALESCE(parent_session_id,'')='' ORDER BY last_activity_at DESC LIMIT 200").fetchall()
            return [{'id': r[0], 'title': r[1] or '未命名会话', 'updated_at': r[2] or 0} for r in rows]
        values = self.harness.client.rpc('session/list')['items']
        return [{'id': s['sessionId'],
                 'title': s.get('projections', {}).get('values', {}).get('title') or '未命名会话',
                 'updated_at': (s.get('updatedAt') or 0) / 1000}
                for s in values if not s.get('projections', {}).get('values', {}).get('subagent')
                and not s.get('archived')]

    def catalog(self, source):
        self.check_source(source)
        native = self._native(source)
        with sqlite3.connect(self.database) as db:
            drafts = db.execute('SELECT id,native_id,title,created_at FROM conversations WHERE source=?',
                                (source,)).fetchall()
        aliases = {r[1]: r[0] for r in drafts if r[1]}
        items = [{**item, 'id': aliases.get(item['id'], item['id']), 'draft': False} for item in native]
        known = {item['id'] for item in items}
        items += [{'id': r[0], 'title': r[2], 'updated_at': r[3], 'draft': r[1] is None}
                  for r in drafts if r[0] not in known and r[1] is None]
        items.sort(key=lambda x: x['updated_at'], reverse=True)
        preferred = get_setting(self.database, source + '_session_id')
        preferred = aliases.get(preferred, preferred)
        if not preferred or not any(s['id'] == preferred for s in items):
            preferred = items[0]['id'] if items else None
        return {'items': items, 'active_id': preferred}

    def create(self, source):
        self.check_source(source)
        item = {'id': 'draft-' + uuid.uuid4().hex, 'title': '新对话',
                'updated_at': time.time(), 'draft': True}
        with sqlite3.connect(self.database) as db:
            db.execute('INSERT INTO conversations(id,source,title,created_at) VALUES(?,?,?,?)',
                       (item['id'], source, item['title'], item['updated_at']))
        return item

    def delete(self, source, conversation):
        """Delete one selected native session and its Bridge-side records."""
        self.check_source(source)
        worker = self.hermes if source == 'hermes' else self.harness
        worker_state = worker.snapshot()
        if worker_state.get('running') or worker_state.get('pending'):
            raise RuntimeError('请等待当前回复完成后再删除会话')

        with sqlite3.connect(self.database) as db:
            row = db.execute('SELECT source,native_id FROM conversations WHERE id=?',
                             (conversation,)).fetchone()
        if row and row[0] != source:
            raise ValueError('会话不属于当前智能体')
        native_id = self.resolve(source, conversation)
        if native_id:
            if source == 'hermes':
                executable = self.hermes.executable
                if not executable:
                    raise RuntimeError('Hermes 当前未安装，暂时无法删除原生会话')
                try:
                    invocation, options = command_invocation(
                        executable, ['sessions', 'delete', '--yes', native_id])
                    result = subprocess.run(
                        invocation,
                        capture_output=True, text=True, timeout=45,
                        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), **options)
                except (OSError, subprocess.TimeoutExpired) as exc:
                    raise RuntimeError('Hermes 删除会话请求未完成，请稍后重试') from exc
                if result.returncode != 0:
                    raise RuntimeError('Hermes 未能删除该会话，请确认 Hermes 服务可用后重试')
            else:
                self.harness.client.delete_session_permanently(native_id)

        with sqlite3.connect(self.database) as db:
            db.execute('DELETE FROM messages WHERE source=? AND conversation_id=?',
                       (source, conversation))
            db.execute('DELETE FROM conversations WHERE id=? AND source=?',
                       (conversation, source))
            db.execute('DELETE FROM settings WHERE key=? AND value=?',
                       (source + '_session_id', native_id or conversation))
        return {'deleted': True, 'source': source, 'session_id': conversation,
                'native_session_id': native_id, 'native_session_deleted': bool(native_id)}

    def resolve(self, source, conversation):
        self.check_source(source)
        with sqlite3.connect(self.database) as db:
            row = db.execute('SELECT source,native_id FROM conversations WHERE id=?', (conversation,)).fetchone()
        if row:
            if row[0] != source:
                raise ValueError('会话不属于当前智能体')
            if row[1] and not any(item['id'] == row[1] for item in self._native(source)):
                raise ValueError('会话不存在或已归档')
            return row[1]
        if any(item['id'] == conversation for item in self._native(source)):
            return conversation
        raise ValueError('会话不存在或已归档')

    def history(self, source, conversation):
        native_id = self.resolve(source, conversation)
        native = []
        if native_id and source == 'hermes':
            path = self.hermes.hermes_home / 'state.db'
            with sqlite3.connect(f'file:{path.as_posix()}?mode=ro', uri=True, timeout=2) as db:
                rows = db.execute("SELECT id,role,content,timestamp FROM messages WHERE session_id=? "
                    "AND role IN ('user','assistant') AND COALESCE(active,1)=1 ORDER BY id DESC LIMIT 200",
                    (native_id,)).fetchall()
            for row in reversed(rows):
                text = text_content(row[2])
                if text.strip():
                    native.append(self._item(source, f'native-{row[0]}', row[1], text, row[3]))
        elif native_id:
            state = self.harness.client.rpc('session/projections', {'sessionId': native_id})
            page = self.harness.client.rpc('session/page', {
                'address': {'kind': 'session', 'sessionId': native_id},
                'throughSeq': state['asOfSeq'], 'maxMessages': 200})
            for record in page['records']:
                e = record.get('event', {})
                d = e.get('data', {})
                if e.get('type') == 'user/message' and d.get('source', {}).get('kind') == 'user':
                    role, content = 'user', d.get('content')
                elif e.get('type') == 'assistant/message':
                    role, content = 'assistant', d.get('message', {}).get('content')
                else:
                    continue
                text = text_content(content)
                if text.strip():
                    native.append(self._item(source, f"native-{e['seq']}", role, text,
                                             e.get('timestamp') or e.get('time') or e.get('at')))
        with sqlite3.connect(self.database) as db:
            db.row_factory = sqlite3.Row
            local = [dict(r) for r in db.execute('SELECT * FROM messages WHERE source=? AND conversation_id=? ORDER BY id',
                                               (source, conversation))]
        if not native:
            return local
        # Native history already includes admitted messages. Keep only unsent or
        # failed local entries; match admitted pending text to avoid duplicates.
        texts = [item['text'] for item in native if item['role'] == 'user']
        pending = [item for item in local if item['role'] == 'user' and item['delivery'] != 'completed'
                   and (item['delivery'] in {'failed', 'interrupted'} or not texts or item['text'] != texts[-1])]
        return native + pending

    @staticmethod
    def _item(source, identity, role, text, timestamp):
        return {'id': identity, 'source': source, 'role': role, 'text': text,
                'created_at': iso_time(timestamp), 'delivery': 'completed',
                'input_method': 'text', 'reply_to': None}
