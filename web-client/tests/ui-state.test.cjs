const test = require('node:test');
const assert = require('node:assert/strict');
const ui = require('../ui-state.js');

test('partial deletion retains failed and unconfirmed selections', () => {
  const items = [{ id: 'a' }, { id: 'b' }, { id: 'c' }];
  const result = ui.deletionOutcome(items, {
    deleted: [{ session_id: 'a' }], failed: [{ session_id: 'b', error: 'busy' }],
  });
  assert.deepEqual(result.deleted, [items[0]]);
  assert.deepEqual(result.failed.map((item) => item.session_id), ['b', 'c']);
  assert.equal(result.failed[0].error, 'busy');
  assert.match(result.failed[1].error, /未确认/);
});

test('touch navigation opens only from left quarter and ignores scrolling', () => {
  assert.equal(ui.swipe({ x: 40, y: 100, open: false }, { x: 140, y: 105 }, 400), true);
  assert.equal(ui.swipe({ x: 110, y: 100, open: false }, { x: 230, y: 105 }, 400), null);
  assert.equal(ui.swipe({ x: 40, y: 100, open: false }, { x: 110, y: 158 }, 400), null);
  assert.equal(ui.swipe({ x: 180, y: 100, open: true }, { x: 80, y: 105 }, 400), false);
});

test('a hung read aborts so subsequent polling can recover', async (t) => {
  t.mock.method(global, 'fetch', (_path, options) => new Promise((_resolve, reject) => {
    options.signal.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')));
  }));
  await assert.rejects(ui.request('/api/status', { timeout: 10 }), /连接超时/);
});

test('ambiguous write timeout is not retried', async (t) => {
  let attempts = 0;
  t.mock.method(global, 'fetch', (_path, options) => new Promise((_resolve, reject) => {
    attempts++;
    options.signal.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')));
  }));
  await assert.rejects(ui.request('/api/messages', { method: 'POST', timeout: 10 }), /结果尚未确认/);
  assert.equal(attempts, 1);
});

test('auth failures preserve HTTP status for the login screen', async (t) => {
  t.mock.method(global, 'fetch', async () => ({ ok: false, status: 401, json: async () => ({ detail: 'Login required' }) }));
  await assert.rejects(ui.request('/api/status'), (error) => error.status === 401);
});

test('switching away from a deleted session keeps partial failure visible and selected', async () => {
  const fs = require('node:fs');
  const vm = require('node:vm');
  const sourceCode = fs.readFileSync(require.resolve('../app.js'), 'utf8');
  const implementation = sourceCode.slice(sourceCode.indexOf('async function deleteConversations('), sourceCode.indexOf('async function refreshSessions('));
  const elements = new Map();
  const element = (selector) => {
    if (!elements.has(selector)) elements.set(selector, { disabled: false, textContent: '', value: '' });
    return elements.get(selector);
  };
  const context = vm.createContext({
    BridgeUI: ui, Set, window: { confirm: () => true }, $: element,
    sessionDeleteInProgress: false, sessionActionError: '',
    targets: { hermes: { title: 'Hermes' } }, source: { value: 'hermes', disabled: false },
    prompt: { disabled: false }, selectedSessions: { hermes: 'a' },
    sessionCatalogs: { hermes: { items: [{ id: 'a' }, { id: 'b' }, { id: 'c' }] } },
    sessionBulkState: { hermes: { active: true, selected: new Set(['a', 'b']) } },
    sessionsLoading: null, renderSessions() {}, refreshSessions: async () => {},
    rememberSession(target, id) { context.selectedSessions[target] = id; },
    selectConversation() { context.sessionActionError = ''; element('#session-error').textContent = ''; },
    request: async () => ({ deleted: [{ session_id: 'a' }], failed: [{ session_id: 'b', error: 'busy' }] }),
  });
  vm.runInContext(implementation, context);
  await context.deleteConversations('hermes', [{ id: 'a' }, { id: 'b' }], { disabled: false });
  assert.match(element('#session-error').textContent, /busy/);
  assert.deepEqual([...context.sessionBulkState.hermes.selected], ['b']);
  assert.equal(context.sessionBulkState.hermes.active, true);
  assert.equal(context.sessionDeleteInProgress, false);
});
