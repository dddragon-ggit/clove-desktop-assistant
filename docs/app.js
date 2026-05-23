let SUPABASE_URL = "";
let SUPABASE_KEY = "";
let EDGE_FUNCTION_URL = "";

function loadSupabaseConfig() {
  SUPABASE_URL = localStorage.getItem("supabase_url") || "";
  SUPABASE_KEY = localStorage.getItem("supabase_key") || "";
  EDGE_FUNCTION_URL = SUPABASE_URL ? SUPABASE_URL + "/functions/v1/todos-api" : "";
}

function storeSupabaseConfig(url, key) {
  localStorage.setItem("supabase_url", url);
  localStorage.setItem("supabase_key", key);
  SUPABASE_URL = url;
  SUPABASE_KEY = key;
  EDGE_FUNCTION_URL = url + "/functions/v1/todos-api";
}

let todos = [];
let notes = [];
let currentFilter = "all";
let searchQuery = "";
let noteSearchQuery = "";
let currentSection = "todos"; // "todos" or "notes"
let apiToken = "";
let notifiedTodoIds = new Set(); // 已通知的待办 ID，避免重复提醒
const DAILY_AUTO_COMPLETE_HOUR = 23;
const DAILY_AUTO_COMPLETE_MINUTE = 30;
const DAILY_AUTO_COMPLETE_LAST_KEY = "daily_auto_complete_last_date";
let dailyAutoCompleteTimer = null;
let dailyAutoCompleteInProgress = false;

// --- Token Auth ---

function getStoredToken() {
  return localStorage.getItem("api_token") || "";
}

function storeToken(token) {
  localStorage.setItem("api_token", token);
  apiToken = token;
}

