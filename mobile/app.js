const SUPABASE_URL = "https://hqrzqipukyqyactkigga.supabase.co";
const SUPABASE_KEY = "sb_publishable_UhiGJpbt_8Fu4RmvESz0aw_b2J5er8c";

let client = null;
let todos = [];
let deviceId = "";

function initDeviceId() {
  let id = localStorage.getItem("device_id");
  if (!id) {
    id = "mobile-" + Math.random().toString(36).slice(2, 14);
    localStorage.setItem("device_id", id);
  }
  deviceId = id;
}

function initSupabase() {
  if (typeof supabase === "undefined") {
    showToast("Supabase JS 加载失败，请检查网络", "error");
    return false;
  }
  try {
    client = supabase.createClient(SUPABASE_URL, SUPABASE_KEY);
    return true;
  } catch (e) {
    showToast("Supabase 连接失败: " + e.message, "error");
    return false;
  }
}

async function loadTodos() {
  if (!client) return;
  try {
    const { data, error } = await client
      .from("todos")
      .select("*")
      .order("created_at", { ascending: false });
    if (error) {
      showToast("加载失败: " + error.message, "error");
      return;
    }
    todos = data || [];
    renderTodos();
  } catch (e) {
    showToast("网络错误: " + e.message, "error");
  }
}

async function addTodo(title, taskType, priority) {
  if (!client || !title.trim()) return;
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
      created_at: now,
      updated_at: now,
      device_id: deviceId,
    };
    const { error } = await client.from("todos").upsert(todo);
    if (error) {
      showToast("添加失败: " + error.message, "error");
      return;
    }
    todos.unshift(todo);
    renderTodos();
    showToast("已添加并同步");
  } catch (e) {
    showToast("网络错误: " + e.message, "error");
  }
}

async function toggleDone(id, currentStatus) {
  if (!client) return;
  const now = new Date().toISOString();
  const newStatus = currentStatus === "done" ? "open" : "done";
  const updates = {
    status: newStatus,
    updated_at: now,
    device_id: deviceId,
  };
  if (newStatus === "done") {
    updates.completed_at = now;
  } else {
    updates.completed_at = null;
  }
  const { error } = await client.from("todos").update(updates).eq("id", id);
  if (error) {
    console.error("Toggle failed:", error);
    return;
  }
  const todo = todos.find((t) => t.id === id);
  if (todo) {
    Object.assign(todo, updates);
  }
  renderTodos();
}

async function deleteTodo(id) {
  if (!client) return;
  if (!confirm("确定删除？")) return;
  const { error } = await client.from("todos").delete().eq("id", id);
  if (error) {
    console.error("Delete failed:", error);
    return;
  }
  todos = todos.filter((t) => t.id !== id);
  renderTodos();
  showToast("已删除");
}

function renderTodos() {
  const list = document.getElementById("todo-list");
  const openTodos = todos.filter((t) => t.status === "open");
  const doneTodos = todos.filter((t) => t.status === "done");

  let html = "";
  if (openTodos.length > 0) {
    html += `<div class="section-header">待办 (${openTodos.length})</div>`;
    for (const t of openTodos) {
      html += todoCard(t);
    }
  }
  if (doneTodos.length > 0) {
    html += `<div class="section-header done-header">已完成 (${doneTodos.length})</div>`;
    for (const t of doneTodos) {
      html += todoCard(t);
    }
  }
  if (todos.length === 0) {
    html = '<div class="empty">暂无待办任务</div>';
  }
  list.innerHTML = html;
}

function todoCard(t) {
  const priorityClass = t.priority === "urgent" ? "urgent" : t.priority === "high" ? "high" : "";
  const typeLabel = t.task_type === "daily" ? "日常" : "临时";
  const doneClass = t.status === "done" ? "done" : "";
  return `
    <div class="todo-card ${priorityClass} ${doneClass}" data-id="${t.id}">
      <div class="todo-main" onclick="toggleDone('${t.id}', '${t.status}')">
        <span class="checkbox">${t.status === "done" ? "✓" : ""}</span>
        <div class="todo-info">
          <span class="todo-title">${escapeHtml(t.title)}</span>
          <span class="todo-meta">${typeLabel} · ${priorityLabel(t.priority)}</span>
        </div>
      </div>
      <button class="delete-btn" onclick="event.stopPropagation(); deleteTodo('${t.id}')">×</button>
    </div>`;
}

function priorityLabel(p) {
  return { urgent: "紧急", high: "重要", normal: "普通", low: "低" }[p] || "普通";
}

function escapeHtml(s) {
  const div = document.createElement("div");
  div.textContent = s;
  return div.innerHTML;
}

function showToast(msg, type = "success") {
  const toast = document.getElementById("toast");
  toast.textContent = msg;
  toast.className = "toast show " + type;
  setTimeout(() => (toast.className = "toast"), 2000);
}

function setupForm() {
  const form = document.getElementById("add-form");
  const input = document.getElementById("todo-input");
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    const taskType = document.getElementById("task-type").value;
    const priority = document.getElementById("priority").value;
    addTodo(input.value, taskType, priority);
    input.value = "";
    input.focus();
  });
}

function setupRealtime() {
  if (!client) return;
  client
    .channel("todos-changes")
    .on("postgres_changes", { event: "*", schema: "public", table: "todos" }, (payload) => {
      const row = payload.new || payload.old;
      if (!row) return;
      if (row.device_id === deviceId) return;
      if (payload.eventType === "INSERT") {
        if (!todos.find((t) => t.id === row.id)) {
          todos.unshift(row);
        }
      } else if (payload.eventType === "UPDATE") {
        const idx = todos.findIndex((t) => t.id === row.id);
        if (idx >= 0) todos[idx] = row;
        else todos.unshift(row);
      } else if (payload.eventType === "DELETE") {
        todos = todos.filter((t) => t.id !== row.id);
      }
      renderTodos();
    })
    .subscribe();
}

function setStatus(text, color) {
  const bar = document.getElementById("status-bar");
  if (bar) {
    bar.textContent = text;
    bar.style.color = color || "#9b8fb8";
  }
}

document.addEventListener("DOMContentLoaded", () => {
  initDeviceId();
  if (typeof supabase === "undefined") {
    setStatus("错误：Supabase JS 未加载，请检查网络", "#ef4444");
    setupForm();
    return;
  }
  try {
    client = supabase.createClient(SUPABASE_URL, SUPABASE_KEY);
    setStatus("已连接 Supabase，正在加载...", "#22c55e");
    loadTodos();
    setupRealtime();
  } catch (e) {
    setStatus("连接失败: " + e.message, "#ef4444");
  }
  setupForm();
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("./sw.js");
  }
});
