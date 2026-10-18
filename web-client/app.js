const $ = (selector) => document.querySelector(selector);
const login = $("#login");
const workspace = $("#workspace");
const source = $("#source");
const messages = $("#messages");
const prompt = $("#prompt");
const targets = {
  hermes: { title: "Hermes", avatar: "H", placeholder: "给 Hermes 发消息…" },
  deepseek_harness: { title: "DeepSeek Harness", avatar: "D", placeholder: "给 DeepSeek Harness 发消息…" },
  doubao_web: { title: "豆包 PPT 网页", avatar: "豆", placeholder: "记录给豆包 PPT 的消息…" },
};
let lastMessageVersion = "";
let messagesLoading = false;
let playbackRequestId = 0;
let pendingApproval = null;
let audioOutput = { volume: 100, muted: false, enabled: true };
let audioSave = Promise.resolve();
let audioPending = 0;
let volumeTimer;
let sidebarSwipeStart = null;
const conversationTargets = ["hermes", "deepseek_harness"];
const sessionCatalogs = {};
const selectedSessions = {};
const sessionBulkState = Object.fromEntries(conversationTargets.map((target) =>
  [target, { active: false, selected: new Set() }]));
try {
  const savedSource = sessionStorage.getItem("conversation:source");
  if (targets[savedSource]) source.value = savedSource;
} catch {}
let sessionsLoading = null;
let sessionDeleteInProgress = false;
let sessionActionError = "";
let voiceTargetSave = Promise.resolve();
let voiceTargetRevision = 0;
let lastVoiceTargetKey = "";
let lastVoiceError = "";
let statusLoading = false;
for (const target of conversationTargets) {
  try { selectedSessions[target] = sessionStorage.getItem(`conversation:${target}`); } catch {}
}

function sessionGroupCollapsed(target) {
  try { return localStorage.getItem(`sessions:collapsed:${target}`) === "true"; } catch { return false; }
}

function rememberSession(target, id) {
  selectedSessions[target] = id;
  try { sessionStorage.setItem(`conversation:${target}`, id); } catch {}
}

function syncVoiceTarget() {
  if (workspace.hidden || document.visibilityState !== "visible") return Promise.resolve();
  const target = { source: source.value, session_id: selectedSessions[source.value] || null };
  const key = JSON.stringify(target);
  if (key === lastVoiceTargetKey) return voiceTargetSave;
  const revision = ++voiceTargetRevision;
  voiceTargetSave = voiceTargetSave.catch(() => {}).then(async () => {
    if (revision !== voiceTargetRevision) return;
    try {
      await request("/api/voice/target", { method: "POST", body: key });
      if (revision === voiceTargetRevision) lastVoiceTargetKey = key;
    } catch (error) {
      if (revision === voiceTargetRevision) {
        lastVoiceTargetKey = "";
        $("#send-error").textContent = `按键语音目标切换失败：${error.message}。请重新选择会话后再录音。`;
      }
    }
  });
  return voiceTargetSave;
}

