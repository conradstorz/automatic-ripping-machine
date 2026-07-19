# History Tab Filtering Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add server-side filtering to the History page (`/history`) by job outcome (all / successful / failed / in-progress) and by start-date range, with filters that survive pagination.

**Architecture:** Pure, DB-free helper functions in a new `arm/ui/history/filters.py` normalize the query params (mirroring how the Settings redesign extracted `ripper_fields.build_field_model` for testability). The `history()` route uses those helpers to build a filtered SQLAlchemy query before paginating, reusing the existing `Job.status == "success"/"fail"` and `~Job.finished` semantics from `json_api.get_x_jobs`. The template gains a filter bar, and the shared `pagination.html` partial is extended (backward-compatibly) to carry the active filter through page links.

**Tech Stack:** Python 3.9–3.12, Flask, Flask-SQLAlchemy, Jinja2, Bootstrap/AdminLTE, `unittest` run via pytest.

## Global Constraints

- Python 3.9–3.12 compatible; no new dependencies.
- flake8 clean: `--max-complexity=15 --max-line-length=120` (CI's binding value).
- Do NOT chain shell commands with `&&` (permission system blocks chains — separate calls).
- No database schema changes and no Alembic migration.
- Reuse existing outcome semantics: successful = `Job.status == "success"`, failed = `Job.status == "fail"`, in-progress = `~Job.finished` (the existing hybrid_property).
- `start_time` is a `db.DateTime` column; date bounds compare against it.
- Tests import from the container install path via `sys.path.insert(0, '/opt/arm')` and run inside the dev container / Linux env, not a bare Windows checkout.

---

### Task 1: Pure filter-parsing helpers (`filters.py`)

Create a DB-free module holding the three pure functions the route needs, and unit-test them the same way `test_ui_ripper_fields.py` tests `build_field_model` — plain inputs, no Flask/DB.

**Files:**
- Create: `arm/ui/history/filters.py`
- Test: `test/unittest/test_ui_history_filters.py`

**Interfaces:**
- Consumes: nothing (leaf module; only `datetime` from stdlib).
- Produces (later tasks rely on these exact names/signatures):
  - `ALLOWED_STATUSES` — tuple `("all", "success", "fail", "active")`.
  - `normalize_status(raw: str | None) -> str` — returns `raw` if in `ALLOWED_STATUSES`, else `"all"`.
  - `parse_date(raw: str | None) -> datetime | None` — parses `"YYYY-MM-DD"` to a `datetime`, else `None` (empty or invalid).
  - `build_page_args(status: str, date_from: str, date_to: str) -> dict` — returns only the non-empty/non-default filter params, keyed `"status"`, `"from"`, `"to"`, for threading through pagination `url_for`.

- [ ] **Step 1: Write the failing test**

Create `test/unittest/test_ui_history_filters.py`:

```python
"""Tests for the History page filter-parsing helpers.

These pure functions normalise the /history query params (status + date
range) before the route builds its SQLAlchemy query. They are DB- and
Flask-free so they can be unit-tested directly, the same way the Settings
redesign extracted build_field_model into ripper_fields for testing.
"""
import sys
import unittest
from datetime import datetime

sys.path.insert(0, '/opt/arm')
from arm.ui.history.filters import (   # noqa: E402
    ALLOWED_STATUSES,
    normalize_status,
    parse_date,
    build_page_args,
)


class TestNormalizeStatus(unittest.TestCase):

    def test_recognised_values_pass_through(self):
        for value in ("all", "success", "fail", "active"):
            self.assertEqual(normalize_status(value), value)

    def test_allowed_statuses_constant(self):
        self.assertEqual(ALLOWED_STATUSES, ("all", "success", "fail", "active"))

    def test_unknown_value_falls_back_to_all(self):
        self.assertEqual(normalize_status("garbage"), "all")

    def test_none_falls_back_to_all(self):
        self.assertEqual(normalize_status(None), "all")

    def test_empty_string_falls_back_to_all(self):
        self.assertEqual(normalize_status(""), "all")


class TestParseDate(unittest.TestCase):

    def test_valid_date(self):
        self.assertEqual(parse_date("2026-01-15"), datetime(2026, 1, 15))

    def test_empty_string_is_none(self):
        self.assertIsNone(parse_date(""))

    def test_none_is_none(self):
        self.assertIsNone(parse_date(None))

    def test_malformed_is_none(self):
        self.assertIsNone(parse_date("not-a-date"))

    def test_wrong_format_is_none(self):
        self.assertIsNone(parse_date("01/15/2026"))


class TestBuildPageArgs(unittest.TestCase):

    def test_empty_when_all_defaults(self):
        self.assertEqual(build_page_args("all", "", ""), {})

    def test_status_included_when_not_all(self):
        self.assertEqual(build_page_args("fail", "", ""), {"status": "fail"})

    def test_dates_included_when_present(self):
        self.assertEqual(
            build_page_args("all", "2026-01-01", "2026-01-31"),
            {"from": "2026-01-01", "to": "2026-01-31"},
        )

    def test_all_three_combined(self):
        self.assertEqual(
            build_page_args("success", "2026-01-01", "2026-01-31"),
            {"status": "success", "from": "2026-01-01", "to": "2026-01-31"},
        )


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 2: Run the test to verify it fails**

Run (inside the dev container, from `/opt/arm`):
```
python3 -m pytest test/unittest/test_ui_history_filters.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'arm.ui.history.filters'`.

- [ ] **Step 3: Write the minimal implementation**

Create `arm/ui/history/filters.py`:

```python
"""Pure helpers for parsing the History page filter query params.

Kept DB- and Flask-free so they can be unit-tested directly. The history
route uses these to normalise ?status=&from=&to= before building its
SQLAlchemy query, and to thread the active filter through pagination links.
"""
from datetime import datetime

ALLOWED_STATUSES = ("all", "success", "fail", "active")


def normalize_status(raw):
    """Return raw if it is a recognised status filter, else 'all'."""
    return raw if raw in ALLOWED_STATUSES else "all"


def parse_date(raw):
    """Parse a 'YYYY-MM-DD' string to a datetime; return None if empty/invalid."""
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%d")
    except (ValueError, TypeError):
        return None


def build_page_args(status, date_from, date_to):
    """Non-empty filter params to forward through pagination url_for() calls."""
    args = {}
    if status and status != "all":
        args["status"] = status
    if date_from:
        args["from"] = date_from
    if date_to:
        args["to"] = date_to
    return args
```

- [ ] **Step 4: Run the test to verify it passes**

Run:
```
python3 -m pytest test/unittest/test_ui_history_filters.py -v
```
Expected: PASS (14 tests).

- [ ] **Step 5: Lint**

Run:
```
flake8 arm/ui/history/filters.py test/unittest/test_ui_history_filters.py --max-complexity=15 --max-line-length=120 --show-source --statistics
```
Expected: no output (clean).

- [ ] **Step 6: Commit**

```
git add arm/ui/history/filters.py test/unittest/test_ui_history_filters.py
git commit -m "history: add pure filter-parsing helpers"
```

---

### Task 2: Wire filters into the history route

Use the helpers to build a filtered, paginated query, and pass the active filter state + pagination args to the template. After this task, filtering works via URL (`/history?status=fail&from=2026-01-01`) even before the UI exists.

**Files:**
- Modify: `arm/ui/history/history.py:24-49`

**Interfaces:**
- Consumes: `normalize_status`, `parse_date`, `build_page_args` from `arm.ui.history.filters` (Task 1); `Job.finished` hybrid + `Job.status`/`Job.start_time` columns (existing).
- Produces: `render_template('history.html', ...)` now also passes `status`, `date_from`, `date_to` (formatted `YYYY-MM-DD` strings, empty if unset) and `page_args` (dict) — Task 4's template reads these.

- [ ] **Step 1: Add imports**

At the top of `arm/ui/history/history.py`, add `timedelta` and the helpers. Change the existing import block so it reads:

```python
import os
from datetime import timedelta
from flask_login import LoginManager, login_required  # noqa: F401
from flask import render_template, request, Blueprint, session

import arm.ui.utils as ui_utils
from arm.ui import app, db
from arm.models.job import Job
from arm.ui.history.filters import normalize_status, parse_date, build_page_args
import arm.config.config as cfg
```

- [ ] **Step 2: Replace the query-building body of `history()`**

Replace the current function body (lines 31-49, from `# regenerate the armui_cfg` through the `return`) with:

```python
    # regenerate the armui_cfg we don't want old settings
    armui_cfg = ui_utils.arm_db_cfg()
    page = request.args.get('page', 1, type=int)

    status = normalize_status(request.args.get('status', 'all'))
    date_from = parse_date(request.args.get('from'))
    date_to = parse_date(request.args.get('to'))
    from_str = date_from.strftime("%Y-%m-%d") if date_from else ""
    to_str = date_to.strftime("%Y-%m-%d") if date_to else ""

    if os.path.isfile(cfg.arm_config['DBFILE']):
        query = Job.query
        if status == "success":
            query = query.filter(Job.status == "success")
        elif status == "fail":
            query = query.filter(Job.status == "fail")
        elif status == "active":
            query = query.filter(~Job.finished)
        if date_from is not None:
            query = query.filter(Job.start_time >= date_from)
        if date_to is not None:
            query = query.filter(Job.start_time < date_to + timedelta(days=1))
        jobs = query.order_by(db.desc(Job.job_id)).paginate(
            page=page, max_per_page=int(armui_cfg.database_limit), error_out=False)
    else:
        app.logger.error('ERROR: /history database file doesnt exist')
        jobs = {}
    app.logger.debug(f"Date format - {cfg.arm_config['DATE_FORMAT']}")

    session["page_title"] = "History"

    return render_template('history.html', jobs=jobs.items,
                           date_format=cfg.arm_config['DATE_FORMAT'], pages=jobs,
                           status=status, date_from=from_str, date_to=to_str,
                           page_args=build_page_args(status, from_str, to_str))
```

- [ ] **Step 3: Verify existing tests still pass and lint is clean**

Run:
```
python3 -m pytest test/unittest/ -v
```
Expected: no NEW failures (the 6 known pre-existing failures in `test_ripper_ARMInfo.py` / `test_ripper_processhandler.py` documented in CLAUDE.md may still fail; nothing else regresses).

Run:
```
flake8 arm/ui/history/history.py --max-complexity=15 --max-line-length=120 --show-source --statistics
```
Expected: no output.

- [ ] **Step 4: Manually verify URL filtering in the dev container**

Bring the UI up (`docker compose -f docker-compose.dev.yml up -d`) and confirm each URL returns HTTP 200 and a filtered list (empty is fine if no matching jobs):
```
curl -s -o /dev/null -w "%{http_code}\n" "http://localhost:8090/history?status=fail"
curl -s -o /dev/null -w "%{http_code}\n" "http://localhost:8090/history?status=success"
curl -s -o /dev/null -w "%{http_code}\n" "http://localhost:8090/history?status=active"
curl -s -o /dev/null -w "%{http_code}\n" "http://localhost:8090/history?from=2026-01-01&to=2026-12-31"
curl -s -o /dev/null -w "%{http_code}\n" "http://localhost:8090/history?status=garbage&from=nonsense"
```
Expected: `200` for every line (the garbage line must NOT 500 — it falls back to `all` / no date bound). Note: these paths require login unless `DISABLE_LOGIN` is set; if login is enabled, verify in a browser session instead and confirm no 500 in the container logs.

- [ ] **Step 5: Commit**

```
git add arm/ui/history/history.py
git commit -m "history: filter jobs by outcome and start-date range via query params"
```

---

### Task 3: Make `pagination.html` forward optional filter params

Extend the shared pagination partial so it spreads an optional `page_args` dict into every `url_for` call. Backward-compatible: pages that don't pass `page_args` are unaffected (defaults to `{}`).

**Files:**
- Modify: `arm/ui/templates/pagination.html`

**Interfaces:**
- Consumes: an optional `page_args` variable in the include context (dict). When absent, defaults to `{}`.
- Produces: pagination links of the form `url_for(page_name, page=N, **page_args)`.

- [ ] **Step 1: Add the default and spread page_args into every link**

Replace the entire contents of `arm/ui/templates/pagination.html` with:

```html
<!-- Pagination Links-->
{% set page_args = page_args | default({}) %}
<div class="row">
    <div class="col">
        <p class="text-left mt-3 d-block">Showing page {{ pages.page }} of {{ pages.pages }}</p>
    </div>
    <div class="col text-right">
        <a href="{{ url_for(page_name, page=pages.prev_num, **page_args) }}"
           class="btn btn-primary {% if pages.page == 1 %}disabled{% endif %}">&laquo;</a>
        <!-- Loop through the number of pages to display a link for each-->
        {% for page_num in pages.iter_pages(left_edge=1, right_edge=1, left_current=1, right_current=2) %}
            {% if page_num %}
                <!-- Check for the active page and set the link to "Active"-->
                {% if pages.page == page_num %}
                    <a href="{{ url_for(page_name, page=page_num, **page_args) }}"
                       class="btn btn-secondary active">{{ page_num }}</a>
                {% else %}
                    <a href="{{ url_for(page_name, page=page_num, **page_args) }}"
                       class="btn btn-primary">{{ page_num }}</a>
                {% endif %}
            {% else %}
                ...
            {% endif %}
        {% endfor %}
        <a href="{{ url_for(page_name, page=pages.next_num, **page_args) }}"
           class="btn btn-primary {% if pages.page == pages.pages %}disabled{% endif %}">&raquo;</a>
    </div>
</div>
```

- [ ] **Step 2: Verify other pages that use the partial still render**

The partial is also included by other paginated pages. Confirm at least one non-history paginated page still returns 200 (e.g. the logs list, if paginated) and the history page (from Task 2) still returns 200:
```
curl -s -o /dev/null -w "%{http_code}\n" "http://localhost:8090/history"
```
Expected: `200`, no 500 in container logs. (Jinja's `**page_args` with the `{}` default is a no-op for callers that don't set it.)

- [ ] **Step 3: Commit**

```
git add arm/ui/templates/pagination.html
git commit -m "pagination: forward optional page_args through page links"
```

---

### Task 4: Add the filter bar to `history.html`

Add the visible filter UI (status dropdown + From/To date inputs + Apply/Clear) and thread `page_args` through both pagination includes so paging keeps the active filter.

**Files:**
- Modify: `arm/ui/history/templates/history.html`

**Interfaces:**
- Consumes: `status`, `date_from`, `date_to` (strings), `page_args` (dict) from the route (Task 2); the extended `pagination.html` (Task 3).
- Produces: rendered filter bar; both pagination includes now pass `page_args`.

- [ ] **Step 1: Insert the filter bar above the top pagination include**

In `arm/ui/history/templates/history.html`, find the top pagination block (currently lines 52-55):

```html
                    <br>
                    {% with pages=pages, page_name="route_history.history" %}
                        {% include "pagination.html" %}
                    {% endwith %}
```

Replace it with the filter form plus the pagination include (note `page_args=page_args` added to the `with`):

```html
                    <br>
                    <form method="get" action="{{ url_for('route_history.history') }}"
                          class="form-inline justify-content-center mb-3">
                        <label class="mr-2" for="status">Show</label>
                        <select name="status" id="status" class="form-control mr-3">
                            <option value="all"{% if status == 'all' %} selected{% endif %}>All</option>
                            <option value="success"{% if status == 'success' %} selected{% endif %}>Successful</option>
                            <option value="fail"{% if status == 'fail' %} selected{% endif %}>Failed</option>
                            <option value="active"{% if status == 'active' %} selected{% endif %}>In-progress</option>
                        </select>
                        <label class="mr-2" for="from">From</label>
                        <input type="date" name="from" id="from" class="form-control mr-3"
                               value="{{ date_from }}">
                        <label class="mr-2" for="to">To</label>
                        <input type="date" name="to" id="to" class="form-control mr-3"
                               value="{{ date_to }}">
                        <button type="submit" class="btn btn-primary mr-2">Apply</button>
                        <a href="{{ url_for('route_history.history') }}" class="btn btn-secondary">Clear</a>
                    </form>
                    {% with pages=pages, page_name="route_history.history", page_args=page_args %}
                        {% include "pagination.html" %}
                    {% endwith %}
```

- [ ] **Step 2: Add `page_args` to the bottom pagination include**

Find the bottom pagination block (currently lines 88-90):

```html
                    {% with pages=pages, page_name="route_history.history" %}
                        {% include "pagination.html" %}
                    {% endwith %}
```

Replace with:

```html
                    {% with pages=pages, page_name="route_history.history", page_args=page_args %}
                        {% include "pagination.html" %}
                    {% endwith %}
```

- [ ] **Step 3: Manually verify the filter bar end-to-end in a browser**

In the dev-container UI (`http://localhost:8090/history`, logging in if required):
1. The filter bar renders above the table with All/Successful/Failed/In-progress and two date pickers.
2. Select "Failed", click Apply → URL becomes `/history?status=fail`, only failed jobs show, and the dropdown stays on "Failed".
3. Set a From date, Apply → only jobs on/after that date show; the date input keeps its value.
4. If there is more than one page under a filter, click page 2 / » → the URL keeps `status=`/`from=`/`to=` (filter persists across paging).
5. Click Clear → returns to `/history` with all jobs and reset controls.

Expected: all five behave as described; no 500s in container logs.

- [ ] **Step 4: Commit**

```
git add arm/ui/history/templates/history.html
git commit -m "history: add outcome + date-range filter bar to the UI"
```

---

## Self-Review Notes

- **Spec coverage:** outcome filter (Task 2 query + Task 4 UI), date-range filter (Task 2 query + Task 4 UI), filters combine via AND (Task 2, sequential `.filter()`), filters survive pagination (Task 3 + Task 4 `page_args`), no DB/migration (only route/template/new-helper files), defensive param handling (Task 1 `normalize_status`/`parse_date` + tested). All spec sections map to a task.
- **Placeholder scan:** every code step contains complete code; no TBD/TODO.
- **Type consistency:** `normalize_status`/`parse_date`/`build_page_args` signatures defined in Task 1 are used with matching arguments in Task 2; `page_args` (dict) produced by Task 2 is consumed by Task 3 (`**page_args`) and Task 4 (`page_args=page_args`); `status`/`date_from`/`date_to` strings produced by Task 2 are consumed by Task 4's template.
- **Note on route testing:** the established test pattern (`test_ui_ripper_fields.py`, `test_ui_security.py`) unit-tests pure helpers, not full Flask routes (which need app + DB context). Task 1 covers the risky parsing logic with unit tests; the thin route wiring and template are verified by the manual/`curl` steps in Tasks 2–4.
