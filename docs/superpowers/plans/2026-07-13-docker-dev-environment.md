# ARM Ripper-Logic Docker Dev Environment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Provide a committed docker-compose dev environment that lets a developer edit ARM source on the Windows host and run the web UI, test suite, and lint inside a container that has all dependencies and native tools.

**Architecture:** A single `arm-dev` compose service builds the local `Dockerfile` (layering ARM source on the `arm-dependencies` base image), runs ARM's real `my_init` entrypoint **without** optical-device passthrough, bind-mounts the repo at `/opt/arm` for live edits, and persists DB/config in named volumes. A thin entrypoint wrapper fixes named-volume ownership so ARM's boot-time ownership check passes. Tests and lint run via `docker compose exec`.

**Tech Stack:** Docker + Docker Compose v5, the `automaticrippingmachine/arm-dependencies` base image, Python 3 (Flask/waitress/pytest/flake8), phusion baseimage `my_init`/runit.

## Global Constraints

- **Additive only:** do not modify the production `Dockerfile` or any production run script under `scripts/`. All dev tooling lives in new files.
- **No hardware ripping:** no `--device=/dev/srX` mappings; physical rips are out of scope.
- **Python versions supported:** 3.9–3.12.
- **Lint command is CI-binding:** `flake8 . --max-complexity=15 --max-line-length=120 --show-source --statistics`.
- **Shell scripts must be LF** line endings (they execute inside a Linux container).
- **Branch:** all work lands on `feature/docker-dev-environment`.
- **All commands are shown in POSIX shell** (Bash tool); the developer's global rule forbids chaining separate Bash tool calls with `&&`. `&&` **inside** a container command string or entrypoint is fine.

---

### Task 1: Static dev files (dev deps, line-ending safeguard, submodule)

**Files:**
- Create: `requirements-dev.txt`
- Create: `.gitattributes`
- Init: `arm-dependencies` git submodule

**Interfaces:**
- Produces: `requirements-dev.txt` (installed inside the container in Task 4); `.gitattributes` enforcing LF on shell scripts.

- [ ] **Step 1: Create `requirements-dev.txt`**

Pin flake8 to the same version the repo already uses in `requirements.txt`; add pytest (not present in the runtime requirements). This makes the in-container test/lint toolchain deterministic regardless of what the base image ships.

```
# Development-only dependencies for the docker-compose dev environment.
# Installed inside the arm-dev container (see CLAUDE.md "Local development").
pytest
flake8==7.3.0
```

- [ ] **Step 2: Create `.gitattributes`**

Guarantees the container-executed scripts keep LF endings even if the repo is re-cloned on Windows.

```
# Shell/init scripts run inside a Linux container — force LF.
*.sh text eol=lf
scripts/docker/custom_udev text eol=lf
```

- [ ] **Step 3: Initialize the dependencies submodule**

Run:
```bash
git submodule update --init
```
Expected: clones `arm-dependencies` into the (currently empty) submodule directory, or prints nothing if already present. Verify with:
```bash
git submodule status
```
Expected: line begins with a space (checked out) rather than `-` (uninitialized), e.g. `<sha> arm-dependencies (heads/main)`.

- [ ] **Step 4: Verify line endings are actually LF**

Run:
```bash
file scripts/docker/runit/start_udev.sh scripts/docker/runsv/armui.sh
```
Expected: no occurrence of `CRLF` in the output.

- [ ] **Step 5: Commit**

```bash
git add requirements-dev.txt .gitattributes
git commit -m "Add dev requirements and LF gitattributes for docker dev env"
```
(The submodule init changes only the working tree checkout, not tracked content, so nothing else is staged here.)

---

### Task 2: The `docker-compose.dev.yml` service

**Files:**
- Create: `docker-compose.dev.yml`

**Interfaces:**
- Consumes: local `Dockerfile`; `requirements-dev.txt` (mounted at `/opt/arm/requirements-dev.txt` via the source bind mount).
- Produces: a service named `arm-dev`, container name `arm-dev`, UI on `localhost:8080`, named volumes `arm-home` and `arm-config`.

