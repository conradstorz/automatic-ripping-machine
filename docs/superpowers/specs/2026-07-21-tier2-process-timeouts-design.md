# Tier 2 — Universal External-Process Timeouts — Design

Date: 2026-07-21
Status: Approved

## Problem

The makemkvcon hang fixed earlier was one instance of a codebase-wide pattern: every external
process (subprocess AND HTTP) that ARM invokes can wedge with **no timeout**, hanging a rip
forever (subprocess) or a waitress worker (HTTP). The whole-project audit enumerated them.

## Approach (agreed)

- Long media subprocesses → **inactivity watchdog** (kill on no-sign-of-life for N seconds),
  never a naive wall-clock that would kill a legitimately-long transcode/rip.
- One **shared helper** extracted from the proven makemkv watchdog; applied everywhere; one branch.
- Short subprocesses → simple wall-clock `timeout=`.
- HTTP → mandatory `timeout=` + adequate exception handling.

## Design

### 1. Shared helper — `arm/ripper/proc_watchdog.py` (new)

Move the generic, already-tested pieces out of `makemkv.py` and add a general runner:

- `kill_process_tree(pid)` — psutil SIGTERM→SIGKILL of a process + descendants (moved from makemkv).
- `heartbeat_idle(last_output, progress_file, now)` — seconds since the freshest of
  {last stdout line, `progress_file` mtime} (moved from makemkv's `_heartbeat_idle`).
- `ProcessInactivityError(Exception)` — raised on watchdog kill.
- `run_watched(cmd, inactivity, progress_file=None, shell=False, on_line=None)` → captured stdout str:
  - `Popen(cmd, stdout=PIPE, stderr=STDOUT, stdin=DEVNULL, text=True, shell=shell)`.
  - Daemon reader thread → `queue.Queue`; main loop `get(timeout=min(inactivity, 5))`.
  - Each real line: append to buffer, call `on_line(line)` if given, refresh `last_output`.
  - Every wake: if `inactivity` and `heartbeat_idle(...) >= inactivity` → `kill_process_tree` +
    raise `ProcessInactivityError`.
  - `finally`: kill the tree if still alive (no orphan; `Popen.__exit__` can't block).
  - On non-zero exit → `subprocess.CalledProcessError` (matches `check_output` semantics callers expect).
  - `inactivity <= 0` / `None` disables the watchdog (blocks like before).

`makemkv.py` imports `kill_process_tree`/`heartbeat_idle` from here (its specialised `run()` stays,
just de-duplicated).

### 2. Long media commands — inactivity watchdog, correct heartbeat per tool

| Tool | Site | Heartbeat |
|------|------|-----------|
| HandBrake transcode | `handbrake.py:31` `run_handbrake_command` | HandBrake logfile mtime (`progress_file=` the HB logfile) |
| ffmpeg transcode | `ffmpeg.py:500` `run_transcode_cmd` | stdout (`on_line=` preserves the existing `time=` progress parse) |
| abcde | `utils.py:530` `rip_music` | abcde logfile mtime |
| dd | `utils.py:591` `rip_data` | `.part` output-file mtime (dd writes it continuously; stale only when wedged) |

Each swaps its blocking `check_output`/manual loop for `run_watched(..., inactivity=config_int(
'SUBPROCESS_MAX_INACTIVITY_SECS', 300), progress_file=<heartbeat>)`. On watchdog kill the existing
failure paths mark the job FAILURE (and, for ffmpeg/HandBrake/dd, the CalledProcessError/raise
paths already handled by Tier 1 preserve state).

### 3. Short commands — wall-clock timeout

- `ProcessHandler.arm_subprocess(cmd, shell=False, check=False, timeout=None)`: pass
  `timeout=timeout or config_int('SUBPROCESS_TIMEOUT_SECS', 60)` to `check_output`; catch
  `subprocess.TimeoutExpired` → return `None` (or re-raise if `check=True`, like other errors).
  Covers all 7 callers (`mount`/`lsdvd`/`findmnt`/`eject`/HW-probe/git/bash-notify).
- Add `timeout=config_int('SUBPROCESS_TIMEOUT_SECS', 60)` directly to ffprobe (`ffmpeg.py:70,483`)
  and HandBrake `--scan` (`handbrake.py:369,381`); handle `TimeoutExpired` in their existing except.
- `identify.py:96` `os.system("umount " + devpath)` → `arm_subprocess(["umount", job.devpath])`
  (inherits timeout, drops the shell + string concatenation).

### 4. HTTP — mandatory timeout + adequate except

Add `timeout=config_int('HTTP_TIMEOUT_SECS', 15)` to all 13 sites; widen too-narrow excepts to the
base class (the reference is `ui/utils.py:916` `requests.get(url, timeout=10)` +
`except requests.RequestException`):

- `identify.py:168` urlopen (already broad `except Exception`, keep).
- `utils.py:421` `scan_emby` — add timeout; widen `except HTTPError` → `except requests.RequestException`.
- `ui/utils.py:606` `send_to_remote_db` — add timeout; wrap in try/except `requests.RequestException`.
- `ui/metadata.py` (10 sites: `:43,76,86` urlopen; `:119,169,218,223,243,302` requests.get) — add
  timeout; the no-handler `requests.get` sites gain a `requests.RequestException` guard that logs and
  returns the function's empty/None fallback; `call_omdb_api` widen `except HTTPError` → `(HTTPError, URLError)`.
- musicbrainz (`music_brainz.py:108,306,382`): library has no per-call hook → set
  `socket.setdefaulttimeout(config_int('HTTP_TIMEOUT_SECS', 15))` once at ripper startup (`main.py`).

### 5. Config — 3 new keys

`setup/arm.yaml` + `arm/ui/comments.json`, read via `utils.config_int(..., default)`:
- `SUBPROCESS_MAX_INACTIVITY_SECS: 300`
- `SUBPROCESS_TIMEOUT_SECS: 60`
- `HTTP_TIMEOUT_SECS: 15`

`MAKEMKV_MAX_INACTIVITY_SECS` is left as-is (makemkv keeps its own).

## Testing (in-container)

- `proc_watchdog.run_watched`: hung child (silent) killed + raises within ~inactivity; healthy child
  with a fresh progress_file NOT killed; stdout-heartbeat child (chatty) not killed and yields lines;
  non-zero exit → CalledProcessError; disabled (`inactivity<=0`) not killed; `on_line` invoked per line.
- `kill_process_tree`/`heartbeat_idle`: moved tests still pass (re-point imports).
- `arm_subprocess`: `TimeoutExpired` → None; `check=True` → re-raises.
- HTTP: patch `requests.get`/`urlopen` and assert `timeout=` is passed; `scan_emby`/`send_to_remote_db`
  swallow a `RequestException` instead of propagating.
- Long-command integrations verified with the fake-executable pattern used for makemkv.

## Files touched

- New: `arm/ripper/proc_watchdog.py`, `test/unittest/test_ripper_proc_watchdog.py`.
- `arm/ripper/makemkv.py` — import shared `kill_process_tree`/`heartbeat_idle`.
- `arm/ripper/handbrake.py`, `arm/ripper/ffmpeg.py`, `arm/ripper/utils.py`,
  `arm/ripper/ProcessHandler.py`, `arm/ripper/identify.py`, `arm/ripper/main.py`.
- `arm/ripper/music_brainz.py`, `arm/ui/metadata.py`, `arm/ui/utils.py`.
- `setup/arm.yaml`, `arm/ui/comments.json`.
- Tests under `test/unittest/`.

No DB/model/migration changes.
