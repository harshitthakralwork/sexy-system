# Runbook — Local Infrastructure (Docker Desktop, and the Windows-native fallback)

Machine inspected 2026-11-02. This document exists because the stack cannot be
provisioned from inside the current session, and because the project must not stall
while that is true.

## 1. What this machine looks like

| Check | Value | Meaning for Docker |
|---|---|---|
| OS | Windows 11 Pro, build 26300 | Supported |
| CPU | 6 cores / 12 logical | Supported |
| RAM | 15.8 GB total, **2.1 GB free at inspection** | Workable, but only after closing apps |
| Virtualization | Firmware enabled, SLAT supported | Supported |
| Hypervisor running | **No** | Virtual Machine Platform / WSL2 must be enabled → **reboot required** |
| Shell elevation | **Not administrator** | The installer cannot be run from this agent session |
| Free disk | C: **26.2 GB**, D: 58.5 GB | Docker/WSL data must be moved to D: or C: will fill |

Verdict: Docker Desktop is supported here. Two facts prevent doing it automatically:
it needs elevation, and enabling the container backend needs a reboot. Both are
deliberate human decisions, not agent oversights.

## 2. Procedure A — Docker Desktop (recommended)

Run these from an **elevated** PowerShell (Start → type `powershell` → Run as administrator).

### 2.1 Install

```powershell
winget install -e --id Docker.DockerDesktop
```

Docker Desktop will enable the required Windows features (`VirtualMachinePlatform`,
`Microsoft-Windows-Subsystem-Linux`) itself. **Reboot when prompted.** Skipping the
reboot leaves `docker info` failing with a WSL error that looks like a Docker bug.

### 2.2 Move container storage off C: before the first image pull

Do this **before** `infra-up.ps1`, otherwise ~10 GB of images land on a 26 GB system
drive and stay there.

1. Docker Desktop → Settings → Resources → Advanced → **Disk image location** → `D:\DockerData`.
2. Apply and restart Docker.

Or pre-place the config at `%USERPROFILE%\.docker\desktop\vhdx-path.json`:

```json
{ "dataFolder": "D:\\DockerData" }
```

### 2.3 Verify

```powershell
docker info --format '{{.ServerVersion}} / {{.OperatingSystem}}'
docker compose version
docker run --rm hello-world
```

### 2.4 Start this project

```powershell
cd D:\SPARKXFLOWSCAPPER\sparkxflow-nexus
./scripts/infra-up.ps1
docker compose ps            # postgres, redis, searxng should be healthy
./scripts/db-migrate.ps1
```

Expect roughly 1.5–2 GB of RAM resident for the three infrastructure containers, plus
about 1.8 GB pulled as images on first start.

### 2.5 Memory discipline

With 2.1 GB free at inspection, the stack will thrash while Discord, Chrome tabs and
CamoStudio are open. Close them before starting containers, and check with
`docker stats` once. The compose file already caps each service, so a starved
container fails visibly instead of quietly eating the desktop.

## 3. Procedure B — Windows-native fallback

Use this if Docker Desktop cannot be installed (no admin rights on the machine, or a
reboot is not acceptable right now). Everything in Phase 0 and most of Phase 1 works
this way.

### 3.1 PostgreSQL — install natively

1. Download the EDB installer for Windows x64 (PostgreSQL 17).
2. Choose a **password** for the `postgres` superuser you will actually type again.
3. Install as a **Windows service** (needs admin) or uncheck the service option and
   start it manually with `pg_ctl` (no admin needed).
4. Create the project role and database:

```sql
CREATE USER sparkx WITH PASSWORD 'sparkx';
CREATE DATABASE sparkxflow OWNER sparkx;
\c sparkxflow
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
```

5. Point `.env` at it (`SPARKX_DATABASE_URL=postgresql+asyncpg://sparkx:sparkx@localhost:5432/sparkxflow`)
   and run `./scripts/db-migrate.ps1`.

Migrations and every DB-backed feature work identically on a native Postgres. This is
the recommended fallback.

### 3.2 Redis — the actual gap

Redis has no official Windows build. Options, best first:

| Option | Notes |
|---|---|
| **Memurai Developer** | Windows-native Redis-compatible server, free for development. Works with Celery. |
| **WSL2 only** (no Docker) | `wsl --install -d Ubuntu`, then `apt install redis-server`. Lighter than Docker Desktop but still needs a reboot. |
| **Skip the broker** | Discovery runs synchronously inside the API process during development. |

Skipping the broker is legitimate for slice 1 and is why `app/workers/dispatcher.py`
sits behind a `TaskDispatcher` protocol: a `SynchronousDispatcher` used in
development satisfies the same interface and lets the pipeline run end to end with no
Redis at all. **Trade-off, stated plainly:** synchronous execution blocks the request
until the job finishes, so it is fine for a 20-result test search and unusable for a
real discovery sweep. Do not build Phase 4 scheduling on it.

### 3.3 SearXNG — no native path

SearXNG is a Linux-flavoured Python service and is not worth fighting on Windows.
Without Docker:

- Set `SPARKX_SEARXNG_BASE_URL` to a public instance you are comfortable using, and
  accept its rate limits and availability; or
- Run the fallback slice against Overpass + the website crawler only, and let the
  Source Manager report SearXNG as `unavailable` rather than pretending.

The second option is the honest one and matches PRD principle 9 (responsible
collection) plus D8 (honest source-failure reporting).

### 3.4 Celery worker

On the Windows host, Celery's default prefork pool does not work. Use
`./scripts/dev-worker.ps1`, which runs `--pool solo`: one job at a time, adequate for
development. Real parallelism arrives with the Linux container.

## 4. What each path unblocks

| Work | Docker | Native fallback | Nothing installed |
|---|---|---|---|
| Phase 0 scaffold, tests, lint | Yes | Yes | **Yes** |
| Migrations, models, DB-backed services | Yes | Yes | No |
| Auth end to end | Yes | Yes | No |
| Source Manager with real rows | Yes | Yes | No |
| Celery background jobs | Yes (parallel) | Yes (Memurai, solo pool) | No |
| SearXNG discovery adapter | Yes | Degraded (public instance / disabled) | No |
| Playwright browser automation | Yes | No — install later, in a container | No |

## 5. Caveat on this compose file

`docker-compose.yml` was written from the specification and reviewed, but **not
executed** — there is no container runtime on this machine yet. The first
`infra-up.ps1` may need small corrections (most likely the SearXNG settings mount or
the memory caps). That is expected and is not a reason to trust it silently: after the
first successful start, the runbook gets updated with what actually happened.