function renderSessions() {
  const groups = $("#session-groups");
  groups.replaceChildren();
  for (const target of conversationTargets) {
    const group = document.createElement("section");
    group.className = "session-group";
    const header = document.createElement("div");
    header.className = "session-group-header";
    const collapsed = sessionGroupCollapsed(target);
    const items = sessionCatalogs[target]?.items || [];
    const bulk = sessionBulkState[target];
    const toggle = document.createElement("button");
    toggle.type = "button";
    toggle.className = "session-group-toggle";
    toggle.setAttribute("aria-expanded", String(!collapsed));
    toggle.setAttribute("aria-label", `${collapsed ? "展开" : "收起"}${targets[target].title}会话`);
    const name = document.createElement("strong");
    name.textContent = targets[target].title;
    const count = document.createElement("span");
    count.className = "session-group-count";
    count.textContent = String(items.length);
    const chevron = document.createElement("span");
    chevron.className = "session-group-chevron";
    chevron.setAttribute("aria-hidden", "true");
    chevron.textContent = "⌄";
    toggle.append(name, count, chevron);
    const list = document.createElement("div");
    list.className = "session-list";
    list.hidden = collapsed;
    toggle.addEventListener("click", () => {
      const nextCollapsed = !sessionGroupCollapsed(target);
      try { localStorage.setItem(`sessions:collapsed:${target}`, String(nextCollapsed)); } catch {}
      list.hidden = nextCollapsed;
      toggle.setAttribute("aria-expanded", String(!nextCollapsed));
      toggle.setAttribute("aria-label", `${nextCollapsed ? "展开" : "收起"}${targets[target].title}会话`);
    });
    const create = document.createElement("button");
    create.type = "button";
    create.className = "text-button";
    create.textContent = "+ 新建";
    create.setAttribute("aria-label", `新建 ${targets[target].title} 会话`);
    create.addEventListener("click", () => createConversation(target, create));
    const manage = document.createElement("button");
    manage.type = "button";
    manage.className = "text-button session-manage-button";
    manage.textContent = bulk.active ? "取消" : "选择";
    manage.setAttribute("aria-label", bulk.active ? `取消选择 ${targets[target].title} 会话` : `批量删除 ${targets[target].title} 会话`);
    manage.hidden = !items.length && !bulk.active;
    manage.addEventListener("click", () => {
      bulk.active = !bulk.active;
      bulk.selected.clear();
      renderSessions();
    });
    header.append(toggle, create, manage);
    group.append(header);
    for (const item of items) {
      const row = document.createElement("div");
      row.className = "session-row";
      const title = item.title || "未命名会话";
      if (bulk.active) {
        const checkbox = document.createElement("input");
        checkbox.type = "checkbox";
        checkbox.className = "session-checkbox";
        checkbox.checked = bulk.selected.has(item.id);
        checkbox.setAttribute("aria-label", `选择 ${targets[target].title} 会话：${title}`);
        checkbox.addEventListener("change", () => {
          if (checkbox.checked) bulk.selected.add(item.id);
          else bulk.selected.delete(item.id);
          if (bulkCount) {
            bulkCount.textContent = `删除选中（${bulk.selected.size}）`;
            bulkCount.disabled = bulk.selected.size === 0;
          }
          if (selectAll) selectAll.textContent = bulk.selected.size === items.length ? "取消全选" : "全选";
        });
        const label = document.createElement("span");
        label.className = "session-item session-item-label";
        label.textContent = title;
        label.title = title;
        row.append(checkbox, label);
      } else {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "session-item";
        button.textContent = title;
        button.title = title;
        if (source.value === target && selectedSessions[target] === item.id) button.setAttribute("aria-current", "true");
        button.addEventListener("click", () => selectConversation(target, item.id));
        const remove = document.createElement("button");
        remove.type = "button";
        remove.className = "session-delete-button";
        remove.textContent = "×";
        remove.title = `删除会话：${title}`;
        remove.setAttribute("aria-label", `删除 ${targets[target].title} 会话：${title}`);
        remove.addEventListener("click", () => deleteConversation(target, item, remove));
        row.append(button, remove);
      }
      list.append(row);
    }
    if (!items.length) {
      const empty = document.createElement("p");
      empty.className = "session-empty";
      empty.textContent = "暂无会话";
      list.append(empty);
    }
    group.append(list);
    let bulkCount = null;
    let selectAll = null;
    if (bulk.active && items.length) {
      const bulkActions = document.createElement("div");
      bulkActions.className = "session-bulk-actions";
      selectAll = document.createElement("button");
      selectAll.type = "button";
      selectAll.className = "text-button";
      selectAll.textContent = bulk.selected.size === items.length ? "取消全选" : "全选";
      selectAll.addEventListener("click", () => {
        if (bulk.selected.size === items.length) bulk.selected.clear();
        else items.forEach((item) => bulk.selected.add(item.id));
        renderSessions();
      });
      bulkCount = document.createElement("button");
      bulkCount.type = "button";
      bulkCount.className = "session-bulk-delete";
      bulkCount.textContent = `删除选中（${bulk.selected.size}）`;
      bulkCount.disabled = bulk.selected.size === 0;
      bulkCount.addEventListener("click", () => {
        const selected = items.filter((item) => bulk.selected.has(item.id));
        deleteConversations(target, selected, bulkCount);
      });
      bulkActions.append(selectAll, bulkCount);
      group.append(bulkActions);
    }
    groups.append(group);
  }
  const current = sessionCatalogs[source.value]?.items.find((item) => item.id === selectedSessions[source.value]);
  if (current) $("#conversation-title").textContent = `${targets[source.value].title} · ${current.title}`;
}

function selectConversation(target, id) {
  rememberSession(target, id);
  source.value = target;
  try { sessionStorage.setItem("conversation:source", target); } catch {}
  prompt.value = "";
  $("#send-error").textContent = "";
  $("#session-status").textContent = "";
  $("#session-error").textContent = "";
  setTarget();
  setSidebar(false);
  messages.replaceChildren();
  renderSessions();
  syncVoiceTarget();
  refreshStatus();
  refreshMessages();
}

