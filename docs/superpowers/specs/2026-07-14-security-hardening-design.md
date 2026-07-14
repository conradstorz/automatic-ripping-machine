# Security Hardening: SECRET_KEY, debug PIN, and `/dbupdate` auth

**Goal:** Remove three concrete, low-risk security weaknesses in the ARM web UI that are reachable on the network: a hardcoded Flask `SECRET_KEY`, a hardcoded Werkzeug debugger PIN, and an unauthenticated database-update endpoint.

**Scope:** These three items only. Explicitly **out of scope** (deferred to separate tracks): CORS tightening, the disc-label shell-injection audit, and the maintainability refactors (config-rewrite-on-import, legacy `Query.get()`, `utils.py` split).

**Constraints:**
- Additive/minimal changes that follow existing patterns; no behavior change to the default configuration beyond replacing insecure constants.
- Must not prevent the UI from booting if the config directory is unwritable.
- Python 3.9–3.12; lint clean under CI flags (`flake8 --max-complexity=15 --max-line-length=120`).
- Runs on the remote `hpz440` Docker daemon; the UI serves at `http://hpz440:8090`. State (including the new key file) lives in the `arm-config` named volume.

---

## Background

`arm/ui/__init__.py` currently hardcodes:

```python
app.config['SECRET_KEY'] = "Big secret key"          # line 54 (TODO: make this random!)
os.environ["WERKZEUG_DEBUG_PIN"] = "12345"           # line 59 (make this random!)
app.logger.debug("Debugging pin: " + os.environ["WERKZEUG_DEBUG_PIN"])  # line 60
```

A constant `SECRET_KEY` lets anyone who has seen the source forge session cookies and CSRF tokens. A constant debugger PIN trivially unlocks the Werkzeug interactive debugger (arbitrary code execution) if the debugger is ever active. Line 60 also logs the PIN.

`arm/ui/database/database.py` — the `/dbupdate` POST route (`update_database`, line 63) has **no** `@login_required`, unlike its sibling routes `view_database` (line 31) and `import_movies` (line 92). It can trigger a DB migration or a database reset (`form.dbfix.data == "new"`). It is CSRF-protected but not authenticated.

`DISABLE_LOGIN` defaults to `false` (`setup/arm.yaml:42`), so login is normally enabled. Flask-Login's `LOGIN_DISABLED` (set from `DISABLE_LOGIN` in `__init__.py:56`) makes `@login_required` a no-op when login is disabled, preserving today's behavior for users who run with login off.

## Architecture

One new dependency-light module plus wiring, so the security logic is testable in isolation without constructing the Flask app.

### Component 1 — `arm/ui/security.py` (new)

Imports only `os`, `secrets`, `logging`. No import of `arm.ui`, `arm.config`, or heavy deps, so unit tests can import it directly.

```
load_or_create_secret_key(config_dir: str) -> str
    key_path = os.path.join(config_dir, "secret_key")
    - If key_path exists and its stripped contents are non-empty: return them.
    - Else: key = secrets.token_hex(32); attempt to write it to key_path with
      mode 0o600; return key.
    - On any OSError (dir missing/unwritable, read error): log a warning and
      return a fresh in-memory secrets.token_hex(32) so the app still boots.
      (Degraded mode: sessions do not persist across restarts, but the UI works.)

generate_debug_pin() -> str
    Return secrets.token_hex(8) (a fresh random PIN each start; not persisted).
```

Design notes:
- The key is 64 hex chars (32 bytes) — well above Flask's needs.
- Writing with `0o600` restricts the file to the owner (the `arm` user, uid 1000). Best effort: if the umask/filesystem ignores the mode, the warning path is not triggered (the key is still secret-by-location in the config volume).
- An **empty or whitespace-only** existing file is treated as absent and regenerated (guards against a truncated write).

### Component 2 — wiring in `arm/ui/__init__.py`

- `from arm.ui.security import load_or_create_secret_key, generate_debug_pin`
- Replace line 54 with:
  `app.config['SECRET_KEY'] = load_or_create_secret_key(os.path.dirname(cfg.arm_config_path))`
  (`cfg.arm_config_path` is the module-level path in `arm/config/config.py`, default `/etc/arm/config/arm.yaml`.)
- Replace line 59 with:
  `os.environ["WERKZEUG_DEBUG_PIN"] = generate_debug_pin()`
- **Delete line 60** (do not log the PIN). Optionally keep a non-sensitive debug line such as `app.logger.debug("Werkzeug debug PIN randomized")`.

### Component 3 — `/dbupdate` auth in `arm/ui/database/database.py`

Add `@login_required` between the route decorator and `def update_database` (line 63):

```python
@route_database.route('/dbupdate', methods=['POST'])
@login_required
def update_database():
    ...
```

`login_required` is already imported (line 12). No other change.

## Data flow

UI startup (`arm/ui/__init__.py` import):
1. `arm.config.config` loads and exposes `arm_config_path`.
2. `config_dir = os.path.dirname(cfg.arm_config_path)` → e.g. `/etc/arm/config`.
3. `load_or_create_secret_key(config_dir)` reads or creates `/etc/arm/config/secret_key` and returns the key → `app.config['SECRET_KEY']`.
4. `generate_debug_pin()` sets a random `WERKZEUG_DEBUG_PIN`.

Request time: `POST /dbupdate` now requires an authenticated session unless `LOGIN_DISABLED` is set.

## Error handling

| Condition | Behavior |
|-----------|----------|
| `secret_key` file absent | Generate, persist (`0o600`), use it. |
| `secret_key` file present, non-empty | Reuse it (sessions survive restart). |
| `secret_key` file empty/whitespace | Treat as absent → regenerate. |
| config dir unwritable / read error | Log warning, use ephemeral in-memory key; app boots. |
| `down -v` wipes the config volume | Fresh key generated next boot (expected; existing sessions invalidated). |

## Testing

New `test/unittest/test_ui_security.py` (imports only `arm.ui.security`, so it needs no app/config/database and runs fast under the CI gate):

1. **generate-when-absent** — given an empty temp dir, `load_or_create_secret_key` returns a non-empty key AND creates `secret_key` containing it.
2. **reuse-existing (idempotent)** — a second call on the same dir returns the identical key; the file is not rewritten with a different value.
3. **unwritable-dir fallback** — given a non-existent/unwritable path, it returns a non-empty key and does not raise.
4. **debug pin** — `generate_debug_pin()` returns a non-empty string that is not `"12345"`.

These are pure-function tests (no Flask app), consistent with the existing `test/unittest/` style, and are enforced by the CI `Run unit tests` step across Python 3.9–3.12.

Manual verification (in the dev container): rebuild, boot, confirm `/etc/arm/config/secret_key` is created (0o600) and stable across `restart`; confirm the UI still serves at `http://hpz440:8090`; with login enabled, confirm `POST /dbupdate` redirects to login when unauthenticated.

## Success criteria

- No hardcoded `SECRET_KEY` or debugger PIN remain in the source; the PIN is no longer logged.
- `SECRET_KEY` persists across UI restarts via `/etc/arm/config/secret_key`.
- `/dbupdate` requires authentication when login is enabled; unchanged when `DISABLE_LOGIN: true`.
- New unit tests pass across 3.9–3.12; flake8 clean; UI boots and serves.
