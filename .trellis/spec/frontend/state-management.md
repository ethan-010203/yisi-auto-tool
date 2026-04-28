# State Management

> How state is managed in this project.

---

## Overview

<!--
Document your project's state management conventions here.

Questions to answer:
- What state management solution do you use?
- How is local vs global state decided?
- How do you handle server state?
- What are the patterns for derived state?
-->

(To be filled by the team)

---

## State Categories

<!-- Local state, global state, server state, URL state -->

(To be filled by the team)

---

## When to Use Global State

<!-- Criteria for promoting state to global -->

(To be filled by the team)

---

## Server State

<!-- How server data is cached and synchronized -->

### Tool Config Contracts

Tool configuration state flows through `front/src/composables/useToolConfig.js`, `ConfigRequest` in `black/main.py`, and the target script config JSON.

#### Signatures

Frontend normalizer:

```js
normalizeEarDeclarationFetcherConfig(config) -> {
  excelFilePath,
  excelFileDisplay,
  excelFolderPath,
  excelFolderDisplay,
  reportYear,
  reportMonthGerman,
  maxWorkers
}
```

Backend request model:

```python
class ConfigRequest(BaseModel):
    maxWorkers: Optional[int] = None
```

Script resolver:

```python
resolve_max_workers(config: dict) -> int
```

#### Contract

For `BUE1 / ear_declaration_data_fetcher`, the `maxWorkers` payload field is an integer from `1` to `4`.

- `1`: script preserves single-worker behavior and writes each row immediately after query.
- `>1`: script splits row tasks across independent workers, stores query results in memory, and writes Excel once after all workers finish.
- Workers must not share Playwright `Page`, `BrowserContext`, or persistent profile directories.
- Excel writes must be parent-only in concurrent mode.

#### Validation & Error Matrix

| Field | Good | Bad | Expected Behavior |
|-------|------|-----|-------------------|
| `maxWorkers` | `1`, `2`, `3`, `4` | `0`, `5`, `"abc"`, `1.5` | Frontend and backend reject before running. |
| `excelFilePath` | Existing `.xlsx` / `.xlsm` file | Empty, missing, non-Excel | Backend rejects before running. |
| concurrent write | Parent writes once | Workers write Excel directly | Forbidden; risks file lock/corruption. |

#### Good/Base/Bad Cases

Base:

```json
{ "maxWorkers": 1 }
```

Good concurrent:

```json
{ "maxWorkers": 2 }
```

Bad:

```json
{ "maxWorkers": 8 }
```

#### Tests Required

- `cmd /c npm run build` must pass after frontend config UI changes.
- `py -3 -m py_compile black/scripts/bue1/ear_declaration_data_fetcher.py black/main.py` must pass after backend config/schema changes.
- For script-only checks, import `resolve_max_workers` and confirm string/number inputs resolve or fail as expected.

#### Wrong vs Correct

Wrong:

```python
# Worker threads write the same Excel file directly.
write_weight_back(row_index, output_column, value, excel_path)
```

Correct:

```python
# Workers return results; parent process writes once after all workers finish.
write_weights_back_batch(write_backs, output_column, excel_path)
```

### Queue Runtime Probe Config Contract

`BUE2 / queue_runtime_probe` and `CONSULT / queue_runtime_probe` share the same saved config shape.

#### Signatures

Frontend normalizer:

```js
normalizeQueueRuntimeProbeConfig(config) -> { waitSeconds }
```

Backend request model:

```python
class ConfigRequest(BaseModel):
    waitSeconds: Optional[int] = None
```

Script resolver:

```python
resolve_wait_seconds(config: dict) -> int
```

#### Contract

`waitSeconds` is an integer from `1` to `3600`. If not configured, the probe defaults to `12` seconds to preserve the previous 6-step, 2-second behavior.

#### Validation & Error Matrix

| Field | Good | Bad | Expected Behavior |
|-------|------|-----|-------------------|
| `waitSeconds` | `1`, `12`, `120` | `0`, `3601`, `"abc"` | Frontend and backend reject invalid saved values; scripts reject invalid runtime configs. |

#### Tests Required

- `cmd /c npm run build` must pass after frontend config UI changes.
- `py -3 -m py_compile black/main.py black/scripts/bue2/testing/queue_runtime_probe.py black/scripts/consult/testing/queue_runtime_probe.py`
- Import each probe's `resolve_wait_seconds` and confirm default, valid, and invalid values.

---

## Common Mistakes

<!-- State management mistakes your team has made -->

(To be filled by the team)
