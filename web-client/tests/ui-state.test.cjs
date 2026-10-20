const test = require('node:test');
const assert = require('node:assert/strict');
const ui = require('../ui-state.js');

test('audition stays on its bound voice and waits while a theme switch is pending', async () => {
  const fs = require('node:fs'), vm = require('node:vm');
  const code = fs.readFileSync(require.resolve('../app.js'), 'utf8');
  const handlers = new Map(), nodes = new Map();
  const node = (selector) => {
    if (!nodes.has(selector)) nodes.set(selector, { value: '', addEventListener(type, handler) { handlers.set(selector+':'+type, handler); } });
    return nodes.get(selector);
  };
  node('#display-theme').value='qiuqiu'; node('#voice-test-language').value='en';
  let played;
  const context = vm.createContext({ displayPending:true, voicePresetInitialized:false,
    $:node, playSpeech:async(text)=>{played=text;} });
  vm.runInContext(code.slice(code.indexOf('$("#tts-form").addEventListener'), code.indexOf('let displayPending = false;')), context);
  handlers.get('#voice-test-language:change')({currentTarget:node('#voice-test-language')});
  await handlers.get('#tts-form:submit')({preventDefault(){}});
  assert.equal(played,undefined);
  context.displayPending=false;
  await handlers.get('#tts-form:submit')({preventDefault(){}});
  assert.match(played,/^Hello, I am your robot/);
  node('#display-theme').value='dsh_pet';
  assert.match(context.voiceTestPreset('zh').text,/派蒙/);
});

function answerHarness(request) {
  const fs = require('node:fs'), vm = require('node:vm');
  const source = fs.readFileSync(require.resolve('../app.js'), 'utf8');
  const context = vm.createContext({ source: { value: 'hermes' }, selectedSessions: { hermes:'one', deepseek_harness:'two' },
    tasksContext:'hermes:one', answerTasks:[], tasksLoading:false, workspace:{hidden:false},
    document:{visibilityState:'visible'}, request, renderLiveAnswer(){}, refreshMessages:async()=>{}, showLogin(){} });
  vm.runInContext(source.slice(source.indexOf('function answerContext('), source.indexOf('function renderLiveAnswer(')), context);
  vm.runInContext(source.slice(source.indexOf('async function refreshTasks('), source.indexOf('$("#stop-answer").addEventListener')), context);
  return context;
}

test('stream polling discards late responses after switching AI or conversation', async () => {
  let finish;
  const h = answerHarness(() => new Promise(resolve => { finish=resolve; }));
  const pending = h.refreshTasks();
  h.source.value='deepseek_harness';
  finish({items:[{message_id:1,state:'running',text:'wrong session'}]});
  await pending;
  assert.equal(h.answerTasks.length,0);
  assert.equal(h.currentAnswerTask(),null);
  assert.equal(h.tasksLoading,false);
});

test('a temporary streaming read failure keeps the scoped stop control available', async () => {
  const h = answerHarness(async () => { throw Error('network'); });
  h.answerTasks=[{message_id:7,state:'running',text:'part'}];
  await h.refreshTasks();
  assert.equal(h.currentAnswerTask().message_id,7);
  h.selectedSessions.hermes='another';
  assert.equal(h.currentAnswerTask(),null);
});

function playerHarness(request) {
  const fs = require('node:fs'), vm = require('node:vm');
  const source = fs.readFileSync(require.resolve('../app.js'), 'utf8');
  const implementation = source.slice(source.indexOf('function renderSpeechButtons('), source.indexOf('async function request('));
  const buttons = [];
  const status = { textContent: '' };
  const context = vm.createContext({
    activePlayback: null, playbackRequestId: 0, audioOutput: { enabled: true },
    crypto: require('node:crypto'), request, $: () => status,
    document: { querySelectorAll: () => buttons },
  });
  vm.runInContext(implementation, context);
  function button(key) {
    const classes = new Set(['message-play-button']);
    const value = { dataset: { playbackKey: key, playLabel: '播放回复' }, disabled: false,
      setAttribute(name, text) { this[name] = text; },
      classList: { contains: (name) => classes.has(name), toggle(name, on) { if (on) classes.add(name); else classes.delete(name); } },
    };
    buttons.push(value);
    return value;
  }
  return { context, buttons, button, status };
}

