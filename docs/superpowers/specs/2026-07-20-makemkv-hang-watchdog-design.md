# Bound makemkvcon so it can never hang ARM — Design

Date: 2026-07-20
Status: Approved

## Problem

`makemkvcon` (MakeMKV v1.18.4) can silently wedge at 100% CPU on damaged/protected discs or
bad drive SCSI states. In production two jobs sat in the `info` stage for 17 and 41 hours,
each with a `makemkvcon info` child pinned at 100% CPU that emitted **zero** output, until an
external kill (container recreate) unblocked ARM.

Root cause is entirely on the ARM side: `arm/ripper/makemkv.py::run()` reads the child with
`for line in proc.stdout:` — a blocking readline with **no timeout, no watchdog**. A silent
child blocks the ripper forever; the job can only leave `info` via a `finally:` that runs only
when `run()` returns. Nothing detects or kills a runaway makemkvcon.

Confirmed ARM-side defects (two independent investigations agreed):
- **D1** No timeout on the makemkvcon wait — `makemkv.py:1204-1206`. (primary)
- **D2** Job pinned in `info` because the state transition is gated on `run()` returning — `makemkv.py:602-618`.
- **D3** No time-based stuck-job detector; `clean_old_jobs` keys off the ripper's own PID (alive during the hang) and only runs at new-job start — `utils.py:746-768`, `main.py:232`.
- **D4** Nothing kills a runaway makemkvcon; Abandon signals `job.pid = os.getpid()` (the ripper), not the child — `job.py:253-256`, `json_api.py:478-524`.
- **D5** Cascade: a lingering hung makemkvcon keeps the process count up, so later jobs' `sleep_check_process` loops unbounded — `utils.py:140-152`.
- **D6** `stdin` inherited/unclosed on the child — potential prompt deadlock — `makemkv.py:1204`.

## Goal

A wedged makemkvcon can never take ARM hostage. Detect a hung child, kill it, and let the
existing error path fail the job and eject the disc. Do not penalize legitimately-long rips.

## Approach (agreed)

- **Timeout strategy:** inactivity watchdog — kill makemkvcon if it produces **no output** for
  N seconds. Works for both the short `info` scan and the long actual rip (a healthy makemkv
  emits progress every ~1s; a hung one goes silent — the incident emitted zero output).
- **Scope:** core (inactivity timeout + kill-tree + `stdin=DEVNULL`) + bound `sleep_check_process`
  (D5) + a stuck-job watchdog (D3). Not a standalone Abandon change — the core already kills the
  child on the timeout path.

## Design

### 1. Core — inactivity watchdog in `run()` (`arm/ripper/makemkv.py`)

`run()` is a generator shared by the info scan and the actual rip, so the guard must be
inactivity-based (not wall-clock).

- **Reader thread + queue.** A helper `iter_lines_with_timeout(stream, timeout)` starts a daemon
  thread that does `for line in stream: q.put(line)` then enqueues an EOF sentinel. The caller
  does `q.get(timeout=timeout)`; each line resets the timer. On `queue.Empty` it raises an
  internal `MakeMkvInactivityError`. The timer starts at spawn (covers the zero-output case) and
  resets per line (long rips that keep emitting progress are never tripped).
- **Spawn** with `stdin=subprocess.DEVNULL` (D6) in addition to the existing `stdout=PIPE, text=True`.
- **On inactivity:** log an error, `kill_process_tree(proc.pid)` (SIGTERM children+parent, 5s grace,
  then SIGKILL survivors — via psutil, mirroring `json_api.terminate_process`), and raise
  `MakeMkvRuntimeError` so the existing caller path fails the job (and, via the existing
  eject-on-failure work in `clean_old_jobs`/`main.py`, ejects the disc).
- **Always clean up:** a `finally:` inside the `with subprocess.Popen(...)` block calls
  `kill_process_tree` if the child is still alive, so `Popen.__exit__`'s `proc.wait()` can never
  block on a hung child, and an early consumer close (GeneratorExit) also kills the child (no orphan).
