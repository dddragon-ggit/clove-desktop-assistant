# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Desktop Assistant is a Windows desktop companion app built with Python + PySide6 + SQLite. It provides todo management, workspace preparation (opening apps/files/URLs), activity tracking, and AI-powered planning/reviewing via an OpenAI-compatible API. The primary entry is a floating shell widget (right-upper corner) that minimizes to an animated desktop orb (Mudie pet).

## Build & Run Commands

Python environment: `D:\anaconda3\envs\app\python.exe` (conda `app` env, Python 3.12+)

```powershell
# Run the UI app
python -m desktop_assistant.ui

# Run CLI dry-run mode
python -m desktop_assistant --mode dry_run --request "打开 QQ" --storage sqlite --ai-backend fake
python -m desktop_assistant --mode dry_run --request "打开 QQ" --storage sqlite --ai-backend real

# Compile check (fast)
python -m compileall -q desktop_assistant tests

# Run all tests
python -m unittest discover -s tests -v

# Run a single test module
python -m unittest tests.test_todo -v
python -m unittest tests.test_ui_shell -v

# Run targeted test subsets
python -m unittest tests.test_ui_shell tests.test_ui_workspace_plan tests.test_ui_execution_feedback -v
python -m unittest tests.test_windows_executor tests.test_openai_responses -v
python -m unittest tests.test_provider_adapter -v

# Quality evaluation (dry-run, no real desktop actions)
python -m desktop_assistant.tools.real_smoke --ai-backend real
python -m desktop_assistant.tools.quality_eval --ai-backend real
```

## Architecture

### Core Pipeline (orchestrator)

`WorkflowOrchestrator` drives the main loop: **Context → Planner → Policy → Reviewer → Executor**. Each step is an injectable protocol defined in [protocols.py](desktop_assistant/protocols.py). The orchestrator supports `dry_run`, `normal`, and `step_by_step` modes, and generates a `trace_id` for every run.

- **Planner**: Translates natural language requests into structured `ActionPlan` (list of `ActionStep`).
- **Policy**: Hard safety boundary — validates action types, risk levels, blocks forbidden actions. Higher priority than AI.
- **Reviewer**: Second AI pass — checks plan against user intent and risk. Can reject but cannot override policy.
- **Executor**: Executes or simulates `ActionStep`s. `WindowsExecutor` handles real desktop actions.

### Adapter Layer (`adapters/`)

All external integrations are isolated here:
- `fake_planner.py`, `fake_reviewer.py`, `fake_executor.py` — simulation adapters for development
- `openai_responses.py`, `openai_planner.py`, `openai_reviewer.py` — real AI via OpenAI-compatible `responses` API
- `anthropic_client.py` — Anthropic Messages API client (same `create_json_response` interface as OpenAI client)
- `provider_factory.py` — Factory with `create_client(config)` routing and `auto_detect_wire_api()` probing
- `windows_executor.py` + `windows_app_handlers.py` / `windows_file_actions.py` / `windows_window_actions.py` — real Windows desktop actions
- `windows_app_discovery.py` — app scanning, caching, and inventory (`runtime/data/app_inventory.json`)
- `web_query.py` — DuckDuckGo + weather queries for `answer_query` capability

#### Provider Adapter Pattern

Both `OpenAIResponsesClient` and `AnthropicClient` implement the same `create_json_response()` interface (formalized as `LLMClient` protocol in `provider_factory.py`). The factory selects the right client based on `config.wire_api` (`"responses"` or `"anthropic"`). Use `auto_detect_wire_api(config)` to probe which format a provider endpoint supports.

Key differences:
- **OpenAI**: `Authorization: Bearer` header, `/v1/responses` endpoint, native JSON schema via `text.format`
- **Anthropic**: `x-api-key` header, `/v1/messages` endpoint, `system` as top-level field, `max_tokens` required, JSON schema embedded in system prompt

The UI has a "模型设置" page in the menu for configuring providers with auto-detect and test-connection features.

### Domain Modules

| Module | Purpose |
|---|---|
| `todo/` | Real todo CRUD, reminders, snooze, daily/temporary task types, urgency colors |
| `sync/` | Supabase cloud sync — push/pull/full-sync for todo items between desktop and mobile |
| `workspace/` | Generates `WorkspaceSuggestion` from goals/todos/activity; supports refine and recipes |
| `activity/` | Non-invasive activity sensing (foreground app, window title, file, project). Privacy boundary: no keyboard/screen/content reading |
| `habits/` | Daily behavior logs, 14-day retention, next-action prediction |
| `input_router/` | Routes homepage input to todo/workspace/continue/dialog pages |
| `confirmation/` | Action-level confirmation flow (reject / this-time / permanent trust) |
| `capability/` | Capability registry, risk validation, handler dispatch |
| `recipe/` | Saveable workspace plans (WorkflowRecipe) |
| `ui_state/` | Persists orb/panel position, size, transparency, stealth mode |
| `projects/` | Local project/folder discovery and matching |

