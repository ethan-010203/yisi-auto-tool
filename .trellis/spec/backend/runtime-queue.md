# Runtime Queue

## Scenario: Worker Concurrency Limit

### 1. Scope / Trigger

- Trigger: changing task execution, queue claiming, worker loops, cancellation, or `runtime_limits.json`.
- Problem prevented: `global` can be configured as `2`, but a synchronous worker loop still behaves like a single-task runner.

### 2. Signatures

Worker command:

```bash
py -3 black/worker.py --poll-interval 1.0
```

Runtime config:

```json
{
  "global": 2,
  "perDepartment": 1,
  "perTool": 1
}
```

Queue claim:

```python
claim_next_execution(worker_id: str, global_limit: int, department_limit: int, tool_limit: int) -> dict | None
```

Force termination:

```python
POST /api/executions/{log_id}/force-terminate
force_terminate_execution(execution_id: str) -> dict | None
```

### 3. Contracts

- `global` is the maximum number of running or cancelling tasks across all departments.
- `perDepartment` is the maximum number of running or cancelling tasks in one department.
- `perTool` is the maximum number of running or cancelling tasks for one department/tool pair.
- A worker process must keep polling after it starts a job, so a second eligible department can be claimed while the first task is still running.
- Each claimed job is marked `running` in SQLite before its script process starts.
- Forced termination is for stale `running` / `cancelling` / `queued` records that no worker can finish. It sets the execution to `terminated`, clears `process_id`, records `finished_at`, and attempts to kill the stored process tree when a process id exists.
- `finalize_execution` must only update active rows. A worker thread finishing after a forced termination must not overwrite the terminal `terminated` status.

### 4. Validation & Error Matrix

| Case | Expected Behavior |
|------|-------------------|
| BUE1 running, CONSULT queued, `global=2`, `perDepartment=1` | CONSULT is claimed as the second running task. |
| BUE1 running, second BUE1 queued, `perDepartment=1` | Second BUE1 remains queued. |
| Two tasks running, third queued, `global=2` | Third task remains queued. |
| Invalid or missing runtime limit file | `load_runtime_limits` falls back to safe minimums/defaults. |
| Stale task stuck in `cancelling` with missing process | Force termination marks it `terminated` and releases active slots. |
| Worker finishes after force termination | The row remains `terminated`; late finalize does not overwrite it. |

### 5. Good/Base/Bad Cases

Base:

```json
{ "global": 2, "perDepartment": 1, "perTool": 1 }
```

Good:

```text
worker main loop starts job thread -> immediately polls queue again -> claims another eligible department.
```

```text
stale cancelling record -> force-terminate endpoint -> status=terminated and process_id=NULL.
```

Bad:

```text
worker main loop calls _run_execution synchronously -> no second task can be claimed until the first script exits.
```

```text
force-terminate sets status=terminated -> late worker finalize overwrites it back to failed.
```

### 6. Tests Required

- `py -3 -m py_compile black/worker.py black/runner/sqlite_store.py black/runner/runtime_limits.py`
- Queue assertion: enqueue two BUE1 jobs and one CONSULT job, then call `claim_next_execution` three times with `global=2`, `department_limit=1`, `tool_limit=1`; the first claim is BUE1, the second is CONSULT, and the third is `None`.
- Force termination assertion: create a running/cancelling row, call `force_terminate_execution`, assert status becomes `terminated`, `process_id` is `NULL`, and a later `finalize_execution` call does not change the status.

### 7. Wrong vs Correct

#### Wrong

```python
job = claim_next_execution(...)
_run_execution(job, worker_id)
```

#### Correct

```python
job = claim_next_execution(...)
start_job(job)
```
