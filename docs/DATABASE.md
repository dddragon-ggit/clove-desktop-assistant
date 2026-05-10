# 数据库架构文档

本文档记录项目的 Supabase 数据库结构、建表语句和迁移步骤，方便后期维护或迁移到其他数据库。

## 概览

项目使用 Supabase（PostgreSQL）作为云端数据库，包含两张表：

| 表名 | 用途 | 主要使用者 |
|------|------|-----------|
| `todos` | 待办任务 | 桌面端 + PWA |
| `notes` | 记事本笔记 | PWA |

## 安全模型

- **RLS（Row Level Security）** 已启用，策略为 `allow_all`
- 实际安全由 **Edge Function 的 API Token** 保证，不依赖 RLS
- 桌面端使用 `service_role` key 直连（绕过 RLS）
- PWA 通过 Edge Function 中转（也绕过 RLS）

## 建表 SQL

在 Supabase Dashboard → SQL Editor 中执行：

### todos 表

```sql
CREATE TABLE IF NOT EXISTS todos (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL DEFAULT '',
  description TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'open',          -- 'open' | 'done'
  priority TEXT NOT NULL DEFAULT 'normal',      -- 'low' | 'normal' | 'high' | 'urgent'
  task_type TEXT NOT NULL DEFAULT 'temporary',  -- 'daily' | 'temporary'
  important BOOLEAN NOT NULL DEFAULT false,
  needs_computer BOOLEAN NOT NULL DEFAULT false,
  due_at DATE,                                  -- 截止日期
  reminder_at TIMESTAMPTZ,                      -- 提醒时间
  snoozed_until TIMESTAMPTZ,                    -- 延后到
  daily_completed_on TEXT,                      -- 日常任务完成日期标记
  daily_skipped_on TEXT,                        -- 日常任务跳过日期标记
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  completed_at TIMESTAMPTZ,                     -- 完成时间
  device_id TEXT                                -- 创建设备标识（历史字段，不再用于过滤）
);

-- 按状态和更新时间查询
CREATE INDEX IF NOT EXISTS idx_todos_status ON todos(status);
CREATE INDEX IF NOT EXISTS idx_todos_updated_at ON todos(updated_at DESC);

-- RLS
ALTER TABLE todos ENABLE ROW LEVEL SECURITY;
CREATE POLICY allow_all ON todos FOR ALL USING (true) WITH CHECK (true);
```

### notes 表

```sql
CREATE TABLE IF NOT EXISTS notes (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL DEFAULT '',
  content TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 按更新时间排序
CREATE INDEX IF NOT EXISTS idx_notes_updated_at ON notes(updated_at DESC);

-- RLS
ALTER TABLE notes ENABLE ROW LEVEL SECURITY;
CREATE POLICY allow_all ON notes FOR ALL USING (true) WITH CHECK (true);
```

## Edge Function

`supabase/functions/todos-api/index.ts` 是唯一的 Edge Function，负责：

1. 验证 `X-API-Token` 请求头
2. 根据 `table` 参数路由到 `todos` 或 `notes` 表
3. 支持 5 种操作：`select`、`insert`、`update`、`delete`、`upsert`

请求格式：
```json
{
  "action": "select | insert | update | delete | upsert",
  "data": { ... },
  "table": "todos | notes"
}
```

### 环境变量

在 Supabase Dashboard → Edge Functions → Settings 中配置：

| 变量名 | 说明 |
|--------|------|
| `API_TOKEN` | 共享访问令牌，PWA 前端输入此值才能调用 API |
| `SUPABASE_URL` | 自动注入，无需手动设置 |
| `SUPABASE_SERVICE_ROLE_KEY` | 自动注入，无需手动设置 |

## 数据流架构

```
┌──────────┐     service_role key      ┌──────────────┐
│  桌面端   │ ─────────────────────────→│              │
│ PySide6  │    Supabase REST API      │  Supabase    │
└──────────┘                           │ (PostgreSQL) │
                                       │              │
┌──────────┐    X-API-Token 验证       │  todos 表    │
│   PWA    │ ──→ Edge Function ───────→│  notes 表    │
│  手机端  │                           │              │
└──────────┘                           └──────────────┘
```

## 迁移到其他数据库

### 迁移到自建 PostgreSQL

最简单的迁移方式，几乎零改动：

1. 在新 PostgreSQL 实例上执行上述建表 SQL
2. 修改桌面端的 Supabase 连接配置（`runtime/data/supabase_config.json`）
3. 重写 Edge Function 为普通 HTTP 服务（或让 PWA 直连）

### 迁移到其他 SQL 数据库（MySQL / SQLite 等）

需要调整：

| 差异点 | PostgreSQL | MySQL / SQLite |
|--------|-----------|----------------|
| 时间类型 | `TIMESTAMPTZ` | `DATETIME` / `TEXT` |
| 布尔类型 | `BOOLEAN` | `TINYINT(1)` / `INTEGER` |
| JSON 操作 | `->>` / `jsonb` | `JSON_EXTRACT` / 无 |
| 自增主键 | `gen_random_uuid()` | `AUTO_INCREMENT` / `AUTOINCREMENT` |

### 迁移到 NoSQL（Firebase / MongoDB 等）

数据模型需要重新设计，建议按 collection / document 结构规划。

## 备份与导出

Supabase 提供自动备份（Pro 计划），也可手动导出：

```bash
# 使用 Supabase CLI 导出
npx supabase db dump --project-ref <ref> > backup.sql

# 或直接用 pg_dump
pg_dump "postgresql://..." > backup.sql
```

PWA 端笔记支持 JSON 导出/导入（在记事本界面点击导出按钮）。
