# brainstorm: speed up BUE1 EAR fetcher

## Goal

Explore practical ways to reduce the runtime of `black/scripts/bue1/ear_declaration_data_fetcher.py`, especially whether multi-threaded or parallel browser execution is appropriate for EAR portal querying.

## What I Already Know

* The current script processes Excel rows sequentially.
* The user is considering multi-threaded concurrency.
* The script logs into the EAR portal, locates a matching row for year/month/category, and writes the fetched value back to Excel.
* The current main loop keeps one browser context and one active page, then iterates `for task in tasks`.
* Same-account session reuse only helps when rows with the same credentials are adjacent.
* Each successful row currently calls `write_weight_back`, which reopens and saves the Excel workbook every time.
* The user observed that most rows to query use the same account/password.

## Assumptions

* Network/browser interaction is likely the primary bottleneck.
* Excel writes should remain serialized or batched to avoid file corruption and lock contention.

## Open Questions

* Confirm exact default worker count and maximum recommended worker count.

## Requirements

* Identify bottlenecks and feasible acceleration approaches before implementation.
* Preserve correctness of login/session handling and Excel write-back.
* Optimize primarily for many rows sharing the same account/password.
* Support worker-based concurrent querying by splitting task data across workers.
* Preserve existing single-thread behavior where each successful row can still be written immediately.
* In multi-worker mode, workers should keep query results in memory and the parent process should write back to Excel after all queries finish.
* Workers may receive rows from the same or different accounts; within each worker, reuse the existing same-account session logic and switch accounts as needed.
* Avoid duplicate querying of the same assigned row/data item across workers.
* Avoid concurrent writes to the same Excel file.
* Expose configurable worker count in the frontend BUE1 EAR config dialog.
* Show a warning to back up the original Excel file before running, especially in concurrent mode.

## Acceptance Criteria

* [ ] Proposed approach explains expected speedup and risk.
* [ ] Proposed approach accounts for EAR portal session behavior and Excel file safety.
* [ ] MVP scope is explicit before code changes.
* [x] `maxWorkers=1` preserves immediate write-back behavior.
* [x] `maxWorkers>1` uses independent workers and parent-only final Excel write-back.
* [x] Frontend config includes worker count and backup warning.

## Definition of Done

* Tests or validation added/updated where appropriate.
* Lint/typecheck/compile checks pass for changed code.
* Rollout/rollback considered if risky.

## Out of Scope

* Replacing the EAR portal workflow with an unsupported/private API unless one is already known and stable.

## Technical Notes

* Primary file: `black/scripts/bue1/ear_declaration_data_fetcher.py`
* Need inspect current browser/session loop, task grouping, and write-back pattern.
* `launch_isolated_browser_context` uses a persistent Playwright context with one profile directory.
* Parallel browser workers would need separate profile directories and should not share Playwright page/context objects.
* Excel write-back should be serialized or batched; concurrent workers should return results rather than write the same workbook directly.

## Research Notes

### Feasible approaches here

**Approach A: Grouping + batched Excel write** (Recommended first)

* How it works: group tasks by credentials/company where possible, reuse one login session for all matching rows, collect write-back results, then save Excel once or in safe batches.
* Pros: low portal risk, no parallel login pressure, likely removes many login/logout and workbook-save costs.
* Cons: speedup depends on repeated accounts/companies and current Excel save cost.

**Approach A2: Same-login company/category batching** (Recommended refinement)

* How it works: group rows by account/password, then by WEEE/company; log in once per account, enter a company once, parse the EAR table once for that company/month/year, and fill all matching category rows from the parsed table.
* Pros: best fit for the observed data shape; reduces repeated login, repeated company switching, and repeated table scanning.
* Cons: requires a slightly larger refactor because `attempt_login_and_fetch` currently returns one row result at a time.

**Approach B: Limited browser-worker concurrency**

* How it works: split tasks into account/company groups, run 2-3 independent Playwright browser contexts in parallel, collect results in the parent process, then write Excel serially.
* Pros: can reduce wall-clock time when portal/network waits dominate.
* Cons: higher risk of EAR throttling/session conflicts, more memory/CPU, more complex error handling.

**User-preferred worker split**

* How it works: split row tasks by configured worker count, regardless of whether rows share an account. Each worker runs the same session reuse/switching logic as the current single-thread loop for its assigned slice. Single-worker mode writes each row immediately. Multi-worker mode records results in memory and writes back once after all workers finish.
* Required safety boundaries: deterministic task partitioning, separate browser context/profile per worker, no shared Playwright objects across workers, no worker-level Excel writes in multi-worker mode, parent-only final Excel write, and clear error aggregation.
* Locking model: a task queue or fixed partition should prevent duplicate assignment; an optional result lock protects shared result collection if using threads, while Excel write lock is unnecessary if only the parent writes after workers complete.

## Decision (ADR-lite)

**Context**: The user wants speedup via configurable worker concurrency while preserving current account-switching behavior.

**Decision**: Implement concurrency as independent workers that each process an assigned subset of row tasks. In single-worker mode, keep immediate write-back behavior. In multi-worker mode, collect query results in memory and perform a serialized final write-back.

**Consequences**: This improves wall-clock time without allowing concurrent Excel writes. It requires separate browser contexts/profile directories per worker and careful result/error aggregation.

**Approach C: Direct request/API reuse**

* How it works: inspect whether the portal requests can be replayed after login and fetch data without full UI navigation.
* Pros: potentially fastest.
* Cons: brittle if portal uses JSF view state/session tokens; larger reverse-engineering effort.
