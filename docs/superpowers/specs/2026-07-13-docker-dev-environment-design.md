# ARM Ripper-Logic Docker Dev Environment — Design

**Date:** 2026-07-13
**Status:** Approved (pending spec review)

## Goal & scope

Provide a committed, reproducible Docker-based development environment for iterating on
Automatic Ripping Machine's **non-hardware ripper logic** — disc identification, metadata
lookup, file naming/matching, notifications, and config handling.

The workflow is: **edit source on the Windows host, run tests / lint / code inside a
container** that already contains all Python dependencies and native tools (MakeMKV,
HandBrake, abcde, libdiscid) via the prebuilt `automaticrippingmachine/arm-dependencies`
base image.

### Out of scope

- **Physical disc ripping / full end-to-end.** The dev host is Windows with Docker Desktop
  and has no `/dev/srX` optical-device passthrough, so udev-triggered rips cannot run here.
  Correctness of ripper logic is verified through the test suite and through crafted
  `Job`/`Track` database records inspected in the web UI — not by ripping a real disc.
- Any change to production Docker artifacts (`Dockerfile`, production run scripts). The dev
  environment is additive.

## Context

- ARM is two processes sharing one codebase and SQLite DB: the udev-triggered ripper
  (`arm/ripper/main.py`, one process per disc) and the long-running Flask/waitress web UI
  (`arm/runui.py`). See `CLAUDE.md`.
- The production image builds `FROM automaticrippingmachine/arm-dependencies:<version>`
  (currently `1.8.0`) and layers ARM source via `COPY . /opt/arm/`. The heavy Python and
  native dependencies live in that base image, **not** in the `arm-dependencies` git
  submodule (which is registered but not checked out locally).
- The container's init scripts (`scripts/docker/runit/arm_user_files_setup.sh`,
  `.../start_udev.sh`, `scripts/docker/runsv/armui.sh`) run under `my_init`/runit and
  stage config into `/etc/arm/config` and start the ARM-UI service on boot. These scripts
  are copied to `/etc/service` and `/etc/my_init.d` during the image build (outside
  `/opt/arm`), so a source bind-mount over `/opt/arm` does not shadow them.
- Docker is available and working on the host: Windows client, Linux `amd64` engine, Docker
  Compose v5.

## Chosen approach — Option A: faithful entrypoint

The dev container runs ARM's normal `my_init` entrypoint (udev + ARM-UI service), exactly
like production **but without any `--device=/dev/srX` mappings**. This reuses ARM's real
boot path so we debug the actual system rather than a facsimile, auto-stages config/DB, and
gives a running UI to inspect crafted records. The tradeoff is harmless udev "no device"
log noise.

Rejected alternatives:
- **Option B (lightweight idle container):** faster/quieter but requires reimplementing
  config staging and provides no running UI; drifts from real boot.
- **Option C (separate test-profile service):** more moving parts than currently needed
  (YAGNI).

## Components

### 1. `docker-compose.dev.yml` (repo root)

A single `arm-dev` service:

- **Build:** `build: { context: ., dockerfile: Dockerfile }` — builds the local source on
  top of the `arm-dependencies` base, baking in the runit/my_init service scripts.
- **Entrypoint:** default (`my_init`) — Option A. No `--device` mappings.
- **Ports:** `8080:8080` (web UI on `localhost:8080`).
- **Privileged:** `privileged: true` — required for udev/mount behavior; acceptable for a
  local dev container.
- **Volumes:**
  - `.:/opt/arm` — live source, so host edits are immediately visible inside the container.
  - named volume → `/home/arm` — SQLite DB, media, logs; persists across restarts.
  - named volume → `/etc/arm/config` — staged config; persists across restarts.
- **Environment:** `ARM_UID=1000`, `ARM_GID=1000`, `TZ` (host timezone),
  `PYTHONUNBUFFERED=1`.
- **Restart:** none (dev).

State resets cleanly with `docker compose -f docker-compose.dev.yml down -v`.

### 2. Dev-workflow documentation

Append a **"Local development (Docker)"** section to `CLAUDE.md` so future Claude Code
sessions inherit the workflow. It documents bring-up, running tests, running lint, crafting
records, and resetting state (commands listed under "Data flow" below).

### 3. `.gitattributes` (optional safeguard)

Add a minimal `.gitattributes` forcing `*.sh` (and other shell/config scripts the container
executes) to LF line endings. The scripts are currently LF, but this prevents a future
re-clone on Windows from reintroducing CRLF and breaking the container at build or runtime.

## Data flow / usage

1. **Bring up:** `docker compose -f docker-compose.dev.yml up -d --build`
   - On first boot, `arm_user_files_setup.sh` stages `setup/arm.yaml`, `apprise.yaml`, and
     `abcde.conf` into the empty `/etc/arm/config` volume.
   - ARM-UI runs DB migrations against the SQLite DB under `/home/arm` and serves the UI on
     `localhost:8080`.
   - Host source edits appear live at `/opt/arm`.
2. **Run tests:**
   `docker compose -f docker-compose.dev.yml exec arm-dev python -m pytest test/unittest/`
   (single file/test via the usual pytest path/`::` selectors).
3. **Run lint (CI-equivalent):**
   `docker compose -f docker-compose.dev.yml exec arm-dev flake8 . --max-complexity=15 --max-line-length=120 --show-source --statistics`
4. **Craft records / exercise logic:** exec a `python` shell with Flask app context inside
   the container to insert `Job`/`Track` rows and call ripper functions, then inspect them
   in the UI.
5. **Reset state:** `docker compose -f docker-compose.dev.yml down -v`.

## Error handling / known caveats

- **udev noise:** the container logs harmless "no optical device" messages; expected and
  ignored.
- **pytest / flake8 availability:** the `arm-dependencies` base image may not include
  `pytest`/`flake8` (CI installs them separately). This is verified during implementation;
  if they are absent, the environment installs them (a documented `pip install pytest
  flake8` one-liner run inside the container, or a small dev-deps step). This is the single
  known open verification point.
- **Submodule:** `git submodule update --init` is run so `requirements.txt` and future
  bare-metal paths resolve, even though runtime deps come from the base image.
- **No hardware ripping:** attempting a real rip will not work here by design.

## Success criteria

- `docker compose -f docker-compose.dev.yml up -d --build` yields a running UI reachable at
  `http://localhost:8080`.
- The existing `test/unittest/` suite runs and passes inside the container via one `exec`
  command.
- `flake8` runs inside the container with the CI flags.
- Editing a Python file on the host is reflected inside the container without a rebuild.
- `down -v` fully resets DB/config state.