async function createConversation(target, button) {
  button.disabled = true;
  try {
    const result = await request("/api/sessions", { method: "POST", body: JSON.stringify({ source: target }) });
    sessionCatalogs[target] ||= { items: [] };
    sessionCatalogs[target].items.unshift(result.item);
    selectConversation(target, result.item.id);
    $("#session-error").textContent = "";
    $("#session-status").textContent = "";
    prompt.focus();
  } catch (error) { $("#session-error").textContent = error.message; }
  finally { button.disabled = false; }
}

async function deleteConversation(target, item, button) {
  return deleteConversations(target, [item], button);
}

async function deleteConversations(target, items, button) {
  if (!items.length || sessionDeleteInProgress) return;
  sessionActionError = "";
  $("#session-error").textContent = "";
  const targetName = targets[target].title;
  const selectedAtStart = selectedSessions[target];
  const description = items.length === 1 ? `“${items[0].title || "未命名会话"}”` : `${items.length} 个所选会话`;
  if (!window.confirm(`将从 ${targetName} 中永久删除 ${description} 及其聊天记录，此操作无法撤销。要继续吗？`)) return;
  const sendButton = $("#composer button[type='submit']");
  const previousDisabled = { prompt: prompt.disabled, source: source.disabled, send: sendButton.disabled };
  prompt.disabled = true;
  source.disabled = true;
  sendButton.disabled = true;
  button.disabled = true;
  sessionDeleteInProgress = true;
  let actionError = "";
  try {
    // Wait for a catalog poll that started before deletion. It discards its results
    // while sessionDeleteInProgress is true, so it cannot overwrite our final UI.
    if (sessionsLoading) await sessionsLoading;
    const result = { deleted: [], failed: [] };
    for (let offset = 0; offset < items.length; offset += 5) {
      const chunk = items.slice(offset, offset + 5);
      try {
        const response = await request("/api/sessions/batch", {
          method: "DELETE", timeout: 240000,
          body: JSON.stringify({ source: target, session_ids: chunk.map((item) => item.id) }),
        });
        const outcome = BridgeUI.deletionOutcome(chunk, response);
        result.deleted.push(...outcome.deleted.map((item) => ({ session_id: item.id })));
        result.failed.push(...outcome.failed);
      } catch (error) {
        result.failed.push(...items.slice(offset).map((item) => ({ session_id: item.id, error: error.message })));
        break;
      }
      $("#session-status").textContent = `已处理 ${Math.min(offset + 5, items.length)} / ${items.length} 个会话`;
    }
    const deletedIds = new Set((result.deleted || []).map((item) => item.session_id));
    const failures = (result.failed || []).map((failure) => {
      const item = items.find((candidate) => candidate.id === failure.session_id);
      return `${item?.title || "未命名会话"}：${failure.error}`;
    });
    const catalog = sessionCatalogs[target];
    if (catalog) catalog.items = catalog.items.filter((entry) => !deletedIds.has(entry.id));
    const deleted = items.filter((item) => deletedIds.has(item.id));
    const wasSelected = deletedIds.has(selectedAtStart) && selectedSessions[target] === selectedAtStart;
    const next = catalog?.items[0];
    if (wasSelected) rememberSession(target, next?.id || "");
    sessionBulkState[target].selected.clear();
    for (const failure of result.failed || []) sessionBulkState[target].selected.add(failure.session_id);
    sessionBulkState[target].active = failures.length > 0;
    actionError = failures.length ? `删除失败：${failures.join("；")}` : "";
    sessionActionError = actionError;
    $("#session-error").textContent = sessionActionError;
    $("#session-status").textContent = deleted.length ? `已删除 ${deleted.length} 个会话` : "";
    if (wasSelected && source.value === target && next) {
      selectConversation(target, next.id);
      $("#session-status").textContent = `已删除 ${deleted.length} 个会话`;
    } else if (wasSelected && source.value === target) {
      try { sessionStorage.setItem("conversation:source", target); } catch {}
      prompt.value = "";
      lastMessageVersion = "";
      messages.replaceChildren();
      $("#conversation-title").textContent = targets[target].title;
      setTarget();
      renderSessions();
      syncVoiceTarget();
      refreshStatus();
    } else {
      renderSessions();
    }
  } catch (error) {
    actionError = `删除失败：${error.message}`;
    sessionActionError = actionError;
    $("#session-error").textContent = sessionActionError;
    renderSessions();
  } finally {
    sessionActionError = actionError;
    sessionDeleteInProgress = false;
    button.disabled = false;
    prompt.disabled = previousDisabled.prompt;
    source.disabled = previousDisabled.source;
    sendButton.disabled = previousDisabled.send;
    await refreshSessions();
    if (sessionActionError) $("#session-error").textContent = sessionActionError;
  }
}

