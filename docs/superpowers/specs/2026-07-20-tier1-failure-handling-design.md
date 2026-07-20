# Tier 1 Failure-Handling Fixes — Design

Date: 2026-07-20
Status: Approved

From the whole-project failure-mode review, the four highest-impact bugs: silent data/state
loss and boot-bricking. All are confirmed in code (several by multiple independent audits).

## Fix 1 — `database_updater` / `database_adder` false success

`arm/ripper/utils.py:757` (`database_updater`) and `arm/ui/utils.py:52` (its UI copy), plus
`database_adder` (both files).

Bug: the `for i in range(wait_time)` commit-retry loop has no `break` on success in
`database_updater`, and neither function returns failure when the DB stays locked for **all**
retries — control falls through to `return True`. Under UI+ripper SQLite contention a write that
never landed is reported as success → job state silently lost. The non-locked error path also
`raise`s without `db.session.rollback()`, leaving the session unusable.

Fix (both functions, both files):
- Track a `committed` flag; on a successful commit set it and `break`.
- `db.session.rollback()` before the non-locked `raise`.
- After the loop, if `not committed`: `db.session.rollback()`, `logging.error(...)`, `return False`.

Decision: on lock-exhaustion **return False** (not raise) — preserves the existing
lock-tolerant intent (retry, don't crash the rip) while removing the lie.

## Fix 2 — `config.py` destructive rewrite

`arm/config/config.py:41-72`. `open(arm_config_path, "w")` truncates the user's arm.yaml
**before** reading `comments.json` and building the replacement. A `JSONDecodeError`/`KeyError`
there escapes the `except OSError` with the file already empty → neither ripper nor UI can boot.

Fix: extract the rewrite into a function `write_arm_yaml(arm_config, arm_config_path, install_path)`:
- Build the entire YAML string first (read comments.json, assemble).
- Write to a temp file in the same directory, then `os.replace(tmp, arm_config_path)` (atomic).
- Broaden the guard to `(OSError, KeyError, ValueError, json.JSONDecodeError)`; on any failure,
  log a warning and leave the original file untouched (no partial write).
- Call it at module load where the inline block was.

This also makes the rewrite unit-testable.

## Fix 3 — `main.py` SUCCESS clobbers FAILURE (+ adjacent None-deref)

`arm/ripper/main.py:127-152` and `:264-268`.

- The music-fail branch sets FAILURE, but the data-fail (`:148`) and unknown (`:152`) branches
  only log. `main()` then returns normally, so `__main__`'s `else:` sets `SUCCESS` (`:268`),
  clobbering any FAILURE. Failed data/music/unknown rips are recorded as success.
- Adjacent: the `except` sets `job.status`/`job.errors` (`:264-265`) unconditionally, so a
  setup failure where `job is None` raises `AttributeError`, masking the real error.

Fix:
- Set `job.status = JobState.FAILURE.value` in the data-fail and unknown branches.
- Guard `__main__`'s `else:` so it only sets SUCCESS when `job.status != FAILURE`.
- Move `job.status`/`job.errors` assignment inside the existing `if job:` block in the `except`.

(`__main__` is script-level and not unit-tested in this codebase; verified by inspection. The
data/unknown FAILURE assignments live in `main()`.)

## Fix 4 — `move_files_main` swallows move failures before raw deletion

`arm/ripper/utils.py:370-388`. `shutil.move` failure is only logged; `move_files` returns
normally and post-processing later calls `delete_raw_files` (`arm_ripper.py:99`, which runs
**after** `move_files_post` at `:91`) → the ripped title is deleted from raw and permanently lost.

Fix: on move failure log **and** `raise RipperException(...)`; after a move, verify
`os.path.isfile(new_file)` and raise if missing. The raise aborts before line 99, so raw is
preserved and the job is marked FAILURE (per the confirmed decision: fail loudly, keep raw).

## Testing (in-container)

- `database_updater`/`database_adder`: mock `db.session.commit` to always raise "database is
  locked" → assert `False` + `rollback` called; a clean commit → `True`, committed once (break).
- `write_arm_yaml`: with a valid config + broken `comments.json`, assert the original arm.yaml is
  **preserved** (not emptied) and the function returns without raising; with valid inputs, assert
  the file is rewritten and re-parses.
- `move_files_main`: a move to an unwritable/again-missing destination raises `RipperException`;
  a successful move leaves the destination present and does not raise; an existing destination is
  left untouched.
- `main.py` status logic verified by inspection (script-level).

## Files touched

- `arm/ripper/utils.py` — `database_updater`, `database_adder`, `move_files_main`.
- `arm/ui/utils.py` — `database_updater`, `database_adder`.
- `arm/config/config.py` — extract + atomic `write_arm_yaml`.
- `arm/ripper/main.py` — status finalization + None-deref guard.
- `test/unittest/` — new tests for the DB helpers, config rewrite, and move.

No DB/model/migration changes.
