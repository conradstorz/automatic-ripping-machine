# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Automatic Ripping Machine (ARM) is a headless server that detects an inserted optical disc (Blu-ray, DVD, CD) via `udev`, identifies whether it's video/audio/data, and rips it — using MakeMKV/HandBrake/ffmpeg for video, abcde for audio, or an ISO backup for data. It ships as a Docker container and exposes a Flask web UI for managing jobs. Runtime target is **Linux inside Docker**; the codebase is not meant to run natively on Windows/macOS (it depends on `udev`, `/dev/srX` devices, `/etc/fstab`, MakeMKV, HandBrake, abcde, etc.).

## Two processes, one codebase

ARM is really two long-lived programs sharing the same models and SQLite database:

1. **The ripper** — [arm/ripper/main.py](arm/ripper/main.py). Launched **once per disc insertion** by a udev rule (`setup/51-docker-arm.rules`), which calls the wrapper in [scripts/docker/docker_arm_wrapper.sh](scripts/docker/docker_arm_wrapper.sh) with `-d <devpath>`. `main()` runs the pipeline: `identify` → dupe check → notify → branch on `job.disctype` (`dvd`/`bluray` → `arm_ripper.rip_visual_media`, `music` → `music_brainz` + `utils.rip_music`, `data` → `utils.rip_data`). Each invocation is a fresh process for one disc.

2. **The web UI** — [arm/runui.py](arm/runui.py). A long-running Flask app served by **waitress** (40 threads, to survive blocking polls of the ripper during rips). It reads/writes the same DB the ripper populates, so the UI can watch and edit in-flight jobs.

Both import from `arm.ripper`, `arm.models`, `arm.ui`, and `arm.config`. The Flask `app`, `db`, and blueprints are created in [arm/ui/__init__.py](arm/ui/__init__.py) — importing `arm.ui` has the side effect of constructing the app and registering all blueprints.

## Layout

- `arm/ripper/` — the ripping engine. Key modules: `identify` (disc type + metadata), `arm_ripper` (visual media orchestration), `makemkv`, `handbrake`, `ffmpeg`, `music_brainz`, `apprise_bulk` (notifications), `ProcessHandler`, `utils` (large grab-bag of rip/file helpers), `logger`.
- `arm/ui/` — Flask app. One subpackage per feature area (`jobs/`, `settings/`, `history/`, `logs/`, `auth/`, `database/`, `notifications/`, `sendmovies/`), each a **blueprint** with its own `templates/`. `routes.py` holds the root routes; `json_api.py` is the AJAX/polling API the front end uses to track jobs live.
- `arm/models/` — SQLAlchemy models: `job` (central; has `JobState` enum and `disctype` = dvd/bluray/data/music/unknown), `track`, `config` (per-job config snapshot), `system_drives`, `system_info`, `ui_settings`, `notifications`, `user`.
- `arm/config/` — `config.py` loads `arm.yaml` (path from `ARM_CONFIG_FILE`, default `/etc/arm/config/arm.yaml`), merges it over the template `setup/arm.yaml`, and rewrites the user's yaml with grouped comments from `arm/ui/comments.json`. Access config globally via `arm.config.config.arm_config[...]`.
- `arm/migrations/` — Alembic (via Flask-Migrate) migrations. The DB is SQLite. `runui.py` runs `arm_db_check()` on startup and the UI has a database-update flow rather than auto-migrating silently.
- `setup/` — default config templates (`arm.yaml`, `apprise.yaml`, `.abcde.conf`) and udev rules, copied into place at install/container start.
- `scripts/` — Docker runit/runsv service scripts, installers, and thick-client wrappers.
- `devtools/` — standalone dev helper (`armdevtools.py`); see below.
- `test/unittest/` — the test suite.
- `arm-dependencies/` — **git submodule** pinning the heavy Python deps (see below). May be empty on a fresh clone until initialized.

## Dependencies

`requirements.txt` starts with `-r arm-dependencies/requirements.txt` — the bulk of dependencies live in the **`arm-dependencies` git submodule**, and the container is built `FROM automaticrippingmachine/arm-dependencies:<version>` (see [Dockerfile](Dockerfile)). If the submodule directory is empty, run `git submodule update --init` before anything that resolves requirements. Follows the project's Python constraint of 3.9–3.12.

## Commands

Per global instructions, prefer `uv` for Python and do not chain commands with `&&` (the permission system blocks chains — use separate calls).

**Lint** (this is what CI enforces — see [.github/workflows/main.yml](.github/workflows/main.yml)):
```
flake8 . --max-complexity=15 --max-line-length=120 --show-source --statistics
```
`setup.cfg` excludes `migrations/`; note `.pylintrc` sets max-line-length 120 but `setup.cfg` flake8 sets 160 — CI's explicit `--max-line-length=120` is the binding value.

**Tests** — `unittest`-based, run with pytest:
```
uv run pytest test/unittest/
uv run pytest test/unittest/test_ripper_utils_file_matching.py           # single file
uv run pytest test/unittest/test_ripper_utils_file_matching.py::TestFileMatching::test_find_matching_file_exact_match   # single test
```
Caveat: tests do `sys.path.insert(0, '/opt/arm')` (the container install path) and import modules that pull in native/optical-media libs, so the suite is designed to run **inside the container / a configured Linux env**, not on a bare Windows checkout.