- **Config:** `MAKEMKV_MAX_INACTIVITY_SECS`, default **300**.

New helpers (module-level, unit-testable in isolation):
- `iter_lines_with_timeout(stream, timeout)` → generator of lines; raises `MakeMkvInactivityError`.
- `kill_process_tree(pid)` → best-effort SIGTERM→SIGKILL of a process and its descendants.
- `MakeMkvInactivityError(Exception)` — internal marker.

### 2. Bound `sleep_check_process` (D5) (`arm/ripper/utils.py`)

Add a cumulative max-wait cap to the `while loop_count >= max_processes:` loop. Track total slept
seconds; when it reaches `MAKEMKV_CONCURRENT_WAIT_MAX_SECS` (default **3600**), log a warning and
`break` (proceed rather than spin forever). No other behavior change.

### 3. Stuck-job watchdog (D3)

Defense-in-depth for orphans/crashes; designed to never kill a legitimately-long rip (no
age-based killing).

- **`reap_orphan_makemkv()`** (new, `arm/ripper/utils.py`): iterate `psutil.process_iter`, and for
  each process named `makemkvcon` whose parent is `init` (ppid == 1, i.e. genuinely reparented
  after its ARM parent died), `kill()` it. A makemkvcon with a live ARM parent is never touched.
- **Periodic runner** in `arm/runui.py` (the long-running UI process): a daemon thread that every
  `JOB_WATCHDOG_INTERVAL_SECS` (default **300**) runs, inside an `app.app_context()`,
  `clean_old_jobs()` (existing dead-PID reap + eject) and `reap_orphan_makemkv()`. Exceptions are
  caught and logged so the thread never dies. The thread respects `shutdown_requested`.

### 4. Config (`setup/arm.yaml` + `arm/ui/comments.json`)

Three new keys with comments, grouped with the existing MakeMKV settings:
- `MAKEMKV_MAX_INACTIVITY_SECS: 300`
- `MAKEMKV_CONCURRENT_WAIT_MAX_SECS: 3600`
- `JOB_WATCHDOG_INTERVAL_SECS: 300`

Read via `cfg.arm_config.get(KEY, default)` so a user yaml lacking them still works.

## What this fixes

D1, D2, D6, and D4-for-the-child via the core inactivity watchdog + kill-tree; D5 via the bounded
wait; D3 via the periodic reaper. The MakeMKV-internal trigger (v1.18.4 wedging on bad discs) is
external and unfixable here — the design bounds its blast radius to `MAKEMKV_MAX_INACTIVITY_SECS`
plus a failed+ejected job instead of a multi-day 100%-CPU hang.

## Testing (in-container)

- `iter_lines_with_timeout`: a silent child (`python3 -c "import time; time.sleep(30)"`) raises
  `MakeMkvInactivityError` within ~timeout; a chatty child yields its lines and finishes cleanly.
- `kill_process_tree`: spawns a parent+child sleep tree, asserts both are gone after the call.
- `run()` end-to-end: with a fake makemkvcon-like silent process and a short timeout, `run()` raises
  `MakeMkvRuntimeError` and leaves no surviving child.
- `sleep_check_process`: with `psutil.process_iter` and `time.sleep` patched to force the over-limit
  branch and a tiny cap, asserts it returns after ~cap, not forever.
- `reap_orphan_makemkv`: with `psutil.process_iter` patched to yield a fake orphan (name
  `makemkvcon`, ppid 1) and a fake parented one, asserts only the orphan is killed.

## Files touched

- `arm/ripper/makemkv.py` — inactivity watchdog, helpers, `stdin=DEVNULL`.
- `arm/ripper/utils.py` — bounded `sleep_check_process`, `reap_orphan_makemkv`.
- `arm/runui.py` — periodic watchdog thread.
- `setup/arm.yaml`, `arm/ui/comments.json` — 3 config keys.
- `test/unittest/` — new tests for the helpers, the bounded wait, and the reaper.

No DB/model/migration changes.
