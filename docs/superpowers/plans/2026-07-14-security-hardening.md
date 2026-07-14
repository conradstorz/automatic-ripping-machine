# Security Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove three network-reachable security weaknesses in the ARM web UI: a hardcoded Flask `SECRET_KEY`, a hardcoded Werkzeug debugger PIN, and an unauthenticated `/dbupdate` endpoint.

**Architecture:** Add one dependency-light module `arm/ui/security.py` (only `os`/`secrets`/`logging`) holding a persist-or-create secret-key helper and a random debug-PIN helper, unit-tested in isolation. Wire both into `arm/ui/__init__.py`, replacing the hardcoded constants and removing the PIN log line. Add `@login_required` to the `/dbupdate` route. Tests run under the existing CI `Run unit tests` gate.

**Tech Stack:** Python 3.9–3.12, Flask, Flask-Login, `secrets` stdlib, pytest/unittest, flake8.

## Global Constraints

- **Python versions supported:** 3.9–3.12.
- **Lint is CI-binding:** `flake8 . --max-complexity=15 --max-line-length=120 --show-source --statistics` must pass (exit 0).
- **Do not chain separate shell calls with `&&`** (global rule); `&&` inside a container command string is fine.
- **Container commands on this Windows host:** prefix any command passing a container-absolute path (e.g. `/opt/arm/...`) with `MSYS_NO_PATHCONV=1`; the dev container has `python3` (no `python`); run pytest/flake8 with `-w /opt/arm`.
- **Docker daemon is remote (hpz440):** source is baked into the image (no bind mount), so rebuild to pick up code changes: `docker compose -f docker-compose.dev.yml up -d --build`. Dev deps (pytest/flake8) must be reinstalled after a rebuild: `docker compose -f docker-compose.dev.yml exec arm-dev pip install --no-cache-dir -r /opt/arm/requirements-dev.txt`. To iterate on tests without a full rebuild, `docker cp <file> arm-dev:/opt/arm/<path>` then run pytest.
- **Branch:** all work lands on `feature/security-hardening` (already created).
- **No behavior change to the default config** beyond replacing insecure constants.

---

### Task 1: `arm/ui/security.py` module + unit tests

**Files:**
- Create: `arm/ui/security.py`
- Create: `test/unittest/test_ui_security.py`

**Interfaces:**
- Produces:
  - `load_or_create_secret_key(config_dir: str) -> str` — returns a hex secret key; reads/creates `<config_dir>/secret_key`.
  - `generate_debug_pin() -> str` — returns a fresh random hex PIN.
- Consumes: nothing (stdlib only).

- [ ] **Step 1: Write the failing tests**

Create `test/unittest/test_ui_security.py`:

```python
import os
import sys
import stat
import unittest
import tempfile

sys.path.insert(0, '/opt/arm')
from arm.ui.security import load_or_create_secret_key, generate_debug_pin   # noqa: E402


class TestUiSecurity(unittest.TestCase):

    def test_generates_key_when_absent(self):
        """A missing key file is created and its contents are returned."""
        with tempfile.TemporaryDirectory() as d:
            key = load_or_create_secret_key(d)
            self.assertTrue(key)
            key_path = os.path.join(d, "secret_key")
            self.assertTrue(os.path.isfile(key_path))
            with open(key_path) as f:
                self.assertEqual(f.read().strip(), key)

    def test_reuses_existing_key(self):
        """A second call returns the identical persisted key."""
        with tempfile.TemporaryDirectory() as d:
            first = load_or_create_secret_key(d)
            second = load_or_create_secret_key(d)
            self.assertEqual(first, second)

    def test_empty_file_is_regenerated(self):
        """An empty/whitespace key file is treated as absent and regenerated."""
        with tempfile.TemporaryDirectory() as d:
            key_path = os.path.join(d, "secret_key")
            with open(key_path, "w") as f:
                f.write("   \n")
            key = load_or_create_secret_key(d)
            self.assertTrue(key)
            with open(key_path) as f:
                self.assertEqual(f.read().strip(), key)

    def test_unwritable_dir_falls_back(self):
        """A non-existent/unwritable dir yields a key without raising."""
        key = load_or_create_secret_key("/nonexistent/definitely/not/here")
        self.assertTrue(key)

    def test_debug_pin_is_random_nonempty(self):
        """generate_debug_pin returns a non-empty string that isn't the old constant."""
        pin = generate_debug_pin()
        self.assertTrue(pin)
        self.assertNotEqual(pin, "12345")


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:
```bash
MSYS_NO_PATHCONV=1 docker cp test/unittest/test_ui_security.py arm-dev:/opt/arm/test/unittest/test_ui_security.py
MSYS_NO_PATHCONV=1 docker compose -f docker-compose.dev.yml exec -w /opt/arm arm-dev python3 -m pytest test/unittest/test_ui_security.py -v
```
Expected: collection error / FAIL — `ModuleNotFoundError: No module named 'arm.ui.security'`.

- [ ] **Step 3: Write the module**

Create `arm/ui/security.py`:

```python
"""Security helpers for the ARM web UI.

Dependency-light on purpose (stdlib only) so it can be unit-tested without
constructing the Flask app.
"""
import os
import logging
import secrets

