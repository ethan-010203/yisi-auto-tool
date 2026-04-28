# brainstorm: staging and production release flow

## Goal

Create a staging and production release workflow so changes can be tested privately before users see them at `auto.ethan010203.online`.

## What I already know

* The current public production domain is `auto.ethan010203.online`, exposed through Cloudflare Tunnel.
* The user currently runs `E:\localhost-auto\yisi-auto-tool-1\restart-services.bat` after changes to see the effect.
* `restart-services.bat` calls `scripts/windows/restart-services.ps1`.
* `restart-services.ps1` builds the frontend, stops the managed services, and starts them again.
* `start-services.ps1` defaults the FastAPI backend to `YISI_BACKEND_PORT` or port `8000`.
* The backend serves the built frontend from `front/dist`.
* The current scripts track one backend PID and one worker PID under `.run/windows`, so they currently model a single running environment.
* Cloudflare Tunnel supports publishing multiple public hostnames to different local services/ports in one tunnel.

## Assumptions

* Production should remain `https://auto.ethan010203.online`.
* Staging uses `https://auto-test.ethan010203.online`.
* Production should only change when the user explicitly publishes/restarts production.

## Open Questions

* None for the MVP.

## Requirements

* Keep the production URL stable for users.
* Allow the user to test changes before publishing to production.
* Avoid overwriting the production frontend build during staging tests.
* Avoid port and PID conflicts between staging and production services.
* Provide one simple root Windows command for staging start/restart/status, production start/restart/status, publish, and rollback.
* Production runs on port `8000` with its own backend, worker, config directory, queue database, logs, and runtime directory.
* Staging runs on port `8001` with its own backend, worker, config directory, queue database, logs, and runtime directory.
* Publishing promotes the tested staging frontend build to production and restarts production.
* Rollback restores the previous production frontend build backup and restarts production.

## Acceptance Criteria

* [x] Production can keep serving the last released build while staging is restarted.
* [x] Staging can run on a separate local port and be mapped by Cloudflare Tunnel to a test hostname.
* [x] A release command can promote a tested build to production.
* [x] Status/stop/restart scripts clearly identify which environment they affect.
* [x] README documents the workflow and Cloudflare route setup.

## Definition of Done

* Tests or command-level validation added where practical.
* Build/start scripts validated on Windows.
* Docs updated with staging, production, publish, and rollback notes.
* Rollback considered for production release.

## Technical Notes

* Relevant files:
  * `restart-services.bat`
  * `start-services.bat`
  * `status-services.bat`
  * `stop-services.bat`
  * `build-frontend.bat`
  * `scripts/windows/common.ps1`
  * `scripts/windows/start-services.ps1`
  * `scripts/windows/restart-services.ps1`
  * `scripts/windows/build-frontend.ps1`
  * `black/main.py`
  * `front/vite.config.js`
* Production frontend artifact is `front/dist-production`.
* Staging frontend artifact is `front/dist-staging`.
* Production data remains in the existing `black/configs`, `black/data`, `black/logs`, and `black/runtime` paths.
* Staging data uses `black/configs-staging`, `black/data-staging`, `black/logs-staging`, and `black/runtime-staging`.
* `black/main.py`, `black/worker.py`, and runner modules now read environment-specific path variables set by the Windows scripts.
* Production release backups are stored in `.releases/production/<timestamp>/frontend`.
* Root `.bat` entrypoints are consolidated into `yisi.bat`; environment-specific PowerShell scripts remain under `scripts/windows/`.

## Research Notes

### What Cloudflare Tunnel supports

* A published application maps one public hostname to one local service URL.
* Multiple published applications can be configured on the same tunnel.
* This means one tunnel can route `auto.ethan010203.online` to `http://localhost:8000` and `auto-test.ethan010203.online` to `http://localhost:8001`.

### Feasible approaches here

**Approach A: two live environments, separate ports and hostnames** (Recommended)

* How it works: production runs on `8000` and serves released assets; staging runs on `8001` and serves staging assets. Cloudflare maps production and staging hostnames separately.
* Pros: safest for users, realistic testing through a public test URL, easy to verify before publishing.
* Cons: needs script changes for environment-specific PID/log/build directories.

**Approach B: local staging, production publish only**

* How it works: test locally with Vite/FastAPI, then run one publish command that builds and restarts production.
* Pros: simpler and fewer moving parts.
* Cons: does not test the exact Cloudflare/public-domain path before release.

**Approach C: separate git worktree or cloned folder for production**

* How it works: staging stays in the active dev folder; production runs from a clean release folder. Publishing copies or pulls approved code into the production folder.
* Pros: strong separation and rollback story.
* Cons: heavier operational workflow.

## Out of Scope

* CI/CD hosted deployment unless explicitly requested.
* User authentication or Cloudflare Access protection for staging unless explicitly requested.
* Replacing Cloudflare Tunnel.
* Cloning backend source code back from a running port. Ports expose running services, not a code repository; backend code rollback remains a Git workflow.
