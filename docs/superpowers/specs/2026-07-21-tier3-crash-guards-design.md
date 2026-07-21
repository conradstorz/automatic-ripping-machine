# Tier 3 — Crash/500 Robustness Guards — Design

Date: 2026-07-21
Status: Approved

From the whole-project failure-mode audit: defensive guards so bad/missing input, missing rows,
or edge states degrade gracefully (404 / clean failure) instead of crashing a request (500) or
the ripper. All findings re-verified present (except the `os.stat(None)` one, which does not
occur — `find_largest_file` returns `""`, never `None`).

## Commit 1 — always-broken routes + data-integrity fall-throughs

- `/activerips` (`arm/ui/jobs/jobs.py`): `Job.query.filter_by(~Job.finished)` →
  `Job.query.filter(~Job.finished)` (filter_by takes kwargs; the expression always raised → 500).
- `/error` (`arm/ui/routes.py`): `def was_error(error=None)` and read the message from
  `request.args` so `GET /error` no longer 500s on the missing positional arg.
- `git_check_version` (`arm/ui/utils.py`): initialize `local_version = "unknown"` before the try
  so a missing/unreadable VERSION file returns cleanly instead of `UnboundLocalError` (which 500s
  every `/settings` load).
- `check_db_version` / `arm_db_migrate` (`arm/ui/utils.py`): the post-upgrade revision-mismatch
  `else` logs "…Exiting arm." but falls through, leaving a half-upgraded DB in use. Make both
  `raise RuntimeError(...)` so a failed migration actually stops startup.

## Commit 2 — model/ripper robustness

- `JobState(self.status)` in the `finished` hybrid getter and the `idle`/`ripping` properties
  (`arm/models/job.py`): wrap in `try/except ValueError` → return `False` when `status` is `None`
  or an unrecognized string (freshly-constructed job, legacy row). The SQL `finished.expression`
  is unaffected.
- `arm_db_get` (`arm/ui/utils.py`): null-check `alembic_db.query.first()` → return `None`
  (treat as needs-init) instead of dereferencing `.version_num` on `None`.
- `duplicate_run_check` (`arm/ripper/utils.py`): `if drive is None: return None` before
  `drive.processing` (a disc in an unregistered drive would otherwise crash job start).
- HandBrake `-1` sentinel (`arm/ripper/handbrake.py`): `handbrake_char_encoding` returns `None`
  on failure (not `-1`), so `get_track_info`'s `if ... is not None` guard reaches the graceful
  "unable to get track information" branch instead of `TypeError` iterating an int. Update the
  docstring.

## Commit 3 — UI None-deref → 404, input validation, auth

- None-deref handlers → guard clause. GET detail views `abort(404)`; form-mutation handlers
  `flash(...)` + redirect back. Sites: `jobdetail` (currently raises `ValueError`→500; make 404),
  `jobdetail_load`, `customtitle`, `changeparams` (`arm/ui/jobs/jobs.py`), `change_job_params`
  (`arm/ui/json_api.py`), `save_ui_settings`, `server_info`, `drive_manual`
  (`arm/ui/settings/settings.py`), `update_password` (`arm/ui/auth/auth.py`).
- `/logs` (`arm/ui/logs/logs.py`): `request.args.get('mode')`/`.get('logfile')` + validate,
  instead of `request.args['...']` (KeyError→500 on missing params).
- `logreader` (`arm/ui/logs/logs.py`): null-check `logfile` and validate BEFORE `os.path.join`;
  catch validation failures and `abort(400/404)` instead of surfacing `ValidationError`/
  `FileNotFoundError` as 500s.
- `login` (`arm/ui/auth/auth.py`): fix `from sqlite3 import OperationalError` →
  `from sqlalchemy.exc import OperationalError` (so the intended guard actually catches DB
  errors), and when the user table is empty redirect to the DB-setup flow instead of
  dereferencing `admin = None` on POST.

## Testing (in-container)

- Unit: `JobState(None)`/unknown → `finished`/`idle`/`ripping` return `False`; `git_check_version`
  with a missing VERSION returns `("unknown", ...)` not `UnboundLocalError`; `handbrake_char_encoding`
  failure path returns `None` (and `get_track_info` tolerates a non-list).
- Route (Flask test client + `LOGIN_DISABLED`): `/activerips` and `/error` return non-500; a
  representative bad-id handler returns 404.
- The remaining handler guards verified by inspection.

## Files touched

`arm/ui/jobs/jobs.py`, `arm/ui/routes.py`, `arm/ui/utils.py`, `arm/ui/json_api.py`,
`arm/ui/settings/settings.py`, `arm/ui/auth/auth.py`, `arm/ui/logs/logs.py`,
`arm/models/job.py`, `arm/ripper/utils.py`, `arm/ripper/handbrake.py`, plus tests.

No DB/model/migration changes.