SECRET_KEY_FILENAME = "secret_key"


def load_or_create_secret_key(config_dir: str) -> str:
    """Return a stable Flask secret key, persisted in ``config_dir``.

    Reads ``<config_dir>/secret_key`` if it exists and is non-empty; otherwise
    generates a new key, writes it with owner-only permissions, and returns it.
    If the directory cannot be read or written, logs a warning and returns a
    fresh in-memory key so the app still boots (sessions will not survive a
    restart in that degraded case).
    """
    key_path = os.path.join(config_dir, SECRET_KEY_FILENAME)
    try:
        if os.path.isfile(key_path):
            with open(key_path, "r", encoding="utf-8") as key_file:
                existing = key_file.read().strip()
            if existing:
                return existing
        key = secrets.token_hex(32)
        with open(key_path, "w", encoding="utf-8") as key_file:
            key_file.write(key)
        os.chmod(key_path, 0o600)
        return key
    except OSError as error:
        logging.warning(
            "Could not read or persist secret key in %s (%s); "
            "using a temporary key for this run.", config_dir, error)
        return secrets.token_hex(32)


def generate_debug_pin() -> str:
    """Return a fresh random Werkzeug debugger PIN (not persisted)."""
    return secrets.token_hex(8)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run:
```bash
MSYS_NO_PATHCONV=1 docker cp arm/ui/security.py arm-dev:/opt/arm/arm/ui/security.py
MSYS_NO_PATHCONV=1 docker compose -f docker-compose.dev.yml exec -w /opt/arm arm-dev python3 -m pytest test/unittest/test_ui_security.py -v
```
Expected: `5 passed`.

- [ ] **Step 5: Lint the new files**

Run:
```bash
MSYS_NO_PATHCONV=1 docker compose -f docker-compose.dev.yml exec -w /opt/arm arm-dev flake8 arm/ui/security.py test/unittest/test_ui_security.py --max-complexity=15 --max-line-length=120 --show-source --statistics
```
Expected: exit 0, no output.

- [ ] **Step 6: Commit**

```bash
git add arm/ui/security.py test/unittest/test_ui_security.py
git commit -m "Add ui.security: persisted secret key and random debug PIN helpers"
```

---

### Task 2: Wire the helpers into `arm/ui/__init__.py`

**Files:**
- Modify: `arm/ui/__init__.py` (lines 54, 59, 60 region)

**Interfaces:**
- Consumes: `arm.ui.security.load_or_create_secret_key`, `arm.ui.security.generate_debug_pin`; `arm.config.config.arm_config_path`.
- Produces: nothing new for later tasks.

- [ ] **Step 1: Add the import**

In `arm/ui/__init__.py`, alongside the existing `import arm.config.config as cfg` (line 16), add:

```python
from arm.ui.security import load_or_create_secret_key, generate_debug_pin
```

Place it after `import arm.config.config as cfg` so `cfg` is available. Because `arm/ui/security.py` imports only stdlib, this does not create an import cycle.