test('same message toggles stop while synthesis is pending and ignores late response', async () => {
  let finish;
  const calls = [];
  const h = playerHarness((path, options) => {
    calls.push({ path, body: JSON.parse(options.body) });
    return path.endsWith('/speak') ? new Promise((resolve) => { finish = resolve; }) : Promise.resolve({ stopped: true });
  });
  const button = h.button('message-a'), error = { textContent: '' };
  const pending = h.context.playSpeech('hello', button, error);
  assert.equal(button.disabled, false);
  assert.equal(button['aria-label'], '停止播放');
  assert.match(button.innerHTML, /rect/);
  await h.context.playSpeech('hello', button, error);
  assert.equal(h.context.activePlayback, null);
  assert.equal(calls[0].body.playback_id, calls[1].body.playback_id);
  finish({ queued: false, superseded: true });
  await pending;
  assert.equal(button['aria-label'], '播放回复');
  assert.equal(h.status.textContent, '已停止播放。');
});

test('switching messages and rerendering keep only the new message in stop state', async () => {
  const synthesis = [];
  const h = playerHarness((path) => path.endsWith('/speak') ?
    new Promise((resolve) => synthesis.push(resolve)) : Promise.resolve({ stopped: true }));
  const first = h.button('message-a'), second = h.button('message-b'), error = {};
  const old = h.context.playSpeech('old', first, error);
  const latest = h.context.playSpeech('new', second, error);
  await new Promise(setImmediate);
  synthesis[0]({ queued: false, superseded: true });
  synthesis[1]({ queued: true });
  await Promise.all([old, latest]);
  assert.equal(first['aria-label'], '播放回复');
  assert.equal(second['aria-label'], '停止播放');
  h.buttons.length = 0;
  const replacement = h.button('message-b');
  h.context.renderSpeechButtons();
  assert.equal(replacement['aria-label'], '停止播放');
  assert.equal(replacement.disabled, false);
});

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
    drafts: ui.drafts(null), draftContext: null,
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

function memoryStorage() {
  const data = new Map();
  return { get length() { return data.size; }, key: (i) => [...data.keys()][i],
    getItem: (key) => data.get(key) ?? null, setItem: (key, value) => data.set(key, value),
    removeItem: (key) => data.delete(key) };
}

test('drafts survive reload and stay separate across AI and sessions', () => {
  const storage = memoryStorage(), drafts = ui.drafts(storage);
  drafts.save('hermes:one', 'first draft');
  drafts.save('hermes:two', 'second draft');
  drafts.save('deepseek_harness:one', 'different AI');
  const reloaded = ui.drafts(storage);
  assert.equal(reloaded.read('hermes:one'), 'first draft');
  assert.equal(reloaded.read('hermes:two'), 'second draft');
  assert.equal(reloaded.read('deepseek_harness:one'), 'different AI');
  reloaded.save('hermes:one', '');
  assert.equal(ui.drafts(storage).read('hermes:one'), '');
  assert.equal(ui.drafts(storage).read('hermes:two'), 'second draft');
  storage.setItem('conversation:source', 'hermes');
  reloaded.clear();
  assert.equal(storage.length, 1);
  assert.equal(reloaded.read('hermes:two'), '');
});

test('unavailable draft storage keeps edits in memory without breaking typing', () => {
  const drafts = ui.drafts({ getItem() { throw Error('disabled'); }, setItem() { throw Error('full'); } });
  assert.equal(drafts.read('hermes:one'), '');
  drafts.save('hermes:one', 'still here');
  assert.equal(drafts.read('hermes:one'), 'still here');
});

function composerHarness(request, refreshSessions = async () => {}) {
  const fs = require('node:fs'), vm = require('node:vm');
  const code = fs.readFileSync(require.resolve('../app.js'), 'utf8');
  let submit;
  const button = { disabled: false, addEventListener() {} }, error = { textContent: '' };
  const context = vm.createContext({
    source: { value: 'hermes' }, selectedSessions: { hermes: 'one' },
    sessionCatalogs: {},
    prompt: { value: 'same text', focus() { this.focused = true; } },
    drafts: ui.drafts(null), sessionDeleteInProgress: false, sendPending: false, currentSessionReadOnly: () => false,
    conversationTargets: ['hermes', 'deepseek_harness'], targets: { hermes: { title: 'Hermes' } },
    $: (selector) => selector === '#composer' ? { addEventListener(_event, handler) { submit = handler; } } :
      selector === '#send-error' ? error : button,
    request, refreshSessions, refreshMessages: async () => {},
  });
  vm.runInContext(code.slice(code.indexOf('function answerContext('), code.indexOf('function currentAnswerTask(')), context);
  vm.runInContext(code.slice(code.indexOf('$("#composer").addEventListener'), code.indexOf('$("#tts-form").addEventListener')), context);
  context.drafts.save('hermes:one', context.prompt.value);
  return { context, submit: () => submit({ preventDefault() {} }), button, error };
}

