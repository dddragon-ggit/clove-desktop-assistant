# Overnight Progress - 2026-04-29

## Completed Without User Permission

- Added execution observability:
  - `WorkflowTrace.timings`
  - per-step `elapsed_seconds`
  - per-step `metadata`
  - debug snapshots now show timings, metadata, failure details, and remedies.
- Added window/app state foundation:
  - new `list_windows` action type
  - `windows.list_windows` capability and handler
  - visible-window metadata returned in execution results.
- Strengthened app execution diagnostics:
  - launch attempts are included in failure details
  - process-running-without-window is separated from launch-not-verified
  - local app failures skip slow model recovery to avoid retry loops.
- Added capability diagnostics:
  - UI capability detail now shows handler status, handler availability, recent failure count, latest failure code, trace id, message, and remedy
  - new `desktop_assistant.tools.capability_debug` report tool.
- Improved information query results:
  - successful answers include `strategy`, `confidence`, `sources`, `source_count`, and `fallback_url`
  - failed lookups include structured `transport_error` or `no_direct_answer` metadata.
- Added project discovery foundation:
  - `discover_project_locations`
  - `ProjectCatalogStore.refresh_discovered`
  - UI `Discover` button for merging detected project roots into `projects.json`.
- Fixed fake planner quality:
  - local app wording like `打开微信应用 / 打开 Cursor 应用 / 打开战网应用` now plans `open_app`
  - unsafe shell/delete requests are rejected instead of converted into filler tasks.

## Verified

- `python -m unittest tests.test_web_query -v`: passed.
- `python -m unittest tests.test_ui_view_model tests.test_capability_debug -v`: passed.
- `python -m unittest tests.test_project_locator -v`: passed.
- `python -m unittest tests.test_orchestrator tests.test_quality_eval -v`: passed.
- `python -m desktop_assistant.tools.capability_debug`: ran successfully; current catalog reports 12 capabilities, 11 enabled, 0 missing handlers, 3 recent recorded failures.
- `python -m desktop_assistant.tools.quality_eval --ai-backend fake`: 9/9 quality cases passed.

## Needs User Permission Or Real Environment Tomorrow

- Real UI/GUIs were not reopened overnight, because opening apps or browsers needs permission while you are present.
- Real provider quality suite was not re-run overnight, because it can make external API/network requests.
- Real `answer_query` network behavior still needs live checks for weather/gold/current-info cases.
- Two temporary test directories from an earlier failed run could not be removed due Windows access denial:
  - `runtime/test_projects/tmp84b_ydaa`
  - `runtime/test_projects/tmpy0k9f50q`

## Next Best Checks

- Run full unit test discovery after all overnight edits.
- With permission, run real UI checks:
  - open QQ
  - open Battle.net
  - open Cursor
  - open a website
  - query weather/gold price through `answer_query`.
- Run real planner/reviewer quality eval and compare against fake 9/9 baseline.

## Deferred Product Backlog

- Productize the recipe system later:
  - goal -> generated plan -> user refinement input -> regenerated plan -> confirmation -> saved reusable recipe.
  - Improve recipe UX beyond the current save/edit/replay foundation.