async function refreshSessions() {
  if (sessionDeleteInProgress) return;
  if (sessionsLoading) return sessionsLoading;
  sessionsLoading = (async () => {
    const errors = [];
    const catalogs = {};
    await Promise.all(conversationTargets.map(async (target) => {
      try {
        const result = await request(`/api/sessions?source=${target}`);
        catalogs[target] = result;
      } catch (error) { errors.push(`${targets[target].title}：${error.message}`); }
    }));
    if (sessionDeleteInProgress) return;
    for (const target of conversationTargets) {
      if (!catalogs[target]) continue;
      sessionCatalogs[target] = catalogs[target];
      if (!selectedSessions[target]) rememberSession(target, catalogs[target].active_id || "");
    }
    $("#session-error").textContent = sessionActionError || errors.join("；");
    renderSessions();
  })();
  try { await sessionsLoading; } finally { sessionsLoading = null; }
}

function renderAudioOutput(settings) {
  audioOutput = settings;
  $("#speaker-volume").value = settings.volume;
  $("#volume-value").textContent = `${settings.volume}%`;
  $("#mute-output").setAttribute("aria-pressed", String(settings.muted));
  const muteLabel = settings.muted ? "恢复语音播报" : "一键静音";
  $("#mute-output").setAttribute("aria-label", muteLabel);
  $("#mute-output").title = muteLabel;
  $("#mute-output").classList.toggle("is-silent", !settings.enabled);
  $("#volume-toggle").classList.toggle("is-silent", !settings.enabled);
  $("#audio-output-note").textContent = !settings.enabled ?
    "仅显示文字回复；录音与屏幕动画照常运行。" : "100% 为当前已确认的音量上限。";
}

function saveAudioOutput(change) {
  audioPending++;
  renderAudioOutput({ ...audioOutput, ...change,
    enabled: !(change.muted ?? audioOutput.muted) && (change.volume ?? audioOutput.volume) > 0 });
  if (!audioOutput.enabled) {
    playbackRequestId++;
    $("#playback-status").textContent = "已静音，回复仅显示文字。";
  }
  audioSave = audioSave.then(async () => {
    try {
      const settings = await request("/api/audio/output", { method: "POST", body: JSON.stringify(change) });
      if (audioPending === 1) renderAudioOutput(settings);
      $("#audio-output-error").textContent = "";
    } catch (error) {
      $("#audio-output-error").textContent = `设置未保存：${error.message}`;
    } finally { audioPending--; }
  });
  return audioSave;
}

function updateApproval(approval) {
  const previousRequest = pendingApproval?.request_id;
  pendingApproval = approval || null;
  const panel = $("#approval-panel");
  panel.hidden = !pendingApproval;
  if (!pendingApproval) {
    $("#approval-error").textContent = "";
    return;
  }
  $("#approval-description").textContent = pendingApproval.description || "Hermes 正在等待你的决定。";
  $("#approval-command").textContent = pendingApproval.command || "未提供命令预览，请谨慎审批。";
  if (!workspace.hidden && previousRequest !== pendingApproval.request_id) setSidebar(true, { restoreFocus: false });
}

async function resolveApproval(choice) {
  const approval = pendingApproval;
  if (!approval) return;
  const buttons = [$("#approval-once"), $("#approval-deny")];
  buttons.forEach((button) => { button.disabled = true; });
  $("#approval-error").textContent = "";
  try {
    await request("/api/hermes/approval", {
      method: "POST", body: JSON.stringify({ request_id: approval.request_id, choice }),
    });
    updateApproval(null);
    await refreshStatus();
  } catch (error) {
    $("#approval-error").textContent = error.message;
    await refreshStatus();
  } finally {
    buttons.forEach((button) => { button.disabled = false; });
  }
}