async function validateToken(token) {
  try {
    const resp = await fetch(EDGE_FUNCTION_URL, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${SUPABASE_KEY}`,
        "X-API-Token": token,
      },
      body: JSON.stringify({ action: "select", data: {} }),
    });
    console.log("validateToken response:", resp.status, resp.ok);
    return resp.ok;
  } catch (e) {
    console.error("validateToken error:", e);
    return false;
  }
}

function showTokenScreen() {
  document.getElementById("token-screen").classList.add("open");
}

function hideTokenScreen() {
  document.getElementById("token-screen").classList.remove("open");
}

async function handleTokenSubmit() {
  const urlInput = document.getElementById("cfg-url");
  const keyInput = document.getElementById("cfg-key");
  const input = document.getElementById("token-input");
  const errorEl = document.getElementById("token-error");
  const url = urlInput.value.trim();
  const key = keyInput.value.trim();
  const token = input.value.trim();

  if (!url || !key || !token) {
    errorEl.textContent = "请填写所有配置项";
    errorEl.style.display = "block";
    return;
  }

  storeSupabaseConfig(url, key);

  const btn = document.getElementById("token-submit");
  btn.textContent = "验证中...";
  btn.disabled = true;
  errorEl.style.display = "none";

  try {
    const valid = await validateToken(token);
    if (valid) {
      storeToken(token);
      hideTokenScreen();
      initApp();
    } else {
      errorEl.textContent = "令牌无效，请重试";
      errorEl.style.display = "block";
    }
  } catch (e) {
    errorEl.textContent = "网络错误: " + e.message;
    errorEl.style.display = "block";
    console.error("Token submit error:", e);
  } finally {
    btn.textContent = "确认连接";
    btn.disabled = false;
  }
}

// --- Edge Function API ---

async function apiCall(action, data = {}, table = "todos") {
  const resp = await fetch(EDGE_FUNCTION_URL, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Authorization": `Bearer ${SUPABASE_KEY}`,
      "X-API-Token": apiToken,
    },
    body: JSON.stringify({ action, data, table }),
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err.error || `HTTP ${resp.status}`);
  }
  return await resp.json();
}

// --- Data ---

async function loadTodos() {
  try {
    const data = await apiCall("select");
    todos = data || [];
    renderTodos();
    return true;
  } catch (e) {
    if (navigator.onLine) {
      showToast("加载失败: " + e.message, "error");
    }
    return false;
  }
}

async function addTodo(title, taskType, priority, dueDate) {
  if (!title.trim()) return;
  try {
    const now = new Date().toISOString();
    const todo = {
      id: crypto.randomUUID ? crypto.randomUUID() : "todo-" + Date.now() + "-" + Math.random().toString(36).slice(2, 8),
      title: title.trim(),
      description: "",
      status: "open",
      priority: priority || "normal",
      task_type: taskType || "temporary",
      important: priority === "high" || priority === "urgent",
      needs_computer: false,
      due_at: dueDate || null,
      created_at: now,
      updated_at: now,
    };
    await apiCall("insert", todo);
    todos.unshift(todo);
    renderTodos();
    showToast("已添加并同步");
  } catch (e) {
    showToast("添加失败: " + e.message, "error");
  }
}

async function updateTodo(id, changes) {
  try {
    const now = new Date().toISOString();
    changes.updated_at = now;
    if (changes.priority) {
      changes.important = changes.priority === "high" || changes.priority === "urgent";
    }
    await apiCall("update", { id, ...changes });
    const todo = todos.find((t) => t.id === id);
    if (todo) Object.assign(todo, changes);
    renderTodos();
    showToast("已保存");
    return true;
  } catch (e) {
    showToast("更新失败: " + e.message, "error");
    return false;
  }
}

async function toggleDone(id, currentStatus) {
  try {
    const now = new Date().toISOString();
    const todo = todos.find((t) => t.id === id);
    if (todo && todo.task_type === "daily") {
      const updates = isDailyCompletedToday(todo)
        ? {
            status: "open",
            completed_at: null,
            daily_completed_on: null,
            updated_at: now,
          }
        : dailyCompletionUpdates(new Date());
      await apiCall("update", { id, ...updates });
      Object.assign(todo, updates);
      notifiedTodoIds.delete(id);
      renderTodos();
      return;
    }
    const newStatus = currentStatus === "done" ? "open" : "done";
    const updates = {
      status: newStatus,
      updated_at: now,
    };
    if (newStatus === "done") {
      updates.completed_at = now;
    } else {
      updates.completed_at = null;
    }
    await apiCall("update", { id, ...updates });
    if (todo) Object.assign(todo, updates);
    notifiedTodoIds.delete(id);
    renderTodos();
  } catch (e) {
    showToast("操作失败: " + e.message, "error");
  }
}

async function deleteTodo(id) {
  if (!confirm("确定删除？")) return;
  try {
    await apiCall("delete", { id });
    todos = todos.filter((t) => t.id !== id);
    notifiedTodoIds.delete(id);
    renderTodos();
    showToast("已删除");
  } catch (e) {
    showToast("删除失败: " + e.message, "error");
  }
}

// --- Notes ---

async function loadNotes() {
  try {
    const data = await apiCall("select", {}, "notes");
    notes = data || [];
    renderNotes();
  } catch (e) {
    if (navigator.onLine) {
      showToast("加载笔记失败: " + e.message, "error");
    }
  }
}

async function addNote(title, content) {
  if (!title.trim()) return;
  try {
    const now = new Date().toISOString();
    const note = {
      id: crypto.randomUUID ? crypto.randomUUID() : "note-" + Date.now() + "-" + Math.random().toString(36).slice(2, 8),
      title: title.trim(),
      content: content || "",
      created_at: now,
      updated_at: now,
    };
    await apiCall("insert", note, "notes");
    notes.unshift(note);
    renderNotes();
    showToast("笔记已保存");
  } catch (e) {
    showToast("保存失败: " + e.message, "error");
  }
}

async function updateNote(id, changes) {
  try {
    changes.updated_at = new Date().toISOString();
    await apiCall("update", { id, ...changes }, "notes");
    const note = notes.find((n) => n.id === id);
    if (note) Object.assign(note, changes);
    renderNotes();
    showToast("已更新");
  } catch (e) {
    showToast("更新失败: " + e.message, "error");
  }
}

async function deleteNote(id) {
  if (!confirm("确定删除这条笔记？")) return;
  try {
    await apiCall("delete", { id }, "notes");
    notes = notes.filter((n) => n.id !== id);
    renderNotes();
    showToast("已删除");
  } catch (e) {
    showToast("删除失败: " + e.message, "error");
  }
}

function getFilteredNotes() {
  if (!noteSearchQuery) return notes;
  return notes.filter(
    (n) =>
      n.title.toLowerCase().includes(noteSearchQuery) ||
      (n.content && n.content.toLowerCase().includes(noteSearchQuery))
  );
}

function renderNotes() {
  const list = document.getElementById("notes-list");
  const filtered = getFilteredNotes();
  let html = "";
  if (filtered.length === 0) {
    html = `<div class="empty">${noteSearchQuery ? "没有匹配的笔记" : "暂无笔记"}</div>`;
  } else {
    for (const n of filtered) html += noteCard(n);
  }
  list.innerHTML = html;
}

function noteCard(n) {
  const time = new Date(n.updated_at).toLocaleDateString("zh-CN", { month: "short", day: "numeric" });
  return `
    <div class="note-card" data-id="${n.id}" onclick="openNoteEditModal('${n.id}')">
      <div class="note-card-inner">
        <span class="note-card-title">${escapeHtml(n.title)}</span>
        <span class="note-card-time">${time}</span>
      </div>
      <button class="note-card-delete" onclick="event.stopPropagation(); deleteNote('${n.id}')">&times;</button>
    </div>`;
}

function exportNotes() {
  if (notes.length === 0) {
    showToast("没有笔记可导出", "error");
    return;
  }
  const blob = new Blob([JSON.stringify(notes, null, 2)], { type: "application/json" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `notes-${new Date().toISOString().slice(0, 10)}.json`;
  a.click();
  URL.revokeObjectURL(a.href);
  showToast("已导出 " + notes.length + " 条笔记");
}

function importNotes(file) {
  const reader = new FileReader();
  reader.onload = async (e) => {
    try {
      const imported = JSON.parse(e.target.result);
      if (!Array.isArray(imported)) {
        showToast("文件格式错误", "error");
        return;
      }
      let count = 0;
      for (const note of imported) {
        if (note.id && note.title) {
          note.updated_at = new Date().toISOString();
          await apiCall("upsert", note, "notes");
          count++;
        }
      }
      await loadNotes();
      showToast("已导入 " + count + " 条笔记");
    } catch (err) {
      showToast("导入失败: " + err.message, "error");
    }
  };
  reader.readAsText(file);
}

// --- Filter & Search ---

function setFilter(filter) {
  currentFilter = filter;
  document.querySelectorAll(".filter-tab").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.filter === filter);
  });
  renderTodos();
}

function setSearch(query) {
  searchQuery = query.toLowerCase().trim();
  renderTodos();
}

function getFilteredTodos() {
  let filtered = todos;

  if (currentFilter === "open") {
    filtered = filtered.filter((t) => isOpenVisibleTodo(t));
  } else if (currentFilter === "daily") {
    filtered = filtered.filter((t) => t.task_type === "daily" && isOpenVisibleTodo(t));
  } else if (currentFilter === "temporary") {
    filtered = filtered.filter((t) => t.task_type === "temporary" && isOpenVisibleTodo(t));
  } else if (currentFilter === "done") {
    filtered = filtered.filter((t) => t.status === "done" || isDailyCompletedToday(t));
  }

  if (searchQuery) {
    filtered = filtered.filter(
      (t) =>
        t.title.toLowerCase().includes(searchQuery) ||
        (t.description && t.description.toLowerCase().includes(searchQuery))
    );
  }

  return filtered;
}

// --- Render ---

function renderTodos() {
  const list = document.getElementById("todo-list");
  const filtered = getFilteredTodos();
  const openTodos = filtered.filter((t) => isOpenVisibleTodo(t));
  const doneTodos = filtered.filter((t) => t.status === "done" || isDailyCompletedToday(t));

  let html = "";
  if (currentFilter === "done") {
    if (doneTodos.length > 0) {
      html += `<div class="section-header">已完成 (${doneTodos.length})</div>`;
      for (const t of doneTodos) html += todoCard(t);
    }
  } else if (currentFilter === "all") {
    if (openTodos.length > 0) {
      html += `<div class="section-header">待办 (${openTodos.length})</div>`;
      for (const t of openTodos) html += todoCard(t);
    }
    if (doneTodos.length > 0) {
      html += `<div class="section-header done-header">已完成 (${doneTodos.length})</div>`;
      for (const t of doneTodos) html += todoCard(t);
    }
  } else {
    if (openTodos.length > 0) {
      for (const t of openTodos) html += todoCard(t);
    }
  }

  if (filtered.length === 0) {
    const msg = searchQuery ? "没有匹配的任务" : "暂无待办任务";
    html = `<div class="empty">${msg}</div>`;
  }
  list.innerHTML = html;
}

function todoCard(t) {
  const priorityClass = t.priority === "urgent" ? "urgent" : t.priority === "high" ? "high" : "";
  const typeLabel = t.task_type === "daily" ? "日常" : "临时";
  const isDone = t.status === "done" || isDailyCompletedToday(t);
  const doneClass = isDone ? "done" : "";
  const dueInfo = formatDueDate(t.due_at);
  const overdueClass = dueInfo.overdue && t.status === "open" ? "overdue" : "";

  let metaHtml = `<span class="tag">${typeLabel}</span><span class="tag">${priorityLabel(t.priority)}</span>`;
  if (dueInfo.text) {
    metaHtml += `<span class="tag due-tag${dueInfo.soon ? " soon" : ""}">${dueInfo.text}</span>`;
  }

  const descHtml = t.description ? `<span class="todo-desc">${escapeHtml(t.description)}</span>` : "";

  return `
    <div class="todo-card ${priorityClass} ${doneClass} ${overdueClass}" data-id="${t.id}">
      <div class="todo-main" onclick="toggleDone('${t.id}', '${t.status}')">
        <span class="checkbox">${isDone ? "✓" : ""}</span>
        <div class="todo-info">
          <span class="todo-title">${escapeHtml(t.title)}</span>
          ${descHtml}
          <div class="todo-meta">${metaHtml}</div>
        </div>
      </div>
      <button class="edit-btn" onclick="event.stopPropagation(); openEditModal('${t.id}')">✎</button>
      <button class="delete-btn" onclick="event.stopPropagation(); deleteTodo('${t.id}')">×</button>
    </div>`;
}

function formatDueDate(dueAt) {
  if (!dueAt) return { text: "", overdue: false, soon: false };
  const due = new Date(dueAt + "T23:59:59");
  const now = new Date();
  const diffMs = due.getTime() - now.getTime();
  const diffDays = Math.ceil(diffMs / (1000 * 60 * 60 * 24));

  if (diffDays < 0) return { text: `已过期${Math.abs(diffDays)}天`, overdue: true, soon: false };
  if (diffDays === 0) return { text: "今天截止", overdue: true, soon: false };
  if (diffDays === 1) return { text: "明天截止", overdue: false, soon: true };
  if (diffDays <= 3) return { text: `${diffDays}天后截止`, overdue: false, soon: true };
  return { text: `${dueAt.slice(5)} 截止`, overdue: false, soon: false };
}

function priorityLabel(p) {
  return { urgent: "紧急", high: "重要", normal: "普通", low: "低" }[p] || "普通";
}

function escapeHtml(s) {
  const div = document.createElement("div");
  div.textContent = s;
  return div.innerHTML;
}

// --- Daily Auto Complete ---

function localDateKey(date = new Date()) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function isAfterDailyAutoCompleteTime(date = new Date()) {
  const minutes = date.getHours() * 60 + date.getMinutes();
  return minutes >= DAILY_AUTO_COMPLETE_HOUR * 60 + DAILY_AUTO_COMPLETE_MINUTE;
}

function isDailyCompletedToday(todo, date = new Date()) {
  return todo.task_type === "daily" && todo.daily_completed_on === localDateKey(date);
}

function isOpenVisibleTodo(todo, date = new Date()) {
  return todo.status === "open" && !isDailyCompletedToday(todo, date);
}

function dailyCompletionUpdates(date = new Date()) {
  const now = date.toISOString();
  return {
    status: "open",
    completed_at: now,
    daily_completed_on: localDateKey(date),
    daily_skipped_on: null,
    snoozed_until: null,
    reminder_repeat_count: 0,
    updated_at: now,
  };
}

async function autoCompleteDailyTodos({ force = false } = {}) {
  if (dailyAutoCompleteInProgress) return;
  if (!navigator.onLine || !apiToken) return;
  const now = new Date();
  const today = localDateKey(now);
  if (!force && !isAfterDailyAutoCompleteTime(now)) return;
  if (localStorage.getItem(DAILY_AUTO_COMPLETE_LAST_KEY) === today) return;

  dailyAutoCompleteInProgress = true;
  try {
    const loaded = await loadTodos();
    if (!loaded) return;

    const dailyTodos = todos.filter(
      (todo) =>
        todo.task_type === "daily" &&
        todo.status === "open" &&
        todo.daily_completed_on !== today &&
        todo.daily_skipped_on !== today
    );
    if (dailyTodos.length === 0) {
      localStorage.setItem(DAILY_AUTO_COMPLETE_LAST_KEY, today);
      return;
    }

    const updates = dailyCompletionUpdates(now);
    let completed = 0;
    for (const todo of dailyTodos) {
      try {
        await apiCall("update", { id: todo.id, ...updates });
        Object.assign(todo, updates);
        notifiedTodoIds.delete(todo.id);
        completed++;
      } catch (e) {
        console.error("Daily auto-complete failed:", todo.id, e);
      }
    }

    renderTodos();
    if (completed === dailyTodos.length) {
      localStorage.setItem(DAILY_AUTO_COMPLETE_LAST_KEY, today);
      showToast(`已自动完成 ${completed} 个日常任务`);
    } else if (completed > 0) {
      showToast(`已自动完成 ${completed}/${dailyTodos.length} 个日常任务`, "error");
    }
  } finally {
    dailyAutoCompleteInProgress = false;
  }
}

function scheduleDailyAutoComplete() {
  if (dailyAutoCompleteTimer) {
    clearTimeout(dailyAutoCompleteTimer);
  }

  const now = new Date();
  const next = new Date(now);
  next.setHours(DAILY_AUTO_COMPLETE_HOUR, DAILY_AUTO_COMPLETE_MINUTE, 0, 0);
  if (next <= now) {
    next.setDate(next.getDate() + 1);
  }

  dailyAutoCompleteTimer = setTimeout(() => {
    autoCompleteDailyTodos({ force: true }).finally(scheduleDailyAutoComplete);
  }, next.getTime() - now.getTime());
}

// --- Toast ---

function showToast(msg, type = "success") {
  const toast = document.getElementById("toast");
  toast.textContent = msg;
  toast.className = "toast show " + type;
  setTimeout(() => (toast.className = "toast"), 2000);
}

// --- Edit Modal ---

function openEditModal(id) {
  const todo = todos.find((t) => t.id === id);
  if (!todo) return;
  document.getElementById("edit-id").value = todo.id;
  document.getElementById("edit-title").value = todo.title;
  document.getElementById("edit-desc").value = todo.description || "";
  document.getElementById("edit-type").value = todo.task_type || "temporary";
  document.getElementById("edit-priority").value = todo.priority || "normal";
  document.getElementById("edit-due").value = todo.due_at || "";
  document.getElementById("edit-modal").classList.add("open");
}

function closeEditModal() {
  document.getElementById("edit-modal").classList.remove("open");
}

async function saveEditModal() {
  const id = document.getElementById("edit-id").value;
  const title = document.getElementById("edit-title").value.trim();
  if (!title) {
    showToast("标题不能为空", "error");
    return;
  }
  const changes = {
    title,
    description: document.getElementById("edit-desc").value.trim(),
    task_type: document.getElementById("edit-type").value,
    priority: document.getElementById("edit-priority").value,
    due_at: document.getElementById("edit-due").value || null,
  };
  const ok = await updateTodo(id, changes);
  if (ok) closeEditModal();
}


// --- Note Edit Modal ---

function openNoteEditModal(id) {
  const note = notes.find((n) => n.id === id);
  if (!note) return;
  document.getElementById("note-edit-id").value = note.id;
  document.getElementById("note-edit-title").value = note.title;
  document.getElementById("note-edit-content").value = note.content || "";
  document.getElementById("note-modal").classList.add("open");
}

function closeNoteEditModal() {
  document.getElementById("note-modal").classList.remove("open");
}

async function saveNoteEditModal() {
  const id = document.getElementById("note-edit-id").value;
  const title = document.getElementById("note-edit-title").value.trim();
  if (!title) {
    showToast("标题不能为空", "error");
    return;
  }
  const changes = {
    title,
    content: document.getElementById("note-edit-content").value,
  };
  if (id) {
    await updateNote(id, changes);
    closeNoteEditModal();
  } else {
    await addNote(title, changes.content);
    closeNoteEditModal();
  }
}

function openNoteAddModal() {
  document.getElementById("note-edit-id").value = "";
  document.getElementById("note-edit-title").value = "";
  document.getElementById("note-edit-content").value = "";
  document.getElementById("note-modal").classList.add("open");
}

// --- Section Switching ---

function switchSection(section) {
  currentSection = section;
  document.querySelectorAll(".nav-tab").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.section === section);
  });
  document.getElementById("todo-section").style.display = section === "todos" ? "" : "none";
  document.getElementById("notes-section").style.display = section === "notes" ? "" : "none";
  if (section === "notes") renderNotes();
}

// --- Notifications ---

function setupNotificationUI() {
  if (!("Notification" in window)) return;
  const status = Notification.permission;
  if (status === "granted") return; // 已授权，不需要按钮
  const bar = document.getElementById("status-bar");
  if (!bar) return;
  if (status === "default") {
    const btn = document.createElement("button");
    btn.textContent = "🔔 开启提醒";
    btn.style.cssText = "margin-left:8px;background:var(--accent);color:white;border:none;border-radius:6px;padding:4px 10px;font-size:12px;cursor:pointer;";
    btn.onclick = () => {
      Notification.requestPermission().then((result) => {
        if (result === "granted") {
          btn.remove();
          showToast("提醒已开启");
        } else {
          btn.textContent = "已拒绝";
          btn.disabled = true;
        }
      });
    };
    bar.appendChild(btn);
  } else if (status === "denied") {
    const span = document.createElement("span");
    span.textContent = " · 通知被拒绝，请在浏览器设置中开启";
    span.style.color = "#f97316";
    bar.appendChild(span);
  }
}

function checkDueNotifications() {
  if (!("Notification" in window) || Notification.permission !== "granted") return;
  const now = new Date();
  for (const t of todos) {
    if (t.status !== "open" || !t.due_at || notifiedTodoIds.has(t.id)) continue;
    const due = new Date(t.due_at + "T23:59:59");
    const diffMs = due.getTime() - now.getTime();
    const diffHours = diffMs / (1000 * 60 * 60);
    if (diffHours <= 24) {
      let dueText = "";
      if (diffHours < 0) {
        dueText = `已过期${Math.abs(Math.ceil(diffHours / 24))}天`;
      } else if (diffHours < 1) {
        dueText = "即将截止";
      } else {
        dueText = `${Math.ceil(diffHours)}小时后截止`;
      }
      const title = "⏰ " + t.title;
      const body = dueText + " · " + (t.task_type === "daily" ? "日常任务" : "临时任务");
      try {
        if (navigator.serviceWorker) {
          navigator.serviceWorker.ready.then((reg) => {
            reg.showNotification(title, {
              body: body,
              tag: "due-" + t.id,
              renotify: true,
              requireInteraction: true,
            });
          });
        } else {
          new Notification(title, { body: body });
        }
      } catch (e) {
        console.error("Notification error:", e);
      }
      notifiedTodoIds.add(t.id);
    }
  }
}

// --- Status ---

function setStatus(text, color) {
  const bar = document.getElementById("status-bar");
  if (bar) {
    bar.textContent = text;
    bar.style.color = color || "#9b8fb8";
  }
}

// --- Init ---

let isOnline = navigator.onLine;
let pollTimer = null;

function startPolling() {
  if (pollTimer) return;
  pollTimer = setInterval(() => {
    if (!navigator.onLine) {
      goOffline();
      return;
    }
    Promise.all([loadTodos(), loadNotes()]).then(() => {
      checkDueNotifications();
      autoCompleteDailyTodos();
      const now = new Date();
      const t = now.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
      setStatus("已连接 · " + t, "#22c55e");
    }).catch(() => {});
  }, 5000);
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
}

function goOffline() {
  isOnline = false;
  stopPolling();
  setStatus("已离线，等待网络恢复...", "#f97316");
}

function goOnline() {
  isOnline = true;
  setStatus("正在重新连接...", "#f97316");
  Promise.all([loadTodos(), loadNotes()])
    .then(() => {
      autoCompleteDailyTodos();
      const now = new Date();
      const t = now.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
      setStatus("已连接 · " + t, "#22c55e");
    })
    .catch(() => setStatus("连接失败", "#ef4444"));
  startPolling();
}

function initApp() {
  window.addEventListener("offline", goOffline);
  window.addEventListener("online", goOnline);

  if (!navigator.onLine) {
    goOffline();
  } else {
    setStatus("正在连接...", "#f97316");
    Promise.all([loadTodos(), loadNotes()])
      .then(() => {
        checkDueNotifications();
        autoCompleteDailyTodos();
        setStatus("已连接", "#22c55e");
      })
      .catch(() => setStatus("连接失败", "#ef4444"));
    startPolling();
  }

  setupForm();
  setupUI();
  setupNotesUI();
  setupNotificationUI();
  setupDailyAutoComplete();

  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("./sw.js");
  }
}

function setupDailyAutoComplete() {
  scheduleDailyAutoComplete();
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) {
      autoCompleteDailyTodos();
      scheduleDailyAutoComplete();
    }
  });
}

document.addEventListener("DOMContentLoaded", () => {
  loadSupabaseConfig();
  apiToken = getStoredToken();

  if (SUPABASE_URL && SUPABASE_KEY && apiToken) {
    hideTokenScreen();
    initApp();
  } else {
    showTokenScreen();
  }

  document.getElementById("token-submit").addEventListener("click", handleTokenSubmit);
  document.getElementById("token-input").addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      handleTokenSubmit();
    }
  });
});

function setupForm() {
  const form = document.getElementById("add-form");
  const input = document.getElementById("todo-input");
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    const taskType = document.getElementById("task-type").value;
    const priority = document.getElementById("priority").value;
    const dueDate = document.getElementById("due-date").value || null;
    addTodo(input.value, taskType, priority, dueDate);
    input.value = "";
    document.getElementById("due-date").value = "";
    input.focus();
  });
}

function setupUI() {
  document.querySelectorAll(".filter-tab").forEach((btn) => {
    btn.addEventListener("click", () => setFilter(btn.dataset.filter));
  });
  const searchInput = document.getElementById("search-input");
  let debounce = null;
  searchInput.addEventListener("input", () => {
    clearTimeout(debounce);
    debounce = setTimeout(() => setSearch(searchInput.value), 200);
  });
  document.getElementById("modal-close").addEventListener("click", closeEditModal);
  document.getElementById("modal-cancel").addEventListener("click", closeEditModal);
  document.getElementById("modal-save").addEventListener("click", saveEditModal);
  document.getElementById("edit-modal").addEventListener("click", (e) => {
    if (e.target === document.getElementById("edit-modal")) closeEditModal();
  });
}

function setupNotesUI() {
  document.querySelectorAll(".nav-tab").forEach((btn) => {
    btn.addEventListener("click", () => switchSection(btn.dataset.section));
  });
  document.getElementById("note-add-btn").addEventListener("click", openNoteAddModal);
  document.getElementById("note-modal-close").addEventListener("click", closeNoteEditModal);
  document.getElementById("note-modal-cancel").addEventListener("click", closeNoteEditModal);
  document.getElementById("note-modal-save").addEventListener("click", saveNoteEditModal);
  document.getElementById("note-modal").addEventListener("click", (e) => {
    if (e.target === document.getElementById("note-modal")) closeNoteEditModal();
  });
  document.getElementById("note-export-btn").addEventListener("click", exportNotes);
  document.getElementById("note-import-input").addEventListener("change", (e) => {
    if (e.target.files[0]) importNotes(e.target.files[0]);
    e.target.value = "";
  });
  const noteSearchInput = document.getElementById("note-search-input");
  let noteDebounce = null;
  noteSearchInput.addEventListener("input", () => {
    clearTimeout(noteDebounce);
    noteDebounce = setTimeout(() => {
      noteSearchQuery = noteSearchInput.value.toLowerCase().trim();
      renderNotes();
    }, 200);
  });
}
