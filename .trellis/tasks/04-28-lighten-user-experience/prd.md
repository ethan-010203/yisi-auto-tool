# Brainstorm: Make Tool UI Lighter For Users

## Goal

Review the current project from an end-user perspective and identify changes that make the automation tool feel lighter, faster to understand, and easier to operate without losing necessary configuration, preview, and execution feedback.

## What I Already Know

* The user feels the current project is somewhat heavy/cumbersome to use.
* The app is a Vue 3 + Vite frontend with a FastAPI/Python automation backend.
* Main user flows are organized around departments, tools, configuration dialogs, preview dialogs, network path checks, and execution logs.
* `front/src/App.vue` currently coordinates many concerns in one page: dashboard, department workspace, network config, global task state, preview, tool config, toast handling, and execution actions.
* PowerShell output showed mojibake for Chinese text, but source code points were verified as valid UTF-8 Chinese. No frontend text rewrite is needed unless browser rendering shows a separate issue.
* The project constraint requires all pages/components/layout elements to use shadcn/ui-style project primitives from `front/src/components/ui/`.

## Assumptions

* The main target user wants to run a known automation task quickly, not inspect a dashboard first.
* Configuration and logs are necessary, but should be secondary/progressive rather than visually competing with the primary "run task" workflow.
* Placeholder/developer tools may be useful internally, but they add noise for normal users.

## Open Questions

* Answered: choose low-risk cleanup first. Fix/verify text encoding, remove hidden dead UI blocks, and reduce obvious native controls without changing the main interaction model.

## Requirements

* Reduce the number of decisions a user sees before starting a task.
* Make the default screen prioritize useful tools and current status over global explanatory copy.
* Keep configuration, preview, logs, and network tests available, but move them into lower-emphasis surfaces where possible.
* Preserve project UI constraints: use local shadcn-style primitives and avoid new third-party UI libraries.
* Verify source text encoding and fix visible mojibake only if present in rendered UI.
* Remove hidden/dead template blocks guarded by `v-if="false"`.
* Replace obvious page-level native buttons with `UiButton` where it does not alter workflow.

## Acceptance Criteria

* [ ] A user can land on the app and identify the next action within one screen.
* [ ] Daily operation flow is no more than: choose department/tool, configure only if needed, run, then see result/progress.
* [ ] Global dashboard/admin/network details do not dominate the normal tool-running workflow.
* [x] Source UI text is verified as valid UTF-8 Chinese; shell mojibake is a terminal display issue.
* [x] shadcn-style UI primitives are used for touched page-level controls; ad-hoc native controls are reduced or wrapped.
* [x] Hidden/dead UI blocks are removed from the main page.

## Definition of Done

* Tests added/updated where behavior changes are non-trivial.
* Frontend build passes.
* UX changes verified at desktop and mobile widths.
* Docs/notes updated if user-facing workflow changes.

## Out of Scope

* Rewriting backend execution logic.
* Introducing another UI framework.
* Removing execution logs or configuration capability entirely.

## Technical Notes

* Inspected `front/src/App.vue`, `front/src/components/DepartmentSidebar.vue`, `front/src/components/ToolGrid.vue`, `front/src/components/ExecutionLogPanel.vue`, `front/src/components/GlobalRunningTasksBar.vue`, `front/src/components/NetworkSettingsPanel.vue`, `front/src/components/ui/UiPageHeader.vue`, `front/src/data/departments.js`, `front/src/style.css`, and `.trellis/spec/frontend/ui-guidelines.md`.
* Current friction points:
  * Hero/page header copy is large and explanatory; it pushes actionable tools downward.
  * The dashboard is restored as a possible saved default view, but daily users likely want their last department/tool workspace.
  * Tool cards show description, setup-state description, multiple badges, secondary actions, and primary action simultaneously.
  * Execution log panel includes filters, export, clear, pagination, detail dialogs, retry, terminate, live status, and toasts on the main workspace.
  * `NetworkSettingsPanel` exposes admin-like fixed path testing in the dashboard; this may be useful but is not part of most daily runs.
  * Some controls are plain `button`/`table`/manual `svg` usage rather than consistently composed UI primitives.
  * There are hidden/dead UI blocks in `App.vue` guarded by `v-if="false"`.
