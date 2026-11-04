/* Chat room: real-time delivery over the shared live socket, with the same
   server endpoint as a fallback while the socket reconnects. Both paths save
   through one service and push to every participant, so delivery is consistent. */
(() => {
  "use strict";
  const root = document.querySelector("[data-chat]");
  if (!root || !window.QuickPost) return;

  const { api, toast, live } = window.QuickPost;
  const me = Number(document.body.dataset.userId);
  const conversation = Number(root.dataset.chat);
  const log = root.querySelector("[data-chat-log]");
  const form = root.querySelector("[data-chat-form]");
  const input = form && form.elements.content;
  const typingEl = root.querySelector("[data-typing]");
  const conn = root.querySelector("[data-conn]");
  const presence = root.querySelector("[data-presence]");
  const otherName = root.querySelector(".page-head .section-title")?.textContent.trim() || "They";

  const timeFmt = new Intl.DateTimeFormat(undefined, { hour: "2-digit", minute: "2-digit" });
  const dayFmt = new Intl.DateTimeFormat(undefined, { day: "numeric", month: "long", year: "numeric" });

  const nearBottom = () => log.scrollHeight - log.scrollTop - log.clientHeight < 120;
  const scrollToBottom = () => (log.scrollTop = log.scrollHeight);
  scrollToBottom();

  function dayKey(date) {
    return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
  }

  function buildBubble({ id, content, sender_id, timestamp, is_read }, { pending = false, clientId } = {}) {
    const mine = sender_id === me;
    const date = timestamp ? new Date(timestamp) : new Date();
    const row = document.createElement("div");
    row.className = "bubble-row" + (mine ? " mine" : "") + (pending ? " is-pending" : "");
    row.dataset.day = dayKey(date);
    if (id) row.dataset.message = id;
    if (clientId) row.dataset.client = clientId;
    const bubble = document.createElement("div");
    bubble.className = "bubble";
    bubble.textContent = content;
    const meta = document.createElement("div");
    meta.className = "bubble-meta";
    const time = document.createElement("time");
    time.dateTime = date.toISOString();
    time.textContent = timeFmt.format(date);
    meta.append(time);
    if (mine) {
      const receipt = document.createElement("span");
      receipt.dataset.receipt = "";
      receipt.textContent = pending ? "Sending" : is_read ? "Seen" : "Sent";
      if (is_read) receipt.className = "read";
      meta.append(receipt);
    }
    row.append(bubble, meta);
    return row;
  }

  function appendRow(row) {
    root.querySelector("[data-empty-chat]")?.remove();
    const last = Array.from(log.querySelectorAll(".bubble-row")).pop();
    if (!last || last.dataset.day !== row.dataset.day) {
      const day = document.createElement("div");
      day.className = "chat-day";
      day.textContent = dayFmt.format(new Date(row.querySelector("time").dateTime));
      log.append(day);
    }
    const stick = nearBottom() || row.classList.contains("mine");
    log.append(row);
    if (stick) scrollToBottom();
  }

  function settle(row, message) {
    row.dataset.message = message.id;
    row.classList.remove("is-pending", "is-failed");
    const receipt = row.querySelector("[data-receipt]");
    if (receipt && receipt.textContent !== "Seen") receipt.textContent = "Sent";
  }

  // ------------------------------------------------------------ incoming
  live.on("message", ({ message }) => {
    if (message.conversation !== conversation) return;
    if (log.querySelector(`[data-message="${message.id}"]`)) return;
    if (message.sender_id === me) {
      const pending = Array.from(log.querySelectorAll(".bubble-row.is-pending")).find(
        (r) => r.querySelector(".bubble").textContent === message.content
      );
      if (pending) return settle(pending, message);
    } else {
      showTyping(false);
      setPresence("Active now", true);
      if (document.visibilityState === "visible") markRead();
    }
    appendRow(buildBubble(message));
  });

  live.on("ack", ({ client_id, id }) => {
    const row = log.querySelector(`[data-client="${client_id}"]`);
    if (row && !row.dataset.message) settle(row, { id });
  });

  live.on("error", ({ client_id, error }) => {
    if (!client_id) return;
    const row = log.querySelector(`[data-client="${client_id}"]`);
    if (row) fail(row, error);
  });

  live.on("read", ({ conversation: id, reader_id, up_to }) => {
    if (id !== conversation || reader_id === me) return;
    log.querySelectorAll(".bubble-row.mine[data-message]").forEach((row) => {
      if (Number(row.dataset.message) <= up_to) {
        const receipt = row.querySelector("[data-receipt]");
        if (receipt) {
          receipt.textContent = "Seen";
          receipt.className = "read";
        }
      }
    });
  });

  let typingTimer;
  function showTyping(on) {
    clearTimeout(typingTimer);
    typingEl.textContent = on ? `${otherName} is typing…` : "";
    if (on) typingTimer = setTimeout(() => showTyping(false), 6000);
  }
  live.on("typing", ({ conversation: id, user_id, typing }) => {
    if (id !== conversation || user_id === me) return;
    showTyping(typing);
    if (typing) setPresence("Active now", true);
  });

  function setPresence(text, online) {
    if (!presence) return;
    presence.classList.toggle("is-online", online);
    const label = presence.querySelector("[data-presence-text]");
    if (label) label.textContent = text;
    if (!presence.querySelector(".dot")) {
      const dot = document.createElement("span");
      dot.className = "dot";
      dot.setAttribute("aria-hidden", "true");
      presence.prepend(dot);
    }
  }

  live.on("status", (connected) => {
    if (conn) conn.hidden = connected;
    if (connected) markRead();
  });
  if (conn) conn.hidden = true;
  setTimeout(() => conn && (conn.hidden = live.open), 2000);

  // ------------------------------------------------------------ read receipts
  let readPending = false;
  async function markRead() {
    if (readPending) return;
    readPending = true;
    try {
      if (!live.send({ action: "read", conversation })) {
        await api(root.dataset.readUrl);
      }
    } catch (_) {
      /* not critical; next visit marks them read */
    } finally {
      readPending = false;
    }
  }
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") markRead();
  });

  // ------------------------------------------------------------ sending
  function fail(row, error) {
    row.classList.remove("is-pending");
    row.classList.add("is-failed");
    const receipt = row.querySelector("[data-receipt]");
    if (receipt) receipt.textContent = "Not sent";
    toast(error || "Message not sent", { error: true });
  }

  async function send(content) {
    const clientId = `c${Date.now()}${Math.random().toString(16).slice(2, 6)}`;
    const row = buildBubble({ content, sender_id: me }, { pending: true, clientId });
    appendRow(row);
    const viaSocket = live.send({ action: "send", conversation, content, client_id: clientId });
    if (viaSocket) {
      // If neither an ack nor the pushed message arrives, retry over HTTP once.
      setTimeout(() => {
        if (row.classList.contains("is-pending")) sendHttp(row, content);
      }, 8000);
      return;
    }
    sendHttp(row, content);
  }

  async function sendHttp(row, content) {
    try {
      const data = await api(root.dataset.sendUrl, { data: { content } });
      if (!log.querySelector(`[data-message="${data.message.id}"]`)) settle(row, data.message);
      else row.remove();
    } catch (err) {
      fail(row, err.message);
    }
  }

  let typingSent = 0;
  let idleTimer;
  function sendTyping(on) {
    live.send({ action: "typing", conversation, typing: on });
    typingSent = on ? Date.now() : 0;
  }

  if (form) {
    form.addEventListener("submit", (e) => {
      e.preventDefault();
      const content = input.value.trim();
      if (!content) return;
      if (content.length > 1000) {
        toast("Messages can be at most 1000 characters", { error: true });
        return;
      }
      input.value = "";
      input.style.height = "";
      clearTimeout(idleTimer);
      if (typingSent) sendTyping(false);
      send(content);
      input.focus();
    });
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
        e.preventDefault();
        form.requestSubmit();
      }
    });
    input.addEventListener("input", () => {
      if (!input.value.trim()) {
        if (typingSent) sendTyping(false);
        return;
      }
      if (Date.now() - typingSent > 3000) sendTyping(true);
      clearTimeout(idleTimer);
      idleTimer = setTimeout(() => typingSent && sendTyping(false), 2500);
    });
    input.focus();
  }

  // ------------------------------------------------------------ history
  const older = root.querySelector("[data-older]");
  if (older) {
    older.addEventListener("click", async () => {
      const first = log.querySelector(".bubble-row[data-message]");
      const url = new URL(root.dataset.historyUrl, location.href);
      if (first) url.searchParams.set("before", first.dataset.message);
      older.classList.add("is-loading");
      try {
        const data = await api(url, { method: "GET" });
        const height = log.scrollHeight;
        const anchor = older.parentElement.nextSibling;
        let lastDay = null;
        data.messages.forEach((m) => {
          const row = buildBubble(m);
          if (row.dataset.day !== lastDay) {
            const day = document.createElement("div");
            day.className = "chat-day";
            day.textContent = dayFmt.format(new Date(m.timestamp));
            log.insertBefore(day, anchor);
            lastDay = row.dataset.day;
          }
          log.insertBefore(row, anchor);
        });
        log.scrollTop = log.scrollHeight - height;
        if (!data.has_more) older.parentElement.remove();
      } catch (err) {
        toast(err.message, { error: true });
      } finally {
        older.classList.remove("is-loading");
      }
    });
  }
})();