async function playSpeech(text, button, errorBox) {
  if (button.disabled) return;
  if (!audioOutput.enabled) {
    $("#playback-status").textContent = "已静音，回复仅显示文字。请恢复语音或提高音量后重试。";
    return;
  }
  const original = button.textContent;
  const requestId = ++playbackRequestId;
  button.disabled = true;
  button.textContent = "正在播放…";
  errorBox.textContent = "";
  $("#playback-status").textContent = "正在本机生成并播放语音…";
  try {
    const result = await request("/api/tts/speak", {
      method: "POST", timeout: 180000, body: JSON.stringify({ text }),
    });
    if (requestId === playbackRequestId) {
      $("#playback-status").textContent = result.muted ? "已静音，回复仅显示文字。" : result.superseded ?
        "这次朗读已被更新的请求取代。" : "已发送到机器人，正在播放。";
    }
    button.textContent = result.superseded ? "已切换" : "播放中";
  } catch (error) {
    errorBox.textContent = error.message;
    if (requestId === playbackRequestId) $("#playback-status").textContent = `朗读失败：${error.message}`;
  } finally {
    setTimeout(() => { button.disabled = false; button.textContent = original; }, 1800);
  }
}

async function request(path, options = {}) {
  return BridgeUI.request(path, options);
}

function showLogin() {
  setSidebar(false, { restoreFocus: false });
  lastVoiceTargetKey = "";
  voiceTargetRevision++;
  login.hidden = false;
  workspace.hidden = true;
  lastMessageVersion = "";
  updateApproval(null);
}

function showWorkspace() {
  login.hidden = true;
  workspace.hidden = false;
}

function setSidebar(open, { restoreFocus = true } = {}) {
  const panel = $("#sidebar");
  const trigger = $("#sidebar-toggle");
  const backdrop = $("#sidebar-backdrop");
  panel.classList.toggle("is-open", open);
  panel.inert = !open;
  panel.setAttribute("aria-hidden", String(!open));
  trigger.setAttribute("aria-expanded", String(open));
  trigger.setAttribute("aria-label", open ? "关闭桌面 AI 机器人侧栏" : "打开桌面 AI 机器人侧栏");
  backdrop.hidden = !open;
  $(".conversation").inert = open;
  if (open) $("#sidebar-close").focus({ preventScroll: true });
  else if (restoreFocus && !workspace.hidden) trigger.focus({ preventScroll: true });
}

$("#sidebar-toggle").addEventListener("click", () => {
  setSidebar($("#sidebar").inert);
});
$("#sidebar-toggle").addEventListener("keydown", (event) => {
  if (event.key === "Enter" || event.key === " ") {
    event.preventDefault();
    setSidebar($("#sidebar").inert);
  }
});
$("#sidebar-close").addEventListener("click", () => setSidebar(false));
$("#sidebar-backdrop").addEventListener("click", () => setSidebar(false));
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !$("#sidebar").inert) {
    event.preventDefault();
    setSidebar(false);
  }
  if (event.key === "Tab" && !$("#sidebar").inert) {
    const controls = [...$("#sidebar").querySelectorAll("button, input, select, summary, [tabindex='0']")]
      .filter((element) => !element.disabled && element.getClientRects().length);
    const first = controls[0], last = controls.at(-1);
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
  }
});

document.addEventListener("pointerdown", (event) => {
  if (event.pointerType !== "touch" || workspace.hidden) return;
  if (event.target.closest("input, textarea, select, button, a, [contenteditable='true']")) return;
  const open = !$("#sidebar").inert;
  if (!open && event.clientX > window.innerWidth / 4) return;
  if (open && !$("#sidebar").contains(event.target)) return;
  sidebarSwipeStart = { x: event.clientX, y: event.clientY, open, id: event.pointerId };
}, { passive: true });
document.addEventListener("pointerup", (event) => {
  if (!sidebarSwipeStart) return;
  const start = sidebarSwipeStart;
  sidebarSwipeStart = null;
  if (event.pointerId !== start.id) return;
  const next = BridgeUI.swipe(start, { x: event.clientX, y: event.clientY }, window.innerWidth);
  if (next !== null) setSidebar(next, { restoreFocus: false });
}, { passive: true });
document.addEventListener("pointercancel", () => { sidebarSwipeStart = null; }, { passive: true });

function setTarget() {
  const target = targets[source.value];
  $("#conversation-title").textContent = target.title;
  prompt.placeholder = target.placeholder;
  $("#session-panel").hidden = source.value === "doubao_web";
  const session = sessionCatalogs[source.value]?.items.find((item) => item.id === selectedSessions[source.value]);
  $("#conversation-title").textContent = session ? `${target.title} · ${session.title}` : target.title;
  lastMessageVersion = "";
}