test('late send confirmation cannot clear identical text in another session', async () => {
  let finish, payload;
  const h = composerHarness((_path, options) => { payload = JSON.parse(options.body); return new Promise(resolve => { finish = resolve; }); });
  const pending = h.submit();
  h.context.selectedSessions.hermes = 'two';
  h.context.drafts.save('hermes:two', 'same text');
  finish({ delivery: 'queued' }); await pending;
  assert.equal(payload.session_id, 'one');
  assert.equal(h.context.prompt.value, 'same text');
  assert.equal(h.context.drafts.read('hermes:two'), 'same text');
  assert.equal(h.context.drafts.read('hermes:one'), '');
  assert.equal(h.context.prompt.focused, undefined);
});

test('send confirmation preserves edits made while the request is pending', async () => {
  let finish, attempts = 0;
  const h = composerHarness(() => { attempts++; return new Promise(resolve => { finish = resolve; }); });
  const pending = h.submit();
  await h.submit();
  assert.equal(attempts, 1);
  h.context.prompt.value = 'next message';
  h.context.drafts.save('hermes:one', 'next message');
  finish({ delivery: 'queued' }); await pending;
  assert.equal(h.context.prompt.value, 'next message');
  assert.equal(h.context.drafts.read('hermes:one'), 'next message');
  assert.equal(h.button.disabled, false);
});

test('desktop read-only session blocks submission before sending anything', async () => {
  let attempts = 0;
  const h = composerHarness(async () => { attempts++; });
  h.context.sessionCatalogs.hermes = { items: [{ id: 'one', read_only: true }] };
  await h.submit();
  assert.equal(attempts, 0);
  assert.equal(h.context.prompt.value, 'same text');
});

test('switching while resolving a missing session never sends into the new session', async () => {
  let finish, attempts = 0;
  const h = composerHarness(async () => { attempts++; }, () => new Promise(resolve => { finish = resolve; }));
  h.context.selectedSessions.hermes = '';
  const pending = h.submit();
  h.context.selectedSessions.hermes = 'two';
  finish(); await pending;
  assert.equal(attempts, 0);
  assert.equal(h.context.prompt.value, 'same text');
  assert.equal(h.button.disabled, false);
  assert.match(h.error.textContent, /本次未发送/);
});

test('real draft switching saves old text and restores each session on return', () => {
  const fs = require('node:fs'), vm = require('node:vm');
  const code = fs.readFileSync(require.resolve('../app.js'), 'utf8');
  const context = vm.createContext({ key: 'hermes:one', draftContext: null,
    drafts: ui.drafts(null), prompt: { value: '' }, answerContext() { return context.key; } });
  vm.runInContext(code.slice(code.indexOf('function syncDraftContext('), code.indexOf('prompt.addEventListener("input"')), context);
  context.syncDraftContext(); context.prompt.value = 'unfinished Hermes message';
  context.key = 'deepseek_harness:two'; context.syncDraftContext();
  assert.equal(context.prompt.value, '');
  context.prompt.value = 'unfinished Harness message';
  context.key = 'hermes:one'; context.syncDraftContext();
  assert.equal(context.prompt.value, 'unfinished Hermes message');
  context.key = 'deepseek_harness:two'; context.syncDraftContext();
  assert.equal(context.prompt.value, 'unfinished Harness message');
});

test('background tab pauses periodic reads and foreground return refreshes immediately', () => {
  const fs = require('node:fs'), vm = require('node:vm');
  const code = fs.readFileSync(require.resolve('../app.js'), 'utf8');
  const intervals = [], handlers = new Map(), calls = [];
  const context = vm.createContext({ workspace: { hidden: false }, lastVoiceTargetKey: '',
    document: { visibilityState: 'hidden', addEventListener(name, fn) { handlers.set(name, fn); } },
    window: { addEventListener() {} }, setInterval(fn) { intervals.push(fn); },
    syncVoiceTarget() { calls.push('voice'); }, refreshStatus() { calls.push('status'); },
    refreshSessions() { calls.push('sessions'); }, refreshMessages() { calls.push('messages'); },
    refreshTasks() { if (context.document.visibilityState === 'visible') calls.push('tasks'); },
  });
  vm.runInContext(code.slice(code.indexOf('document.addEventListener("visibilitychange"'),
    code.indexOf('// Keep the composer above Android')), context);
  for (const interval of intervals) interval();
  assert.deepEqual(calls, []);
  context.document.visibilityState = 'visible'; handlers.get('visibilitychange')();
  assert.deepEqual(calls, ['voice', 'status', 'sessions', 'messages', 'tasks']);
});