- [ ] **Step 1: Write `docker-compose.dev.yml`**

The `entrypoint` override creates and chowns the two volume mount points to the ARM uid/gid before exec-ing the real `my_init`, so `arm_user_files_setup.sh`'s `check_folder_ownership` passes on fresh root-owned named volumes. Only the top-level dirs are chowned (the ownership check is non-recursive), so this stays fast.

```yaml
# Local development environment for ARM ripper-logic work (non-hardware).
# Usage is documented in CLAUDE.md, section "Local development (Docker)".
#
# This is additive and never used in production. It builds the same Dockerfile
# but runs without optical-device passthrough, so physical ripping cannot occur.
services:
  arm-dev:
    build:
      context: .
      dockerfile: Dockerfile
    image: arm-dev:local
    container_name: arm-dev
    # Required for udev/mount behaviour the container expects. Safe locally.
    privileged: true
    ports:
      - "8080:8080"
    environment:
      ARM_UID: "1000"
      ARM_GID: "1000"
      TZ: "Etc/UTC"
      PYTHONUNBUFFERED: "1"
    volumes:
      # Live source: host edits are visible immediately inside the container.
      - .:/opt/arm
      # Persistent state (SQLite DB, media, logs, staged config).
      - arm-home:/home/arm
      - arm-config:/etc/arm/config
    # Fix ownership of freshly-created named volumes (root-owned by default) so
    # ARM's boot-time ownership check passes, then hand off to the real init.
    entrypoint:
      - /bin/bash
      - -c
      - >-
        mkdir -p /home/arm /etc/arm/config &&
        chown "${ARM_UID}:${ARM_GID}" /home/arm /etc/arm/config &&
        exec /sbin/my_init

volumes:
  arm-home:
  arm-config:
```

- [ ] **Step 2: Validate the compose file parses**

Run:
```bash
docker compose -f docker-compose.dev.yml config
```
Expected: prints the fully-resolved config with no error; the `arm-dev` service, both named volumes, and the `entrypoint` list are present.

- [ ] **Step 3: Commit**

```bash
git add docker-compose.dev.yml
git commit -m "Add docker-compose.dev.yml for ripper-logic dev environment"
```

---

### Task 3: Build the image and verify a clean boot

**Files:** none (verification task; may amend `docker-compose.dev.yml` only if boot fails).

**Interfaces:**
- Consumes: `docker-compose.dev.yml`, local `Dockerfile`.
- Produces: a running `arm-dev` container serving the UI on `localhost:8080`.

- [ ] **Step 1: Build and start the container**

Run (first run pulls the multi-GB base image; allow several minutes):
```bash
docker compose -f docker-compose.dev.yml up -d --build
```
Expected: build completes, `Container arm-dev  Started`.

- [ ] **Step 2: Confirm the container is running**

Run:
```bash
docker compose -f docker-compose.dev.yml ps
```
Expected: `arm-dev` shows state `Up` (not `Restarting` or `Exited`).

- [ ] **Step 3: Inspect boot logs for the ownership check and UI start**

Run:
```bash
docker compose -f docker-compose.dev.yml logs --no-log-prefix arm-dev
```
Expected to see, in order:
- `[OK]: ARM UID and GID set correctly, ARM has access to '/home/arm'`
- `[OK]: ARM UID and GID set correctly, ARM has access to '/etc/arm/config'`
- `Config not found! Creating config file: /etc/arm/config/arm.yaml` (first boot only)
- `Starting web ui`
- an ARM-UI startup line such as `Starting ARM-UI on interface address`

udev "no device" noise is expected and can be ignored. If instead you see `[ERROR]: ARM does not have permissions` followed by the container exiting, the entrypoint chown did not take effect — recheck Task 2 Step 1 `ARM_UID`/`ARM_GID` values and that the `entrypoint` list is present, then `down -v` and repeat from Step 1.

