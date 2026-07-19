# Graceful Empty State When DB File Is Missing — Design

Date: 2026-07-19
Status: Approved

## Problem

`/history` and `/database` both crash with HTTP 500 when the ARM database file
(`arm_config['DBFILE']`) does not exist. Their missing-DB branch sets `jobs = {}` and
then calls `render_template(..., jobs=jobs.items, pages=jobs)`:

- `jobs.items` passes the bound `dict.items` **method**; the template's
  `{% for job in jobs %}` then iterates a method → `TypeError`.
- `pages = {}` (a bare dict) reaches `pagination.html`, which accesses `pages.page` →
  Jinja `UndefinedError`.

The home page (`routes.py`) already avoids this: it passes `jobs=jobs` (never `.items`),
does not paginate, and redirects to setup on a DB error. This design brings `/history` and
`/database` up to the same graceful standard.

## Goal

When the DB file is missing, `/history` and `/database` render normally with an empty job
list, no pagination, and a friendly notice — instead of 500-ing. Behavior when the DB
exists is unchanged.

## Non-goals

- No "database setup/redirect" flow from these pages (the app's startup `arm_db_check`
  and `/dbupdate` already own DB creation).
- No change to the home page.
- No config/model/migration changes.

## Design

### Routes (`arm/ui/history/history.py`, `arm/ui/database/database.py`)

Replace the `jobs = {}` fallback with an explicit, template-safe state and stop calling
`.items` on the fallback. In both routes:

- DB present branch: build the paginated `jobs` as today, then
  `job_items = jobs.items`, `db_missing = False`.
- DB missing branch: log the existing error, then `jobs = None`, `job_items = []`,
  `db_missing = True`.
- Render with `jobs=job_items, pages=jobs, db_missing=db_missing` (plus history's existing
  filter kwargs, unchanged).

Because `pages` is now either a real `Pagination` object (truthy) or `None` (falsy), the
template can guard on it directly.

### Templates (`history.html`, `databaseview.html`)

- Wrap each `pagination.html` include in `{% if pages %}…{% endif %}` so pagination only
  renders when a real Pagination object exists.
- Add a notice, shown only when `db_missing`:
  `<div class="alert alert-warning text-center">No database found — no jobs to show.</div>`
  Placed above the job list. The job loop over an empty `job_items` then renders nothing.

History's filter bar is left in place when `db_missing` (harmless; submitting it just
reloads the same empty state).

## Error handling

- DB missing → empty state + notice, HTTP 200. No 500.
- DB present, zero matching jobs → unchanged (empty table, pagination shows page 1 of 0).

## Testing

`test/unittest/test_ui_missing_db_render.py`: render `history.html` and `databaseview.html`
inside a Flask request context with the missing-DB state (`pages=None`, `db_missing=True`,
`jobs=[]`) and assert each renders without raising and contains the notice text. This locks
out the exact 500 regression. Runs in-container like the other `arm.ui` tests.

## Files touched

- `arm/ui/history/history.py` — safe missing-DB state.
- `arm/ui/database/database.py` — safe missing-DB state.
- `arm/ui/history/templates/history.html` — pagination guard + notice.
- `arm/ui/database/templates/databaseview.html` — pagination guard + notice.
- `test/unittest/test_ui_missing_db_render.py` — regression test.

No config/model/migration changes.