function updateDevice(link) {
  const badge = $("#device");
  badge.classList.toggle("offline", !link.connected);
  badge.textContent = link.connected ? `设备已连接 · ${link.port}` :
    link.present ? `等待设备握手 · ${link.port}` : "设备未连接";

}

async function refreshStatus() {
  if (statusLoading) return false;
  statusLoading = true;
  try {
    const status = await request("/api/status");
    showWorkspace();
    updateDevice(status.device);
    const task = status.task || { label: "准备就绪", state: "idle" };
    $("#task-status").textContent = task.detail ? `${task.label} · ${task.detail}` : task.label;
    $("#task-status").dataset.state = task.state;
    const maintenance = status.maintenance || {};
    $("#task-status").title = maintenance.version ? `Bridge ${maintenance.version}` : "";
    const warning = maintenance.low_disk_space ? "磁盘剩余空间不足 1 GB，请清理后继续使用。" :
      maintenance.database?.state === "deferred" ? "启动时数据库检查因忙碌或超时暂缓，请稍后重启复查。" : "";
    $("#maintenance-warning").textContent = warning;
    $("#maintenance-warning").hidden = !warning;
    if (!audioPending && !volumeTimer && status.audio_output) renderAudioOutput(status.audio_output);
    const voiceStatus = status.tts || {};
    const paimonOption = $("#voice-select option[value='paimon']");
    paimonOption.disabled = !voiceStatus.paimon_ready;
    $("#voice-select").value = voiceStatus.active || "kokoro";
    const connected = status.hermes?.available;
    const voiceTarget = status.voice?.target;
    if (voiceTarget) $("#voice-tools-toggle").title = `语音工具 · 按键录音目标：${targets[voiceTarget.source]?.title || "未选择"}`;
    const voiceError = status.voice?.state === "error" ? status.voice.last_error || "语音处理失败" : "";
    if (voiceError && voiceError !== lastVoiceError) $("#playback-status").textContent = `按键语音：${voiceError}`;
    lastVoiceError = voiceError;
    updateApproval(status.hermes?.approval);
    $("#connection-state").textContent = source.value === "hermes" ?
      status.hermes?.approval ? "Hermes 正在等待工具审批" :
      status.hermes?.running ? "Hermes 正在回复…" : connected ? "已连接 · 当前会话" : "Hermes 未连接" :
      "仅保存消息 · 暂无自动回复";
    if (source.value === "deepseek_harness") {
      const harness = status.deepseek_harness || {};
      $("#connection-state").textContent = harness.last_error ? `Harness：${harness.last_error}` :
        harness.running ? "DeepSeek Harness 正在回复…" :
        harness.available ? "已连接 · 当前会话" : "DeepSeek Harness 暂未连接";
    }
    return true;
  } catch (error) {
    if (error.status === 401) showLogin();
    else if (!workspace.hidden) $("#connection-state").textContent = "Bridge 暂时无法连接，正在重试…";
    return false;
  } finally { statusLoading = false; }
}

function deliveryLabel(item) {
  if (item.role === "assistant") return "";
  if (item.source === "doubao_web") return "仅保存";
  const name = targets[item.source]?.title || "AI";
  return {
    queued: `等待 ${name} 回复`,
    running: `${name} 正在回复…`,
    completed: "已回复",
    failed: "发送失败",
    interrupted: "回复中断，请重新发送",
    not_configured: "旧消息，仅保存",
  }[item.delivery] || item.delivery;
}