- [ ] **Step 4: Verify the UI is reachable from the host**

Run:
```bash
curl -sS -o /dev/null -w "%{http_code}\n" http://localhost:8080
```
Expected: an HTTP status line — `200`, or `302`/`301` (redirect to `/setup` or `/login`). Any of these confirms the UI is serving. A `000`/connection-refused means the UI did not bind; re-check Step 3 logs.

- [ ] **Step 5: No commit** (verification only). If Task 2's file was amended to achieve a clean boot, commit that fix:

```bash
git add docker-compose.dev.yml
git commit -m "Fix arm-dev boot: <describe the adjustment>"
```

---

### Task 4: Run the test suite and lint inside the container

**Files:** none (verification task).

**Interfaces:**
- Consumes: the running `arm-dev` container, `requirements-dev.txt`.
- Produces: confirmation that `pytest` and `flake8` run inside the container.

- [ ] **Step 1: Install dev dependencies inside the container**

Run:
```bash
docker compose -f docker-compose.dev.yml exec arm-dev pip install --no-cache-dir -r /opt/arm/requirements-dev.txt
```
Expected: `Successfully installed ... pytest-<v> ...` (flake8 may report "already satisfied").

- [ ] **Step 2: Run the existing unit tests**

Run:
```bash
docker compose -f docker-compose.dev.yml exec arm-dev python -m pytest test/unittest/ -v
```
Expected: pytest collects the tests from `test_ripper_ARMInfo.py`, `test_ripper_processhandler.py`, and `test_ripper_utils_file_matching.py` and reports a summary line (e.g. `=== N passed in Xs ===`). If any test fails, capture the failure output — that is a real signal about the environment or code, not a plan defect; investigate before proceeding.

- [ ] **Step 3: Run a single test to confirm selectors work**

Run:
```bash
docker compose -f docker-compose.dev.yml exec arm-dev python -m pytest "test/unittest/test_ripper_utils_file_matching.py::TestFileMatching::test_find_matching_file_exact_match" -v
```
Expected: `1 passed`.

- [ ] **Step 4: Run flake8 with the CI-binding flags**

Run:
```bash
docker compose -f docker-compose.dev.yml exec arm-dev flake8 . --max-complexity=15 --max-line-length=120 --show-source --statistics
```
Expected: exit code 0 with no output (the committed `main` tree is lint-clean under these flags). Any findings printed here are pre-existing and should be noted, not silently fixed as part of this task.

- [ ] **Step 5: No commit** (verification only).

---

### Task 5: Verify live edits + reset, then document the workflow

**Files:**
- Modify: `CLAUDE.md` (append a "Local development (Docker)" section)

**Interfaces:**
- Consumes: the running `arm-dev` container.
- Produces: developer-facing documentation of the workflow.

- [ ] **Step 1: Prove host edits are live inside the container (no rebuild)**

Create a throwaway marker on the host and read it back from inside the container:
```bash
echo "live-edit-check" > live_edit_probe.txt
docker compose -f docker-compose.dev.yml exec arm-dev cat /opt/arm/live_edit_probe.txt
```
Expected: prints `live-edit-check`. Then remove the probe:
```bash
rm live_edit_probe.txt
```

- [ ] **Step 2: Append the "Local development (Docker)" section to `CLAUDE.md`**

Add this section at the end of `CLAUDE.md`:

```markdown
## Local development (Docker)

`docker-compose.dev.yml` provides a container for working on ARM's **non-hardware
ripper logic** (identification, metadata, file naming, notifications, config). It builds
the production `Dockerfile` but runs without optical-device passthrough, so it cannot rip a
physical disc — verify ripper logic via `test/unittest/` and crafted `Job`/`Track` records
viewed in the UI. Requires Docker with a Linux engine (Docker Desktop is fine).

Bring it up (first build pulls the multi-GB dependencies base image):
```
docker compose -f docker-compose.dev.yml up -d --build
```
The UI serves on http://localhost:8080. Source is bind-mounted at `/opt/arm`, so edits on
the host are live inside the container (Python changes need a UI restart:
`docker compose -f docker-compose.dev.yml restart arm-dev`).

Install dev-only tooling (pytest/flake8) once per container lifecycle:
```
docker compose -f docker-compose.dev.yml exec arm-dev pip install -r /opt/arm/requirements-dev.txt
```

Run tests / a single test / lint inside the container:
```
docker compose -f docker-compose.dev.yml exec arm-dev python -m pytest test/unittest/
docker compose -f docker-compose.dev.yml exec arm-dev python -m pytest test/unittest/test_ripper_utils_file_matching.py::TestFileMatching::test_find_matching_file_exact_match
docker compose -f docker-compose.dev.yml exec arm-dev flake8 . --max-complexity=15 --max-line-length=120 --show-source --statistics
```

Open a Python shell (Flask app context available) to craft `Job`/`Track` records:
```
docker compose -f docker-compose.dev.yml exec arm-dev /bin/python3
```

Reset all DB/config state to a clean slate:
```
docker compose -f docker-compose.dev.yml down -v
```

Note: udev logs harmless "no optical device" messages — expected. State lives in the
`arm-home` and `arm-config` named volumes; `down` without `-v` keeps it, `down -v` wipes it.
```

- [ ] **Step 3: Verify the documented reset works**

Run:
```bash
docker compose -f docker-compose.dev.yml down -v
```
Expected: `Container arm-dev  Removed` and `Volume ...arm-home  Removed` / `...arm-config  Removed`.

- [ ] **Step 4: Bring it back up to confirm reset boots cleanly from scratch**

Run:
```bash
docker compose -f docker-compose.dev.yml up -d
```
Then re-check logs as in Task 3 Step 3:
```bash
docker compose -f docker-compose.dev.yml logs --no-log-prefix arm-dev
```
Expected: the two `[OK]: ARM UID and GID set correctly` lines and `Config not found! Creating config file` reappear (fresh volumes), and the UI starts.

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md
git commit -m "Document Docker dev-environment workflow in CLAUDE.md"
```

---

## Self-Review

**Spec coverage:**
- Committed `docker-compose.dev.yml`, single `arm-dev` service, build from local Dockerfile, Option A `my_init`, no `--device`, `8080:8080`, `privileged`, bind-mount `.:/opt/arm`, named volumes for `/home/arm` + `/etc/arm/config`, env `ARM_UID/ARM_GID/TZ/PYTHONUNBUFFERED` → Task 2. ✓
- Dev-workflow docs appended to `CLAUDE.md` → Task 5. ✓
- `.gitattributes` LF safeguard → Task 1. ✓
- Config/DB auto-staging + UI on first boot (data flow) → Task 3. ✓
- Tests via `exec`, single-test selector, CI-equivalent flake8 → Task 4. ✓
- udev-noise caveat, pytest/flake8 availability resolved deterministically via `requirements-dev.txt`, `down -v` reset, submodule init → Tasks 1, 4, 5. ✓
- Success criteria (UI reachable, tests pass, flake8 runs, live edits reflected, `down -v` resets) → Tasks 3, 4, 5. ✓
- The spec's single "open verification point" (pytest/flake8 presence) is closed by committing `requirements-dev.txt` and always installing it — an improvement over the spec, consistent with its intent.

**Placeholder scan:** No TBD/TODO/"handle edge cases" placeholders. The only bracketed text is `<describe the adjustment>` in Task 3 Step 5, which is a conditional commit message filled only if a boot fix was needed — acceptable.

**Type/name consistency:** Service name `arm-dev`, container name `arm-dev`, image `arm-dev:local`, volumes `arm-home`/`arm-config`, env `ARM_UID`/`ARM_GID`, and the `-f docker-compose.dev.yml` flag are used identically across all tasks and the CLAUDE.md docs.