### Storage (`storage/`)

- **SQLite** (`runtime/data/desktop_assistant.db`): Primary storage for workflow traces, todo items, workspace drafts, workflow recipes. Uses WAL mode and schema migrations.
- **JSON**: Atomic-write JSON files for config, activity, privacy, ui_state, prediction. Supports corrupt-file isolation (`*.corrupt`) with auto-recovery.
- Provider config: `runtime/data/model_provider.json` (stores API key, base URL, model name)

### UI (`ui/`)

PySide6 Qt Widgets. Key structure:
- `shell_window.py` — Top-level shell window, drag/resize, orb/panel mode switching
- `shell_orb.py` — Transparent animated orb (current: sound-wave capsules with double-ring border)
- `shell_controller.py` — Thin control layer connecting UI to backend services
- `shell_todo.py` / `shell_workspace_flow.py` / `shell_workspace_confirm.py` — Page-specific interaction flows
- `shell_pages.py` + helpers — Page dispatch and layout builders
- `shell_styles.py` — Mudie theme (purple-gray base, blue-pink accents)
- `desktop_pet_window.py` — Mudie desktop pet with bubble menus, drag animations, reminder bubbles
- `localization.py` — Maps internal English protocol values to Chinese display text
- `execution_feedback.py` / `execution_remedies.py` — Human-readable execution results and failure recovery

### Prompts (`prompts/`)

System prompts for Planner (`planner_system.txt`) and Reviewer (`reviewer_system.txt`). Prompt templates are loaded via `prompting/` module with app inventory context injection.

## Maintenance Rule

**CLAUDE.md is a living document.** Update it whenever the project changes or progresses — new modules, architecture shifts, command changes, test count milestones, or resolved blockers. This ensures future Claude sessions can pick up seamlessly. Modifications to this file do not require user confirmation.

## Recent Bug Fixes (2026-05-05)

A comprehensive code audit found 21 bugs. All 21 bugs (Critical through Low) were fixed.

**Critical fixes:**
- `storage/json_files.py` — Removed dead `quarantine_corrupted_file` overload that was silently overwritten
- `adapters/windows_window_manager.py` — `find_by_hwnd` now accepts `require_visible` param; `focus_window` checks `SetForegroundWindow` return value

**High fixes:**
- `adapters/windows_app_handlers.py` — `OpenAppHandler` tries all launch targets before reporting failure
- `adapters/windows_window_models.py` / `windows_window_null.py` / `windows_window_actions.py` — Updated `find_by_hwnd` protocol to include `require_visible` param

**Medium fixes:**
- `core/policy.py` — `CRITICAL` risk now requires confirmation; `_highest_step_risk` uses effective risk from capability registry
- `core/orchestrator_recovery.py` — Recovery policy re-evaluation uses recovery planner's risk guess
- `adapters/openai_client.py` — Fallback API body now includes `reasoning` and `text.format` for structured output
- `todo/models.py` — `is_daily_completed_today`/`is_daily_skipped_today` accept `daily_reset_hour` and use `logical_local_date` from `reminder_settings`
- `todo/store.py` — `mark_done`/`skip_daily_today` fallback dates use `logical_local_date` with default reset hour
- `workspace/service.py` — `recipe_as_suggestion` uses deterministic UUID (uuid5) to prevent duplicate drafts
- `ui/shell_window.py` / `ui/shell_todo.py` / `ui/shell_workspace_confirm.py` — Added concurrent worker guards (`worker_thread.isRunning()`)
- `ui/shell_workspace_confirm.py` — Removed redundant `release_pet_hold`/`trigger_pet_action` calls

**Low fixes:**
- `adapters/openai_responses.py` — Removed unused imports from `openai_planner_helpers`
- `todo/models.py` — Removed duplicate `_logical_local_date`, now uses lazy import from `reminder_settings`
- `storage/in_memory.py` — `save_debug_run` type annotation changed from `Any` to `DebugRunRecord`
- `adapters/fake.py` / `windows_app_discovery.py` / `web_query.py` — Removed private `_`-prefixed names from `__all__`
- `todo/store.py` / `workspace/drafts.py` / `recipe/store.py` — Added `sqlite3.Connection` type annotations to `connection` params
- `workspace/service.py` — Added `ActionStep` type annotation to `_resource_from_step`
- `adapters/fake_planner.py` — Replaced `assert` with `if/raise` in production code
- `habits/journal.py` — `_last_activity_line` now reads file line-by-line instead of loading entire file

## Recent Feature: Multi-Provider AI Adapter Layer (2026-05-09)