function messageNode(item, voiceReplyIds) {
  const assistant = item.role === "assistant";
  const row = document.createElement("article");
  row.className = `message-row ${assistant ? "from-assistant" : "from-user"}`;
  row.dataset.messageId = item.id;
  const avatar = document.createElement("span");
  avatar.className = "message-avatar";
  avatar.setAttribute("aria-hidden", "true");
  avatar.textContent = assistant ? targets[item.source].avatar : "我";
  const content = document.createElement("div");
  content.className = "message-content";
  const role = document.createElement("div");
  role.className = "message-role";
  role.textContent = assistant ? (voiceReplyIds.has(item.reply_to) ? `${targets[item.source].title} · 语音回复` : targets[item.source].title) :
    (item.input_method === "voice" ? "你 · 语音" : "你");
  const bubble = document.createElement("div");
  bubble.className = "message-bubble";
  bubble.textContent = item.text;
  const meta = document.createElement("div");
  meta.className = "message-meta";
  const time = document.createElement("time");
  time.dateTime = item.created_at;
  time.textContent = new Date(item.created_at).toLocaleString("zh-CN", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" });
  meta.append(time);
  const stateText = deliveryLabel(item);
  if (stateText) {
    const state = document.createElement("span");
    if (["failed", "interrupted"].includes(item.delivery)) state.className = "failed";
    state.textContent = `· ${stateText}`;
    meta.append(state);
  }
  content.append(role, bubble, meta);
  if (assistant) {
    const actions = document.createElement("div");
    actions.className = "message-actions";
    const speak = document.createElement("button");
    speak.type = "button";
    speak.textContent = item.text.length > 300 ? "朗读前 300 字" : "让机器人朗读";
    speak.addEventListener("click", async () => {
      await playSpeech(item.text.slice(0, 300), speak, $("#send-error"));
    });
    actions.append(speak);
    content.append(actions);
  }
  row.append(avatar, content);
  return row;
}

async function refreshMessages() {
  if (messagesLoading || workspace.hidden) return;
  messagesLoading = true;
  const selected = source.value;
  const sessionId = selectedSessions[selected] || "";
  const context = `${selected}:${sessionId}`;
  try {
    if (conversationTargets.includes(selected) && !sessionCatalogs[selected]) await refreshSessions();
    if (sessionId !== (selectedSessions[selected] || "")) return;
    const result = await request(`/api/messages?source=${encodeURIComponent(selected)}${sessionId ? `&session_id=${encodeURIComponent(sessionId)}` : ""}`);
    if (selected !== source.value || sessionId !== (selectedSessions[selected] || "")) return;
    const version = `${context}:${result.items.map((item) => `${item.id}-${item.delivery}`).join(",")}`;
    if (version === lastMessageVersion) return;
    const nearBottom = messages.scrollHeight - messages.scrollTop - messages.clientHeight < 100;
    const sourceChanged = !lastMessageVersion.startsWith(`${context}:`);
    lastMessageVersion = version;
    const voiceReplyIds = new Set(result.items.filter((item) => item.input_method === "voice").map((item) => item.id));
    const nodes = result.items.map((item) => messageNode(item, voiceReplyIds));
    if (!nodes.length) {
      const empty = document.createElement("div");
      empty.className = "empty-state";
      const icon = document.createElement("span");
      icon.textContent = targets[selected].avatar;
      const heading = document.createElement("h3");
      heading.textContent = `开始与 ${targets[selected].title} 对话`;
      const detail = document.createElement("p");
      detail.textContent = selected !== "doubao_web" ? `发送第一条消息，${targets[selected].title} 的回复会在这里出现。` : "这里会保存你发送的消息，自动回复尚未接入。";
      empty.append(icon, heading, detail);
      nodes.push(empty);
    }
    messages.replaceChildren(...nodes);
    if (nearBottom || sourceChanged) messages.scrollTop = messages.scrollHeight;
  } catch (error) {
    if (error.status === 401) showLogin();
    else $("#send-error").textContent = `读取消息失败：${error.message}`;
  } finally {
    messagesLoading = false;
    if (`${source.value}:${selectedSessions[source.value] || ""}` !== context) refreshMessages();
  }
}

$("#login-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  $("#login-error").textContent = "";
  try {
    await request("/api/login", { method: "POST", body: JSON.stringify({ token: $("#key").value }) });
    $("#key").value = "";
    showWorkspace();
    setTarget();
    await refreshSessions();
    setTarget();
    await syncVoiceTarget();
    await Promise.all([refreshStatus(), refreshMessages()]);
  } catch (error) { $("#login-error").textContent = error.message; }
});

$("#composer").addEventListener("submit", async (event) => {
  event.preventDefault();
  const text = prompt.value.trim();
  if (!text) return;
  const button = $("#composer button[type=submit]");
  const errorBox = $("#send-error");
  errorBox.textContent = "";
  button.disabled = true;
  try {
    const target = source.value;
    if (conversationTargets.includes(target) && !selectedSessions[target]) {
      await refreshSessions();
      if (!selectedSessions[target]) throw new Error("请先在侧栏新建或选择一个会话。");
    }
    const result = await request("/api/messages", { method: "POST", body: JSON.stringify({
      source: target, text, session_id: selectedSessions[target] || null,
    }) });
    if (source.value === target && prompt.value.trim() === text) prompt.value = "";
    if (result.delivery === "failed") errorBox.textContent = `${targets[target].title} 暂时无法接收；消息已保存。`;
    await refreshMessages();
  } catch (error) { errorBox.textContent = error.message; }
  finally { button.disabled = false; prompt.focus(); }
});

$("#tts-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  await playSpeech($("#speak-text").value, $("#tts-form button[type=submit]"), $("#tts-error"));
});