- [ ] **Step 2: Replace the hardcoded SECRET_KEY**

Replace this line (currently line 54):

```python
app.config['SECRET_KEY'] = "Big secret key"  # TODO: make this random!
```

with:

```python
# Persisted secret key (see arm/ui/security.py); survives UI restarts.
app.config['SECRET_KEY'] = load_or_create_secret_key(os.path.dirname(cfg.arm_config_path))
```

- [ ] **Step 3: Replace the hardcoded debug PIN and remove the PIN log line**

Replace these two lines (currently lines 59–60):

```python
os.environ["WERKZEUG_DEBUG_PIN"] = "12345"  # make this random!
app.logger.debug("Debugging pin: " + os.environ["WERKZEUG_DEBUG_PIN"])
```

with:

```python
# Randomize the Werkzeug debugger PIN each start; never log its value.
os.environ["WERKZEUG_DEBUG_PIN"] = generate_debug_pin()
app.logger.debug("Werkzeug debug PIN randomized")
```

- [ ] **Step 4: Rebuild the container and verify a clean boot**

Run:
```bash
docker compose -f docker-compose.dev.yml up -d --build
```
Then wait for startup and check the boot logs and health:
```bash
MSYS_NO_PATHCONV=1 docker compose -f docker-compose.dev.yml logs --no-log-prefix arm-dev
docker inspect --format '{{.State.Health.Status}}' arm-dev
```
Expected: `Starting ARM-UI on interface address` / `Serving on ...` present; health becomes `healthy`; no traceback. The old `Debugging pin: 12345` line must NOT appear.

- [ ] **Step 5: Verify the key file was created with owner-only perms**

Run:
```bash
MSYS_NO_PATHCONV=1 docker compose -f docker-compose.dev.yml exec arm-dev ls -l /etc/arm/config/secret_key
```
Expected: the file exists and its mode is `-rw-------` (0o600), owned by the arm user.

- [ ] **Step 6: Verify the key persists across a restart**

Run:
```bash
MSYS_NO_PATHCONV=1 docker compose -f docker-compose.dev.yml exec arm-dev sh -c "cat /etc/arm/config/secret_key" > before.txt
docker compose -f docker-compose.dev.yml restart arm-dev
```
Wait for health, then:
```bash
MSYS_NO_PATHCONV=1 docker compose -f docker-compose.dev.yml exec arm-dev sh -c "cat /etc/arm/config/secret_key" > after.txt
diff before.txt after.txt
```
Expected: `diff` prints nothing (identical key across restart). Then remove the temp files:
```bash
rm before.txt after.txt
```

- [ ] **Step 7: Verify the UI still serves**

Run:
```bash
curl -sS -o /dev/null -w "%{http_code}\n" --max-time 10 http://hpz440:8090
```
Expected: `200` (or a `301`/`302` redirect). Any of these confirms the UI serves with the new key.

- [ ] **Step 8: Commit**

```bash
git add arm/ui/__init__.py
git commit -m "Use persisted random SECRET_KEY and random debug PIN; stop logging the PIN"
```

---

### Task 3: Require authentication on `/dbupdate`

**Files:**
- Modify: `arm/ui/database/database.py:63-64`

**Interfaces:**
- Consumes: `flask_login.login_required` (already imported at line 12).
- Produces: nothing new.

- [ ] **Step 1: Add the decorator**

In `arm/ui/database/database.py`, change:

```python
@route_database.route('/dbupdate', methods=['POST'])
def update_database():
```

to:

```python
@route_database.route('/dbupdate', methods=['POST'])
@login_required
def update_database():
```

- [ ] **Step 2: Confirm `login_required` is imported (no new import needed)**

Verify line 12 still reads:
```python
from flask_login import LoginManager, login_required  # noqa: F401
```
(If the `# noqa: F401` is no longer needed because `login_required` is now used, leave it — it is harmless and other symbols on the line may still need it.)

- [ ] **Step 3: Rebuild and lint**

