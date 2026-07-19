# History Tab Filtering — Design

Date: 2026-07-19
Status: Approved (pending spec review)

## Problem

The History tab (`/history`) lists every job in reverse-`job_id` order with server-side
pagination, but offers no way to narrow the list. Finding, for example, only the failed
rips, or only jobs from a given week, means paging through everything. Users want to filter
history by **outcome** (successful / failed / in-progress) and by **date range**.

## Goal

Add server-side filtering to the History page:

- Filter by job outcome: All / Successful / Failed / In-progress.
- Filter by a start-date range (From / To), either bound optional.
- Filters combine (AND) and survive pagination.
- No database schema changes, no migration.

## Non-goals

- Title/text search (already exists as a separate JSON API concept; out of scope here).
- Disc-type filtering.
- Client-side/instant filtering (rejected: only filters the current page, conflicts with
  server-side pagination).
- Sorting changes (existing client-side tablesorter is untouched).

## Current behavior (baseline)

- Route: `arm/ui/history/history.py:24-49`. Reads `page` from query args and runs
  `Job.query.order_by(db.desc(Job.job_id)).paginate(page=page, max_per_page=database_limit,
  error_out=False)`, rendering `history.html` with `jobs=jobs.items`, `pages=jobs`,
  `date_format`.
- Template: `arm/ui/history/templates/history.html`. Fully server-rendered
  (`{% for job in jobs %}`). Columns: Title, Start Time, Duration, Status, Logfile.
  Includes the shared `arm/ui/templates/pagination.html` partial twice (top and bottom),
  passing `pages` and `page_name="route_history.history"`.
- The shared pagination partial builds links with `url_for(page_name, page=...)` — it passes
  **only** `page`, so any active filter would be dropped when paging.
- Job outcome fields (`arm/models/job.py`): `status` is a plain `String(32)`.
  `JobState.SUCCESS = "success"`, `JobState.FAILURE = "fail"`. The `Job.finished`
  hybrid_property is `status in ("success", "fail")` and is already usable in SQL filters
  (`~Job.finished` = in-progress). `start_time` is a real `db.DateTime` column.
- Precedent: `arm/ui/json_api.py:35-78` `get_x_jobs()` already filters by
  `filter_by(status="success"|"fail")` and `~Job.finished` — this design reuses that exact
  semantics, just on the paginated history query.

## Design

### 1. Route (`arm/ui/history/history.py`)

Read three new optional query params in addition to `page`:

| Param    | Values                                  | Default | Notes |
|----------|-----------------------------------------|---------|-------|
| `status` | `all`, `success`, `fail`, `active`      | `all`   | Unknown value → treated as `all` |
| `from`   | `YYYY-MM-DD`                            | (none)  | Inclusive lower bound on `start_time`; unparseable → ignored |
| `to`     | `YYYY-MM-DD`                            | (none)  | Inclusive upper bound (`< to + 1 day`); unparseable → ignored |

Build the query incrementally, then paginate:

```python
query = Job.query

if status == "success":
    query = query.filter(Job.status == "success")
elif status == "fail":
    query = query.filter(Job.status == "fail")
elif status == "active":
    query = query.filter(~Job.finished)
# else: "all" — no status filter

if from_date is not None:
    query = query.filter(Job.start_time >= from_date)
if to_date is not None:
    query = query.filter(Job.start_time < to_date + timedelta(days=1))

jobs = query.order_by(db.desc(Job.job_id)).paginate(
    page=page, max_per_page=int(armui_cfg.database_limit), error_out=False)
```

Date parsing is defensive: `datetime.strptime(value, "%Y-%m-%d")` inside a try/except; on
failure the bound is ignored (not a 500). `status` is normalized to the allowed set, falling
back to `all`.

Pass the normalized filter values back to the template so the filter bar and pagination can
reflect them: `status`, `from` (raw string), `to` (raw string).

### 2. Template — filter bar (`history.html`)

Above the table, a `<form method="get" action="{{ url_for('route_history.history') }}">`
containing:

- A `<select name="status">` with options All / Successful / Failed / In-progress, the
  current `status` marked `selected`.
- `<input type="date" name="from">` and `<input type="date" name="to">`, pre-filled with the
  current `from`/`to` values.
- An **Apply** submit button and a **Clear** link back to bare `/history`.

Styling follows the existing Bootstrap/AdminLTE form conventions already used elsewhere in
the UI (e.g. inline form controls). The bar renders once, above the top pagination.

Note: submitting the form omits `page`, so applying a new filter naturally returns to page 1
(correct — the old page number may not exist under the new filter).

### 3. Pagination — thread filters through links

The shared `pagination.html` currently calls `url_for(page_name, page=...)`. To keep the
active filter while paging, the history route will pass the active filter params to the
template, and the pagination includes will forward them.

Approach: pass an optional `page_args` dict from the history template into the
`pagination.html` include, and have the partial spread it into each `url_for` call
(`url_for(page_name, page=p, **page_args)`). `page_args` defaults to an empty dict via
`{{ ... | default({}) }}` (or a Jinja `set`), so **every other page that includes the partial
is unaffected** — they simply don't pass `page_args`.

The history template builds `page_args` from the active filter (only including keys with a
value), e.g. `{"status": status, "from": from, "to": to}` minus empties.

## Error handling

- Bad `status` → `all`. Bad/absent dates → that bound is dropped. No user-facing errors,
  no 500s.
- `error_out=False` on paginate is retained, so an out-of-range `page` yields an empty list
  rather than a 404 (unchanged behavior).
- Empty result set: the table renders with no rows (existing template handles an empty
  `jobs` loop gracefully; a short "no jobs match" message may be added inside the
  `{% for %}`/`{% else %}`).

## Testing

- Unit/route tests hitting the history route with combinations:
  `/history`, `/history?status=fail`, `/history?status=success`, `/history?status=active`,
  `/history?from=2026-01-01&to=2026-01-31`, combined status+date, and a garbage
  `status`/`from` to confirm graceful fallback.
- Assert the returned job set matches the filter (seed a few `Job` rows with distinct
  `status` and `start_time` in the test DB).
- Confirm pagination links in the rendered HTML carry the filter params.
- Run within the existing `test/unittest/` harness (container/Linux env per project docs).

## Files touched

- `arm/ui/history/history.py` — filter params + query building.
- `arm/ui/history/templates/history.html` — filter bar + build `page_args`.
- `arm/ui/templates/pagination.html` — forward optional `page_args` into `url_for`
  (backward-compatible default).
- `test/unittest/` — new test(s) for history filtering.

No changes to `arm/models/`, no Alembic migration.