$("#voice-select").addEventListener("change", async (event) => {
  const select = event.currentTarget;
  select.disabled = true;
  try {
    await request("/api/tts/voice", {
      method: "POST", body: JSON.stringify({ voice: select.value }),
    });
    await refreshStatus();
  } catch (error) {
    $("#tts-error").textContent = error.message;
    await refreshStatus();
  } finally { select.disabled = false; }
});

function setVolumePanel(open) {
  $("#audio-panel").hidden = !open;
  $("#volume-toggle").setAttribute("aria-expanded", String(open));
  if (open) setVoicePanel(false);
}
function setVoicePanel(open) {
  $("#voice-tools-panel").hidden = !open;
  $("#voice-tools-toggle").setAttribute("aria-expanded", String(open));
  if (open) setVolumePanel(false);
}
$("#voice-tools-toggle").addEventListener("click", () => setVoicePanel($("#voice-tools-panel").hidden));
$("#volume-toggle").addEventListener("click", () => {
  setVolumePanel($("#audio-panel").hidden);
});
document.addEventListener("click", (event) => {
  if (!event.target.closest(".device-audio-group")) { setVolumePanel(false); setVoicePanel(false); }
});
$("#voice-tools-panel").addEventListener("keydown", (event) => {
  if (event.key === "Escape") { setVoicePanel(false); $("#voice-tools-toggle").focus(); }
});
$("#audio-panel").addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    setVolumePanel(false);
    $("#volume-toggle").focus();
  }
});

$("#speaker-volume").addEventListener("input", (event) => {
  const volume = Number(event.target.value);
  $("#volume-value").textContent = `${volume}%`;
  clearTimeout(volumeTimer);
  volumeTimer = setTimeout(() => { volumeTimer = null; saveAudioOutput({ volume }); }, 150);
});
$("#mute-output").addEventListener("click", () => {
  // Flush the final slider value before toggling so polling cannot overwrite it.
  if (volumeTimer) {
    clearTimeout(volumeTimer);
    volumeTimer = null;
    saveAudioOutput({ volume: Number($("#speaker-volume").value) });
  }
  const change = { muted: !audioOutput.muted };
  if (!change.muted && audioOutput.volume === 0) change.volume = 100;
  saveAudioOutput(change);
});

$("#approval-once").addEventListener("click", () => resolveApproval("once"));
$("#approval-deny").addEventListener("click", () => resolveApproval("deny"));

source.addEventListener("change", () => {
  setSidebar(false);
  try { sessionStorage.setItem("conversation:source", source.value); } catch {}
  setTarget(); renderSessions(); syncVoiceTarget(); refreshStatus(); refreshMessages();
});
$("#logout").addEventListener("click", async () => {
  try { await request("/api/logout", { method: "POST" }); } finally { showLogin(); }
});

setTarget();
refreshStatus().then(async (ready) => { if (ready) { await refreshSessions(); setTarget(); await syncVoiceTarget(); refreshMessages(); } });
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible" && !workspace.hidden) {
    lastVoiceTargetKey = "";
    syncVoiceTarget();
  }
});
window.addEventListener("focus", () => { if (!workspace.hidden) { lastVoiceTargetKey = ""; syncVoiceTarget(); } });
setInterval(() => { if (!workspace.hidden) refreshMessages(); }, 2000);
setInterval(() => { if (!workspace.hidden) { refreshStatus(); } }, 2000);
setInterval(() => { if (!workspace.hidden) refreshSessions(); }, 6000);

// Keep the composer above Android/iOS on-screen keyboards.
function fitViewport() {
  if (!window.visualViewport || window.visualViewport.scale === 1) {
    document.documentElement.style.setProperty("--app-height", `${window.visualViewport?.height || window.innerHeight}px`);
  }
}
window.visualViewport?.addEventListener("resize", fitViewport);
window.addEventListener("resize", fitViewport);
fitViewport();

document.querySelector("#download-diagnostics").addEventListener("click", async (event) => {
  const button = event.currentTarget;
  button.disabled = true;
  $("#diagnostics-error").textContent = "";
  try {
    const report = await request("/api/diagnostics");
    const url = URL.createObjectURL(new Blob([JSON.stringify(report, null, 2)], { type: "application/json" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = `robot-diagnostics-${new Date().toISOString().slice(0, 10)}.json`;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 10000);
  } catch (error) { $("#diagnostics-error").textContent = error.message; }
  finally { button.disabled = false; }
});