Run:
```bash
docker compose -f docker-compose.dev.yml up -d --build
MSYS_NO_PATHCONV=1 docker compose -f docker-compose.dev.yml exec arm-dev pip install --no-cache-dir -r /opt/arm/requirements-dev.txt
MSYS_NO_PATHCONV=1 docker compose -f docker-compose.dev.yml exec -w /opt/arm arm-dev flake8 arm/ui/database/database.py --max-complexity=15 --max-line-length=120 --show-source --statistics
```
Expected: flake8 exit 0.

- [ ] **Step 4: Verify the endpoint requires auth when login is enabled**

The dev config defaults to `DISABLE_LOGIN: false`, so `/dbupdate` should now redirect unauthenticated POSTs to the login page instead of acting. Run:
```bash
curl -sS -o /dev/null -w "%{http_code} %{redirect_url}\n" -X POST --max-time 10 http://hpz440:8090/dbupdate
```
Expected: a `302`/`401` (redirect to login), NOT a `200`/redirect to `/index`. (A CSRF rejection is also acceptable evidence the request did not perform a DB action.)

Note: if the running dev instance has `DISABLE_LOGIN: true`, this check instead confirms unchanged behavior (login bypassed). Confirm the effective value with:
```bash
MSYS_NO_PATHCONV=1 docker compose -f docker-compose.dev.yml exec arm-dev grep -i "^DISABLE_LOGIN" /etc/arm/config/arm.yaml
```

- [ ] **Step 5: Commit**

```bash
git add arm/ui/database/database.py
git commit -m "Require login for POST /dbupdate (matches sibling database routes)"
```

---

### Task 4: Full verification (all versions + full suite)

**Files:** none (verification only).

- [ ] **Step 1: Run the full unit-test suite in the container**

Run:
```bash
MSYS_NO_PATHCONV=1 docker compose -f docker-compose.dev.yml exec -w /opt/arm arm-dev python3 -m pytest test/unittest/ -v
```
Expected: all tests pass (the previous 29 plus the 5 new `test_ui_security.py` tests = 34 passed).

- [ ] **Step 2: Run flake8 on the changed files under CI flags**

Run:
```bash
MSYS_NO_PATHCONV=1 docker compose -f docker-compose.dev.yml exec -w /opt/arm arm-dev flake8 arm/ui/security.py arm/ui/__init__.py arm/ui/database/database.py test/unittest/test_ui_security.py --max-complexity=15 --max-line-length=120 --show-source --statistics
```
Expected: exit 0.

- [ ] **Step 2 note:** Do not run bare `flake8 .` locally — the untracked `Autorippr/` dir is baked into the dev image and will report pre-existing findings unrelated to this work (CI checks out only tracked files, so it is unaffected).

- [ ] **Step 3: No commit** (verification only). Proceed to finishing the branch (PR to the fork, per the project's fork workflow).

---

## Self-Review

**Spec coverage:**
- New `arm/ui/security.py` with `load_or_create_secret_key` (persist, `0o600`, empty-file regen, unwritable fallback) + `generate_debug_pin` → Task 1. ✓
- `__init__.py` wiring: SECRET_KEY from config dir, random PIN, remove PIN log line → Task 2. ✓
- `/dbupdate` `@login_required` → Task 3. ✓
- New tests (generate-when-absent, reuse, unwritable fallback, debug pin) → Task 1 (also covers empty-file regen, an extra case beyond the spec). ✓
- CI enforcement across 3.9–3.12 → covered by the existing gate; full suite run in Task 4. ✓
- Success criteria (no hardcoded key/PIN, PIN not logged, key persists, /dbupdate auth, tests pass, flake8 clean, UI boots) → Tasks 2, 3, 4. ✓

**Placeholder scan:** No TBD/TODO/"handle edge cases" — all code shown in full. The only literal "TODO" text appears inside a quoted before-image of the existing line being replaced.

**Type/name consistency:** `load_or_create_secret_key(config_dir: str) -> str` and `generate_debug_pin() -> str` are used identically in Tasks 1 and 2. `SECRET_KEY_FILENAME = "secret_key"` matches the `/etc/arm/config/secret_key` path referenced in verification steps. `cfg.arm_config_path` matches `arm/config/config.py:10`.