Added support for both OpenAI Responses API and Anthropic Messages API providers. The adapter layer auto-detects which format a provider endpoint supports. Key files:
- `adapters/anthropic_client.py` — Anthropic Messages API client
- `adapters/provider_factory.py` — Factory with `create_client()`, `auto_detect_wire_api()`, `probe_provider()`
- `ui/shell_provider_pages.py` — Provider settings UI page ("模型设置") with auto-detect and test-connection
- `tests/test_provider_adapter.py` — 17 tests covering both clients and the factory

Both clients share the `LLMClient` protocol with identical `create_json_response()` interface. `RealPlanner` and `RealReviewer` accept any `LLMClient` implementation.

## Recent Feature: Todo List Task Type Separation (2026-05-06)

The todo list page now visually separates daily tasks and temporary tasks with section headers. Daily tasks appear first under a "每日日常" header, followed by temporary tasks under a "临时任务" header. Section headers are non-selectable and styled with the `sectionLabel` theme. Helper methods `_todo_item_count()`, `_todo_item_at()`, and `_todo_actual_row()` provide logical-index access that skips section headers.

## Key Constraints

- **Single file limit**: Keep Python files under ~400 lines. Split into sub-modules when approaching this limit.
- **Root directory discipline**: Prefer adding new code to domain sub-packages. Root-level files are thin facades (re-export only).
- **Fake/Real dual backend**: All AI-dependent code must work with both `fake` and `real` adapters. Use `--ai-backend fake|real` to switch.
- **Safety boundary**: Policy engine is the final hard boundary. AI cannot override it. `Critical` actions are always blocked. No shell execution, file deletion, or system modification.
- **Activity privacy**: `activity/` only reads metadata (app name, window title, file path, project). Never reads keyboard, clipboard, screen, file content, or web content.
- **JSON atomicity**: All local JSON stores use temp-file + `os.replace()` atomic writes.
- **SQLite migrations**: Schema changes go through `storage/sqlite.py` migration system with `schema_migrations` history table.

## Testing Patterns

- Tests use `unittest` (no pytest). Test files are in `tests/` with `__init__.py`.
- UI tests mock backend services but use real Qt widgets where possible.
- Quality evaluation tools (`tools/quality_eval.py`, `tools/execution_eval.py`) run dry-run rounds to verify Planner/Reviewer stability.
- Full test suite has 335+ tests. UI tests can be slow with Qt cleanup; running individual test modules is faster for iteration.

## Real Provider Setup

The real AI backend uses an OpenAI-compatible `responses` API. Config is loaded from:
1. Environment variables: `DESKTOP_ASSISTANT_API_KEY`, `DESKTOP_ASSISTANT_BASE_URL`, `DESKTOP_ASSISTANT_MODEL`
2. Fallback: `runtime/data/model_provider.json`

Never print or commit full API keys. Use `ProviderConfigStore().describe()` to check config status (returns masked key only).

## Supabase Sync (Mobile ↔ Desktop)

The `sync/` module provides cloud sync via Supabase (PostgreSQL). Config is stored in `runtime/data/supabase_config.json`:
```json
{"url": "https://xxx.supabase.co", "key": "sb_publishable_...", "enabled": true}
```

- `SupabaseSyncService` handles push/pull/full-sync of `TodoItem`s
- `device_id` stored in `runtime/data/device_id.txt` prevents sync loops
- Conflict resolution: last-write-wins on `updated_at`
- Desktop UI auto-syncs on startup and after each todo mutation
- Supabase table: `todos` with RLS enabled, `allow_all` policy

### PWA Mobile Client (`mobile/`)

Lightweight PWA for adding todos on the phone. Uses Supabase JS client (CDN) + Realtime for live updates.

```powershell
# Local test (same WiFi network)
python mobile/serve.py
# Open http://<local-ip>:8080 on phone
```

Files: `index.html`, `app.js`, `sw.js`, `manifest.json`, `serve.py`

#### PWA 连接排查

手机无法访问 PWA 时，按顺序排查：

1. **WiFi 网络**：手机和电脑必须在同一局域网（同一路由器 WiFi 或电脑连手机热点均可）
2. **Windows 防火墙**：默认阻止 8080 端口入站，需手动添加规则：
   ```powershell
   # 以管理员身份运行 PowerShell
   netsh advfirewall firewall add rule name="PWA Server 8080" dir=in action=allow protocol=TCP localport=8080
   ```
   验证：`netsh advfirewall firewall show rule name="PWA Server 8080"`
3. **手机热点 AP 隔离**：部分手机热点默认禁止连接设备间通信（AP isolation）。如果电脑通过手机热点上网，手机反而无法访问电脑 — 换用同一路由器 WiFi 即可
