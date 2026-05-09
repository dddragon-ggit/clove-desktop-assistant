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
let currentFilter = "all";
let searchQuery = "";
let apiToken = "";

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

async function apiCall(action, data = {}) {
  const resp = await fetch(EDGE_FUNCTION_URL, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Authorization": `Bearer ${SUPABASE_KEY}`,
      "X-API-Token": apiToken,
    },
    body: JSON.stringify({ action, data }),
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
  } catch (e) {
    showToast("加载失败: " + e.message, "error");
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
    const todo = todos.find((t) => t.id === id);
    if (todo) Object.assign(todo, updates);
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
    renderTodos();
    showToast("已删除");
  } catch (e) {
    showToast("删除失败: " + e.message, "error");
  }
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
    filtered = filtered.filter((t) => t.status === "open");
  } else if (currentFilter === "daily") {
    filtered = filtered.filter((t) => t.task_type === "daily" && t.status === "open");
  } else if (currentFilter === "temporary") {
    filtered = filtered.filter((t) => t.task_type === "temporary" && t.status === "open");
  } else if (currentFilter === "done") {
    filtered = filtered.filter((t) => t.status === "done");
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
  const openTodos = filtered.filter((t) => t.status === "open");
  const doneTodos = filtered.filter((t) => t.status === "done");

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
  const doneClass = t.status === "done" ? "done" : "";
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
        <span class="checkbox">${t.status === "done" ? "✓" : ""}</span>
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

// --- Status ---

function setStatus(text, color) {
  const bar = document.getElementById("status-bar");
  if (bar) {
    bar.textContent = text;
    bar.style.color = color || "#9b8fb8";
  }
}

// --- Init ---

function initApp() {
  setStatus("正在连接...", "#f97316");
  loadTodos()
    .then(() => setStatus("已连接", "#22c55e"))
    .catch(() => setStatus("连接失败", "#ef4444"));

  // Poll for changes every 5 seconds (Realtime blocked by RLS)
  setInterval(() => {
    loadTodos().then(() => {
      const now = new Date();
      const t = now.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
      setStatus("已连接 · " + t, "#22c55e");
    });
  }, 5000);

  setupForm();
  setupUI();

  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("./sw.js");
  }
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
