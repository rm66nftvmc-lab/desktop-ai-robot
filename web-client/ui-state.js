/* Pure interaction rules shared with the browser regression tests. */
(function (root) {
  const api = {
    drafts(storage) {
      const prefix = "bridge:draft:", memory = new Map();
      return {
        read(context) {
          if (memory.has(context)) return memory.get(context);
          let value = "";
          try { value = storage?.getItem(prefix + context) || ""; } catch {}
          value = value.slice(0, 4000);
          memory.set(context, value);
          return value;
        },
        save(context, value) {
          value = String(value).slice(0, 4000);
          memory.set(context, value);
          try {
            if (value) storage?.setItem(prefix + context, value);
            else storage?.removeItem(prefix + context);
          } catch {} // A full/disabled tab store must not prevent typing.
        },
        clear() {
          memory.clear();
          try {
            for (let i = storage.length - 1; i >= 0; i--) {
              const key = storage.key(i);
              if (key?.startsWith(prefix)) storage.removeItem(key);
            }
          } catch {}
        },
      };
    },
    deletionOutcome(items, result) {
      const deleted = new Set((result.deleted || []).map((item) => item.session_id));
      const errors = new Map((result.failed || []).map((item) => [item.session_id, item.error]));
      return {
        deleted: items.filter((item) => deleted.has(item.id)),
        failed: items.filter((item) => !deleted.has(item.id)).map((item) => ({
          session_id: item.id, error: errors.get(item.id) || "服务器未确认删除，请刷新列表核对后重试",
        })),
      };
    },
    swipe(start, end, width) {
      const dx = end.x - start.x, dy = end.y - start.y;
      if (Math.abs(dx) < 64 || Math.abs(dy) > 60 || Math.abs(dx) < Math.abs(dy) * 1.5) return null;
      if (!start.open && start.x <= width / 4 && dx > 0) return true;
      if (start.open && dx < 0) return false;
      return null;
    },
    async request(path, options = {}) {
      const { timeout = 15000, ...fetchOptions } = options;
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), timeout);
      try {
        const response = await fetch(path, {
          credentials: "same-origin", cache: "no-store",
          headers: { "Content-Type": "application/json" }, ...fetchOptions, signal: controller.signal,
        });
        const body = await response.json().catch(() => ({}));
        if (controller.signal.aborted) throw new DOMException("aborted", "AbortError");
        if (!response.ok) {
          const error = new Error(body.detail || `请求失败 (${response.status})`);
          error.status = response.status;
          throw error;
        }
        return body;
      } catch (error) {
        if (error.name === "AbortError") throw new Error(
          fetchOptions.method && fetchOptions.method !== "GET" ?
            "请求超时，结果尚未确认；请刷新会话核对后再操作" : "连接超时，正在等待 Bridge 恢复");
        throw error;
      } finally { clearTimeout(timer); }
    },
  };
  root.BridgeUI = api;
  if (typeof module !== "undefined") module.exports = api;
})(globalThis);
