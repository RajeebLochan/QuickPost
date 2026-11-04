/* QuickPost front end: progressive enhancement over server-rendered pages.
   Every action here calls a real endpoint; optimistic UI is rolled back when
   the server says no. Without JavaScript, forms and links still work. */
(() => {
  "use strict";

  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
  const body = document.body;
  const userId = Number(body.dataset.userId || 0);
  const desktop = () => window.matchMedia("(min-width: 768px)").matches;

  // ------------------------------------------------------------ http
  function csrfToken() {
    const cookie = document.cookie.split("; ").find((c) => c.startsWith("csrftoken="));
    if (cookie) return decodeURIComponent(cookie.split("=")[1]);
    const input = $("input[name=csrfmiddlewaretoken]");
    return input ? input.value : "";
  }

  function goToLogin() {
    const next = encodeURIComponent(location.pathname + location.search);
    location.href = `${body.dataset.loginUrl}?next=${next}`;
  }

  async function api(url, { method = "POST", data, form } = {}) {
    if (!userId && method !== "GET") {
      goToLogin();
      throw new Error("login required");
    }
    const headers = { "X-Requested-With": "fetch", Accept: "application/json" };
    let payload;
    if (method !== "GET") {
      headers["X-CSRFToken"] = csrfToken();
      payload = form ? new FormData(form) : new URLSearchParams(data || {});
    }
    let response;
    try {
      response = await fetch(url, { method, headers, body: payload, credentials: "same-origin" });
    } catch (err) {
      throw new ApiError("You're offline. Check your connection and try again.");
    }
    if (response.redirected && response.url.includes("/accounts/login")) {
      goToLogin();
      throw new ApiError("Please log in.");
    }
    let json = {};
    try {
      json = await response.json();
    } catch (_) {
      /* non-JSON error page */
    }
    if (!response.ok) {
      throw new ApiError(json.error || defaultError(response.status), response.status);
    }
    return json;
  }

  class ApiError extends Error {
    constructor(message, status = 0) {
      super(message);
      this.status = status;
    }
  }

  function defaultError(status) {
    if (status === 403) return "You're not allowed to do that.";
    if (status === 404) return "That no longer exists.";
    if (status === 429) return "You're doing that too often. Try again in a minute.";
    return "Something went wrong. Try again.";
  }

  // ------------------------------------------------------------ toasts
  const toastBox = $("#toasts");
  function toast(text, { error = false, href, linkText } = {}) {
    if (!toastBox || !text) return;
    const el = document.createElement("div");
    el.className = "toast" + (error ? " is-error" : "");
    const span = document.createElement("span");
    span.textContent = text;
    el.append(span);
    if (href) {
      const a = document.createElement("a");
      a.href = href;
      a.textContent = linkText || "Open";
      a.style.marginLeft = "auto";
      el.append(a);
    }
    toastBox.append(el);
    setTimeout(() => {
      el.classList.add("is-leaving");
      setTimeout(() => el.remove(), 250);
    }, error ? 6000 : 3500);
  }
  window.QuickPost = { api, toast, ApiError };

  const flash = $("#flash-data");
  if (flash) {
    try {
      JSON.parse(flash.textContent).forEach((m) => toast(m.text, { error: m.level === "error" }));
    } catch (_) {}
  }

  // ------------------------------------------------------------ menus
  let openMenu = null;
  function closeMenu() {
    if (!openMenu) return;
    openMenu.menu.classList.remove("is-open");
    openMenu.trigger.setAttribute("aria-expanded", "false");
    openMenu = null;
  }
  function toggleMenu(trigger, menu) {
    const wasOpen = openMenu && openMenu.menu === menu;
    closeMenu();
    if (wasOpen) return;
    menu.classList.add("is-open");
    trigger.setAttribute("aria-expanded", "true");
    openMenu = { trigger, menu };
    const first = menu.querySelector("button:not([disabled]), a[href]");
    if (first && !menu.classList.contains("notif-pop")) first.focus({ preventScroll: true });
  }
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && openMenu) {
      const trigger = openMenu.trigger;
      closeMenu();
      trigger.focus();
    }
    if (openMenu && (e.key === "ArrowDown" || e.key === "ArrowUp")) {
      const items = $$(".menu-item:not([aria-disabled])", openMenu.menu);
      if (!items.length) return;
      e.preventDefault();
      const i = items.indexOf(document.activeElement);
      const next = e.key === "ArrowDown" ? (i + 1) % items.length : (i - 1 + items.length) % items.length;
      items[next].focus();
    }
  });

  // ------------------------------------------------------------ dialogs
  function openDialog(dialog) {
    if (typeof dialog.showModal === "function") dialog.showModal();
    else dialog.setAttribute("open", "");
  }
  function closeDialog(dialog) {
    if (typeof dialog.close === "function") dialog.close();
    else dialog.removeAttribute("open");
  }
  $$("dialog").forEach((d) =>
    d.addEventListener("click", (e) => {
      if (e.target === d) closeDialog(d); // backdrop click
    })
  );

  function confirmAction(text, okLabel = "Confirm") {
    const dialog = $("#confirm-dialog");
    if (!dialog) return Promise.resolve(window.confirm(text));
    $("[data-confirm-text]", dialog).textContent = text;
    const ok = $("[data-confirm-ok]", dialog);
    ok.textContent = okLabel;
    openDialog(dialog);
    ok.focus();
    return new Promise((resolve) => {
      const done = (value) => {
        ok.removeEventListener("click", yes);
        dialog.removeEventListener("close", no);
        closeDialog(dialog);
        resolve(value);
      };
      const yes = () => done(true);
      const no = () => done(false);
      ok.addEventListener("click", yes);
      dialog.addEventListener("close", no);
    });
  }

  // ------------------------------------------------------------ helpers
  function setCount(scope, key, value) {
    $$(`[data-count="${key}"]`, scope).forEach((el) => {
      const inStats = el.tagName === "STRONG";
      el.textContent = inStats ? String(value) : value > 0 ? String(value) : "";
    });
  }
  function postScopes(postId) {
    return $$(`[data-actions="${postId}"], .post-detail[data-post="${postId}"]`);
  }
  function busy(el, on) {
    el.toggleAttribute("disabled", on);
    el.setAttribute("aria-busy", on ? "true" : "false");
  }
  async function copyText(text) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch (_) {
      const ta = document.createElement("textarea");
      ta.value = text;
      ta.style.position = "fixed";
      ta.style.opacity = "0";
      document.body.append(ta);
      ta.select();
      const ok = document.execCommand("copy");
      ta.remove();
      return ok;
    }
  }
  function postIdOf(el) {
    const holder = el.closest("[data-actions]");
    return holder ? holder.dataset.actions : el.closest("[data-post]")?.dataset.post;
  }

  // ------------------------------------------------------------ actions
  const actions = {
    async react(btn) {
      const postId = postIdOf(btn);
      const scopes = postScopes(postId);
      const isLike = btn.classList.contains("like");
      const snapshot = scopes.map((s) => ({
        s,
        like: $(".action.like", s)?.getAttribute("aria-pressed"),
        dislike: $(".action.dislike", s)?.getAttribute("aria-pressed"),
        counts: $$("[data-count]", s).map((c) => [c, c.textContent]),
      }));
      // Optimistic: toggle this reaction, clear the opposite one.
      const pressed = btn.getAttribute("aria-pressed") === "true";
      scopes.forEach((s) => {
        const mine = $(isLike ? ".action.like" : ".action.dislike", s);
        const other = $(isLike ? ".action.dislike" : ".action.like", s);
        if (mine) mine.setAttribute("aria-pressed", String(!pressed));
        if (other && !pressed) other.setAttribute("aria-pressed", "false");
      });
      busy(btn, true);
      try {
        const data = await api(btn.dataset.url);
        scopes.forEach((s) => {
          $(".action.like", s)?.setAttribute("aria-pressed", String(data.liked));
          $(".action.dislike", s)?.setAttribute("aria-pressed", String(data.disliked));
          setCount(s, "likes_count", data.likes_count);
          setCount(s, "dislikes_count", data.dislikes_count);
        });
      } catch (err) {
        snapshot.forEach(({ s, like, dislike, counts }) => {
          if (like) $(".action.like", s)?.setAttribute("aria-pressed", like);
          if (dislike) $(".action.dislike", s)?.setAttribute("aria-pressed", dislike);
          counts.forEach(([c, t]) => (c.textContent = t));
        });
        toast(err.message, { error: true });
      } finally {
        busy(btn, false);
      }
    },

    async save(btn) {
      const pressed = btn.getAttribute("aria-pressed") === "true";
      btn.setAttribute("aria-pressed", String(!pressed));
      try {
        const data = await api(btn.dataset.url);
        btn.setAttribute("aria-pressed", String(data.saved));
        toast(data.message);
      } catch (err) {
        btn.setAttribute("aria-pressed", String(pressed));
        toast(err.message, { error: true });
      }
    },

    async repost(btn) {
      closeMenu();
      try {
        const data = await api(btn.dataset.url);
        $$(`[data-actions="${data.original_id}"], .post-detail[data-post="${data.original_id}"]`).forEach((s) => {
          $(".action.repost", s)?.setAttribute("aria-pressed", String(data.reposted));
          const label = $("[data-repost-label]", s);
          if (label) label.textContent = data.reposted ? "Undo repost" : "Repost";
          setCount(s, "reposts_count", data.reposts_count);
        });
        toast(data.message);
      } catch (err) {
        toast(err.message, { error: true });
      }
    },

    async share(btn) {
      const url = btn.dataset.shareUrl;
      if (navigator.share && !desktop()) {
        try {
          await navigator.share({ title: btn.dataset.shareTitle || "QuickPost", url });
          return;
        } catch (err) {
          if (err.name === "AbortError") return;
        }
      }
      toast((await copyText(url)) ? "Link copied" : "Couldn't copy the link", { error: false });
    },

    async "copy-link"(btn) {
      closeMenu();
      toast((await copyText(btn.dataset.shareUrl)) ? "Link copied" : "Couldn't copy the link");
    },

    async "delete-post"(btn, event) {
      event.preventDefault();
      closeMenu();
      if (!(await confirmAction("Delete this post? Its comments go with it. This can't be undone.", "Delete"))) return;
      try {
        await api(btn.dataset.url);
        const id = postIdOf(btn);
        if ($(`.post-detail[data-post="${id}"]`)) {
          location.href = "/feed/";
          return;
        }
        $$(`[data-post="${id}"]`).forEach((el) => el.remove());
        toast("Post deleted");
      } catch (err) {
        toast(err.message, { error: true });
      }
    },

    report(btn) {
      closeMenu();
      if (!userId) return goToLogin();
      const dialog = $("#report-dialog");
      const form = $("form", dialog);
      form.reset();
      form.elements.target_type.value = btn.dataset.targetType;
      form.elements.target_id.value = btn.dataset.targetId;
      openDialog(dialog);
    },

    async block(btn) {
      closeMenu();
      const name = btn.dataset.username;
      const ok = await confirmAction(
        `Block @${name}? They won't be able to see your profile or posts, follow you, comment or message you. They aren't notified.`,
        "Block"
      );
      if (!ok) return;
      try {
        await api(btn.dataset.url);
        toast(`Blocked @${name}`);
        setTimeout(() => (location.href = "/feed/"), 600);
      } catch (err) {
        toast(err.message, { error: true });
      }
    },

    async follow(btn) {
      const previous = { state: btn.dataset.state, text: btn.textContent };
      busy(btn, true);
      try {
        const data = await api(btn.dataset.url);
        btn.dataset.state = data.state;
        btn.textContent = { following: "Following", requested: "Requested", none: "Follow" }[data.state];
        const count = $("[data-followers-count]");
        if (count && btn.closest(".profile-head")) count.textContent = data.followers_count;
        if (data.state === "requested") toast("Request sent. You'll see their posts once they approve.");
      } catch (err) {
        btn.dataset.state = previous.state;
        btn.textContent = previous.text;
        toast(err.message, { error: true });
      } finally {
        busy(btn, false);
      }
    },

    reply(btn) {
      const form = $("[data-comment-form]");
      if (!form) return;
      form.elements.parent.value = btn.dataset.parent;
      const target = $("[data-reply-target]", form);
      target.textContent = `Replying to @${btn.dataset.username}`;
      target.hidden = false;
      $("[data-cancel-reply]", form).hidden = false;
      const ta = form.elements.content;
      if (!ta.value.includes(`@${btn.dataset.username}`)) ta.value = `@${btn.dataset.username} ` + ta.value;
      ta.dispatchEvent(new Event("input"));
      form.scrollIntoView({ block: "center", behavior: "smooth" });
      ta.focus();
    },

    async "delete-comment"(btn) {
      if (!(await confirmAction("Delete this comment?", "Delete"))) return;
      try {
        const data = await api(btn.dataset.url);
        btn.closest("[data-comment]").remove();
        $$(".post-detail").forEach((s) => setCount(s, "comments_count", data.comments_count));
        toast("Comment deleted");
      } catch (err) {
        toast(err.message, { error: true });
      }
    },
  };

  document.addEventListener("click", (event) => {
    const menuTrigger = event.target.closest("[data-menu]");
    if (menuTrigger) {
      event.preventDefault();
      toggleMenu(menuTrigger, document.getElementById(menuTrigger.dataset.menu));
      return;
    }
    const notif = event.target.closest("[data-notif-toggle]");
    if (notif && desktop()) {
      event.preventDefault();
      toggleNotifications(notif);
      return;
    }
    const actionEl = event.target.closest("[data-action]");
    if (actionEl && actions[actionEl.dataset.action]) {
      if (actionEl.tagName === "A") event.preventDefault();
      actions[actionEl.dataset.action](actionEl, event);
      return;
    }
    if (openMenu && !openMenu.menu.contains(event.target)) closeMenu();

    const closer = event.target.closest("[data-close]");
    if (closer) closeDialog(closer.closest("dialog"));

    const more = event.target.closest("[data-load-more]");
    if (more) {
      event.preventDefault();
      loadMore(more);
    }
    const lb = event.target.closest("[data-lightbox]");
    if (lb) {
      event.preventDefault();
      const dialog = $("#lightbox");
      $("img", dialog).src = lb.getAttribute("href");
      $("img", dialog).alt = $("img", lb)?.alt || "";
      openDialog(dialog);
    }
    const back = event.target.closest("[data-back]");
    if (back && document.referrer.startsWith(location.origin) && history.length > 1) {
      event.preventDefault();
      history.back();
    }
    const cancelReply = event.target.closest("[data-cancel-reply]");
    if (cancelReply) resetReply(cancelReply.closest("form"));
  });

  // ------------------------------------------------------------ notifications popover
  async function toggleNotifications(trigger) {
    const pop = $("#notif-pop");
    const willOpen = !pop.classList.contains("is-open");
    toggleMenu(trigger, pop);
    if (!willOpen) return;
    pop.innerHTML = '<div class="body"><div class="skeleton-post"><div class="skeleton avatar-s"></div><div class="lines"><div class="skeleton skeleton-line" style="width:70%"></div><div class="skeleton skeleton-line" style="width:40%"></div></div></div></div>';
    try {
      const res = await fetch("/notifications/menu/", { headers: { "X-Requested-With": "fetch" } });
      if (!res.ok) throw new Error();
      pop.innerHTML = await res.text();
    } catch (_) {
      pop.innerHTML = '<div class="empty"><p>Couldn\'t load notifications</p><a class="btn btn-sm btn-outline" href="/notifications/">Open notifications</a></div>';
    }
  }

  function setBadge(name, value) {
    $$(`[data-badge="${name}"]`).forEach((b) => {
      b.textContent = value > 99 ? "99+" : String(value);
      b.hidden = value <= 0;
    });
  }
  function badgeValue(name) {
    const b = $(`[data-badge="${name}"]`);
    return b && !b.hidden ? parseInt(b.textContent, 10) || 0 : 0;
  }

  // ------------------------------------------------------------ forms
  document.addEventListener("submit", async (event) => {
    const form = event.target;

    if (form.matches("[data-comment-form]")) {
      event.preventDefault();
      const button = $("[data-submit]", form);
      button.classList.add("is-loading");
      try {
        const data = await api(form.action, { form });
        const holder = document.createElement("div");
        holder.innerHTML = data.html.trim();
        const node = holder.firstElementChild;
        if (data.parent) {
          const replies = $(`[data-replies="${data.parent}"]`);
          replies.hidden = false;
          replies.append(node);
        } else {
          const list = $("[data-comment-list]");
          const loadMoreWrap = $("[data-load-more-wrap]", list);
          list.insertBefore(node, loadMoreWrap);
        }
        $("[data-no-comments]")?.remove();
        node.classList.add("is-flash");
        setTimeout(() => node.classList.remove("is-flash"), 1600);
        $$(".post-detail").forEach((s) => setCount(s, "comments_count", data.comments_count));
        form.elements.content.value = "";
        form.elements.content.dispatchEvent(new Event("input"));
        resetReply(form);
      } catch (err) {
        toast(err.message, { error: true });
      } finally {
        button.classList.remove("is-loading");
      }
      return;
    }

    if (form.matches("[data-report-form]")) {
      event.preventDefault();
      try {
        const data = await api(form.action, { form });
        closeDialog(form.closest("dialog"));
        toast(data.message || "Report sent");
      } catch (err) {
        toast(err.message, { error: true });
      }
      return;
    }

    if (form.matches("[data-mark-all]")) {
      event.preventDefault();
      try {
        await api(form.action, { form });
        setBadge("notifications", 0);
        $$(".notice.is-unread").forEach((n) => n.classList.remove("is-unread"));
        form.remove();
      } catch (err) {
        toast(err.message, { error: true });
      }
      return;
    }

    if (form.matches("[data-request-form]")) {
      event.preventDefault();
      try {
        const data = await api(form.action, { form });
        form.closest("[data-request]").remove();
        toast(data.message);
      } catch (err) {
        toast(err.message, { error: true });
      }
      return;
    }

    if (form.matches("[data-composer], [data-submit-once]")) {
      const button = $("[data-submit], button[type=submit]", form);
      if (button) {
        button.classList.add("is-loading");
        setTimeout(() => button.setAttribute("disabled", ""), 0);
      }
    }
  });

  function resetReply(form) {
    if (!form || !form.elements.parent) return;
    form.elements.parent.value = "";
    const target = $("[data-reply-target]", form);
    if (target) target.hidden = true;
    const cancel = $("[data-cancel-reply]", form);
    if (cancel) cancel.hidden = true;
  }

  // ------------------------------------------------------------ text inputs
  function updateCounter(ta) {
    const counter = document.getElementById(ta.dataset.countTo);
    const max = Number(counter?.dataset.max || ta.maxLength || 0);
    const length = ta.value.length;
    if (counter) {
      const left = max - length;
      counter.textContent = length ? String(left) : "";
      counter.classList.toggle("is-near", left <= 20 && left >= 0);
      counter.classList.toggle("is-over", left < 0);
    }
    const form = ta.form;
    const submit = form && $("[data-submit]", form);
    if (submit) {
      const hasImages = form.querySelector("[data-image-input]")?.files?.length > 0;
      const required = ta.required || form.matches(".composer");
      submit.disabled = (required && !ta.value.trim() && !hasImages) || length > max;
    }
  }
  function autogrow(ta) {
    ta.style.height = "auto";
    ta.style.height = Math.min(ta.scrollHeight + 2, 320) + "px";
  }
  document.addEventListener("input", (e) => {
    const ta = e.target;
    if (ta.matches("[data-count-to]")) updateCounter(ta);
    if (ta.matches("[data-autogrow]")) autogrow(ta);
  });
  $$("[data-count-to]").forEach(updateCounter);

  // Image picker with previews and per-image removal.
  $$("[data-image-input]").forEach((input) => {
    const form = input.form;
    const previews = $("[data-previews]", form);
    const max = Number(input.dataset.max || 4);
    const allowed = ["image/jpeg", "image/png", "image/webp", "image/gif"];
    let files = [];
    function sync() {
      const dt = new DataTransfer();
      files.forEach((f) => dt.items.add(f));
      input.files = dt.files;
      previews.innerHTML = "";
      files.forEach((file, index) => {
        const item = document.createElement("div");
        item.className = "preview";
        const img = document.createElement("img");
        img.alt = "";
        img.src = URL.createObjectURL(file);
        img.onload = () => URL.revokeObjectURL(img.src);
        const remove = document.createElement("button");
        remove.type = "button";
        remove.setAttribute("aria-label", `Remove ${file.name}`);
        remove.innerHTML = '<svg class="icon icon-sm" aria-hidden="true"><use href="#i-x"></use></svg>';
        remove.addEventListener("click", () => {
          files.splice(index, 1);
          sync();
        });
        item.append(img, remove);
        previews.append(item);
      });
      const ta = $("[data-count-to]", form);
      if (ta) updateCounter(ta);
    }
    input.addEventListener("change", () => {
      const picked = Array.from(input.files);
      for (const file of picked) {
        if (!allowed.includes(file.type)) {
          toast(`${file.name} isn't a JPEG, PNG, WebP or GIF`, { error: true });
          continue;
        }
        if (file.size > 5 * 1024 * 1024) {
          toast(`${file.name} is larger than 5 MB`, { error: true });
          continue;
        }
        if (files.length >= max) {
          toast(`You can add up to ${max} photos`, { error: true });
          break;
        }
        files.push(file);
      }
      sync();
    });
  });

  // ------------------------------------------------------------ load more
  async function loadMore(link) {
    const wrap = link.closest("[data-load-more-wrap]");
    link.classList.add("is-loading");
    const url = new URL(link.href, location.href);
    url.searchParams.set("partial", "1");
    try {
      const res = await fetch(url, { headers: { "X-Requested-With": "fetch", Accept: "application/json" } });
      if (!res.ok) throw new Error();
      const data = await res.json();
      const tpl = document.createElement("template");
      tpl.innerHTML = data.html;
      wrap.replaceWith(tpl.content);
    } catch (_) {
      link.classList.remove("is-loading");
      toast("Couldn't load more. Try again.", { error: true });
    }
  }

  // Broken avatar files fall back to the initial underneath.
  document.addEventListener(
    "error",
    (e) => {
      if (e.target.matches && e.target.matches("img[data-avatar]")) e.target.remove();
    },
    true
  );

  // ------------------------------------------------------------ live connection
  const live = {
    socket: null,
    handlers: {},
    retry: 0,
    queue: [],
    on(type, fn) {
      (this.handlers[type] = this.handlers[type] || []).push(fn);
    },
    emit(type, data) {
      (this.handlers[type] || []).forEach((fn) => fn(data));
    },
    get open() {
      return this.socket && this.socket.readyState === WebSocket.OPEN;
    },
    send(obj) {
      if (!this.open) return false;
      this.socket.send(JSON.stringify(obj));
      return true;
    },
    connect() {
      if (!userId || !("WebSocket" in window)) return;
      if (this.socket && this.socket.readyState <= WebSocket.OPEN) return;
      const scheme = location.protocol === "https:" ? "wss" : "ws";
      const socket = new WebSocket(`${scheme}://${location.host}/ws/live/`);
      this.socket = socket;
      socket.addEventListener("open", () => {
        this.retry = 0;
        this.emit("status", true);
      });
      socket.addEventListener("message", (e) => {
        let data;
        try {
          data = JSON.parse(e.data);
        } catch (_) {
          return;
        }
        this.emit(data.type, data);
      });
      socket.addEventListener("close", (e) => {
        this.emit("status", false);
        if (e.code === 4401) return; // not logged in
        const delay = Math.min(30000, 1000 * 2 ** this.retry++) + Math.random() * 500;
        setTimeout(() => this.connect(), delay);
      });
    },
  };
  QuickPost.live = live;

  live.on("notification", (data) => {
    setBadge("notifications", badgeValue("notifications") + 1);
    if (!location.pathname.startsWith("/notifications")) toast(data.text, { href: data.url, linkText: "View" });
  });
  live.on("message", (data) => {
    const m = data.message;
    if (m.sender_id === userId) return;
    const chat = $("[data-chat]");
    if (chat && Number(chat.dataset.chat) === m.conversation) return; // chat.js handles it
    setBadge("messages", badgeValue("messages") + 1);
    const item = $(`[data-inbox] [data-conversation="${m.conversation}"]`);
    if (item) {
      $("[data-preview]", item).textContent = m.content.slice(0, 80);
      item.classList.add("is-unread");
      item.parentElement.prepend(item);
    } else {
      toast(`New message from ${m.sender_name || m.sender}`, { href: `/messages/${m.conversation}/`, linkText: "Reply" });
    }
  });
  live.connect();
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") live.connect();
  });
})();