**Run the UI locally** (as CI smoke-tests it) — requires config files staged at `/etc/arm/config/` and `INSTALLPATH` set up; the CI `main.yml` "Fix config files" step shows the exact staging needed. Then:
```
python ./arm/runui.py
```

**Dev tools** — [devtools/armdevtools.py](devtools/armdevtools.py) is intentionally dependency-free and standalone:
```
./devtools/armdevtools.py -qa      # run flake8 QA across ARM
./devtools/armdevtools.py -pr      # run pre-PR checks
./devtools/armdevtools.py -b <branch>   # branch switch helper
./devtools/armdevtools.py -db_rem  # remove arm.db to test fresh-install path
```

## Conventions & gotchas

- **Branching/PRs**: `CONTRIBUTING.md` names old branches (`v2_fixes`, `v2.x_dev`), but the live default branch is `main` and CI runs on push/PR to `main`. Confirm the intended target branch rather than trusting the doc.
- **`VERSION`** holds the app version (currently `2.24.0`); a `version_bump` workflow manages bumps.
- **Config is global mutable state**: `arm.config.config` loads and *rewrites* the user's `arm.yaml` on import (adding comments), and the UI can also edit config rows in the DB. Be careful that changes to config keys stay consistent across `setup/arm.yaml`, `arm/ui/comments.json` (comment grouping), and any model/migration.
- **Job lifecycle** is DB-driven: the ripper mutates a `Job` row through `JobState` values and `db.session.commit()`s; the UI polls those rows. When touching rip flow, keep the job status/stage transitions intact — the setup code specifically installs a SIGTERM handler so `finally:` blocks run and the DB isn't left mid-transaction.
- **Security notes**: `arm/ui/__init__.py` currently hardcodes `SECRET_KEY` and the Werkzeug debug PIN (both marked TODO). Login can be disabled globally via the `DISABLE_LOGIN` config key.
- CI also runs CodeQL (python + javascript) and a shellcheck workflow for the shell scripts under `scripts/`.

## Local development (Docker)

`docker-compose.dev.yml` provides a container for working on ARM's **non-hardware
ripper logic** (identification, metadata, file naming, notifications, config). It builds
the production `Dockerfile` but runs without optical-device passthrough, so it cannot rip a
physical disc — verify ripper logic via `test/unittest/` and crafted `Job`/`Track` records
viewed in the UI.

**Source is baked into the image, not bind-mounted.** The `Dockerfile` `COPY`s the repo to
`/opt/arm` at build time, so this works even when the Docker daemon is **remote** (an SSH
`docker context`) and cannot see your working tree. The trade-off: there is **no live edit** —
after changing code on the host, rebuild to pick it up (fast; the dependency base image is cached):
```
docker compose -f docker-compose.dev.yml build
docker compose -f docker-compose.dev.yml up -d          # recreate from the new image
```

Bring it up (first build pulls the multi-GB dependencies base image):
```
docker compose -f docker-compose.dev.yml up -d --build
```

**Where the UI serves:** published ports bind on the **daemon host**, not necessarily
`localhost`. Host port is **8090** → container 8080. With a local engine the UI is at
`http://localhost:8090`; with a remote daemon it is at `http://<daemon-host>:8090`.

Install dev-only tooling (pytest/flake8) once per container lifecycle, then run tests / a
single test / lint inside the container. Use `python3` (there is no `python` on PATH), and
run from `/opt/arm`:
```
docker compose -f docker-compose.dev.yml exec arm-dev pip install -r /opt/arm/requirements-dev.txt
docker compose -f docker-compose.dev.yml exec -w /opt/arm arm-dev python3 -m pytest test/unittest/
docker compose -f docker-compose.dev.yml exec -w /opt/arm arm-dev python3 -m pytest test/unittest/test_ripper_utils_file_matching.py::TestFileMatching::test_find_matching_file_exact_match
docker compose -f docker-compose.dev.yml exec -w /opt/arm arm-dev flake8 . --max-complexity=15 --max-line-length=120 --show-source --statistics
```

Open a Python shell (Flask app context available) to craft `Job`/`Track` records:
```
docker compose -f docker-compose.dev.yml exec -w /opt/arm arm-dev /bin/python3
```

Reset all DB/config state to a clean slate:
```
docker compose -f docker-compose.dev.yml down -v
```

Notes:
- **Windows + Git Bash:** prefix any command that passes a container-absolute path (e.g.
  `/opt/arm/...`) with `MSYS_NO_PATHCONV=1`, or MSYS rewrites it to a Windows path.
- udev logs harmless "no optical device" messages — expected.
- State lives in the `arm-home` and `arm-config` named volumes; `down` keeps it, `down -v` wipes it.
- Known pre-existing test failures (unrelated to this dev env): 6 tests in
  `test_ripper_ARMInfo.py` (bytes-vs-str regex) and `test_ripper_processhandler.py`
  (stale `check_output` mock assertion) fail on the current tree; 23 pass.
