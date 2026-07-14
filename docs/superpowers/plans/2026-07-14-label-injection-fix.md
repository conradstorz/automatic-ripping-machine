# Disc-Label Injection Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the confirmed command injection in `rip_data` (a crafted disc label reaching a `shell=True` `dd` command) and sanitize `job.label` at its source so a malicious label can never break out of a shell or escape its directory.

**Architecture:** Add a stdlib-only `arm/ripper/sanitize.py` with a minimal, look-preserving `sanitize_label`. Rewrite `rip_data`'s `dd` call to list-form (no shell) via a pure `build_dd_command` helper in `utils.py`, and re-sanitize the label before building paths. Sanitize `self.label` at its untrusted sources in `arm/models/job.py`.

**Tech Stack:** Python 3.9–3.12, stdlib `re`/`shlex`/`subprocess`, pytest/unittest, flake8.

## Global Constraints

- **Python versions supported:** 3.9–3.12. (`list[str]` annotations are fine on 3.9 via PEP 585; do NOT use `X | None` syntax.)
- **Lint is CI-binding:** `flake8 . --max-complexity=15 --max-line-length=120 --show-source --statistics` must pass (exit 0).
- **`arm/ripper/sanitize.py` must be stdlib-only** (import only `re`) so `arm/models/job.py` and `arm/ripper/utils.py` can import it without an import cycle.
- **No behavior change for normal labels:** a label with no path separators/control characters/`..` must pass through `sanitize_label` unchanged.
- **Container commands (Windows/Git Bash, remote hpz440 daemon):** the `arm-dev` container is running; source is baked in. Run tests by `docker cp`-ing changed files into the container then invoking pytest — no rebuild needed for test-only runs. Prefix any command with a container-absolute path (`/opt/arm/...`) with `MSYS_NO_PATHCONV=1`. Container has `python3` (no `python`); run pytest/flake8 with `-w /opt/arm`. pytest/flake8 are already installed. Do NOT chain distinct shell commands with `&&`.
- **Branch:** all work lands on `feature/label-injection-fix` (already created).

---

### Task 1: `arm/ripper/sanitize.py` (`sanitize_label`) + tests

**Files:**
- Create: `arm/ripper/sanitize.py`
- Create: `test/unittest/test_ripper_sanitize.py`

**Interfaces:**
- Produces: `sanitize_label(raw) -> str` — filesystem-safe, look-preserving label.
- Consumes: nothing (stdlib `re` only).

- [ ] **Step 1: Write the failing tests**

Create `test/unittest/test_ripper_sanitize.py`:

```python
import sys
import unittest

sys.path.insert(0, '/opt/arm')
from arm.ripper.sanitize import sanitize_label   # noqa: E402


class TestSanitizeLabel(unittest.TestCase):

    def test_benign_labels_unchanged(self):
        for label in ("Tom & Jerry", "The Matrix (1999)", "Depeche Mode - Violator", "data-disc"):
            self.assertEqual(sanitize_label(label), label)

    def test_path_separators_removed(self):
        self.assertNotIn("/", sanitize_label("a/b/c"))
        self.assertNotIn("\\", sanitize_label("a\\b\\c"))

    def test_traversal_neutralized(self):
        result = sanitize_label("../../etc/passwd")
        self.assertNotIn("/", result)
        self.assertFalse(result.startswith("."))
        self.assertEqual(result, "etcpasswd")

    def test_dotdot_becomes_empty(self):
        self.assertEqual(sanitize_label(".."), "")

    def test_control_chars_removed(self):
        self.assertEqual(sanitize_label("a\x00b\x1fc"), "abc")

    def test_shell_metachars_kept_but_harmless(self):
        # Not stripped (list-form dd makes them harmless literals), but no separators.
        result = sanitize_label('x"; rm -rf ~; echo "')
        self.assertNotIn("/", result)
        self.assertIn('"', result)

    def test_empty_and_none(self):
        self.assertEqual(sanitize_label(""), "")
        self.assertIsNone(sanitize_label(None))


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:
```bash
MSYS_NO_PATHCONV=1 docker cp test/unittest/test_ripper_sanitize.py arm-dev:/opt/arm/test/unittest/test_ripper_sanitize.py
MSYS_NO_PATHCONV=1 docker compose -f docker-compose.dev.yml exec -w /opt/arm arm-dev python3 -m pytest test/unittest/test_ripper_sanitize.py -v
```
Expected: collection error — `ModuleNotFoundError: No module named 'arm.ripper.sanitize'`.

- [ ] **Step 3: Write the module**

Create `arm/ripper/sanitize.py`:

```python
"""Sanitization helpers for untrusted optical-disc metadata.

Stdlib-only (``re``) so it can be imported from both ``arm.models.job`` and
``arm.ripper.utils`` without an import cycle, and unit-tested in isolation.
"""
import re

_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")
_MULTI_DOT = re.compile(r"\.{2,}")


def sanitize_label(raw):
    """Return a filesystem-safe, still-readable version of a disc label.

    Removes only what is dangerous for use as a single path component:
    control/DEL characters, path separators (``/`` and ``\\``), and runs of
    dots (``..`` traversal). Ordinary characters (letters, digits, spaces,
    ``& : ( ) - _`` ...) are preserved so labels keep their original look.
    Returns the input unchanged if it is falsy (``""``/``None``).
    """
    if not raw:
        return raw
    text = _CONTROL_CHARS.sub("", str(raw))
    text = text.replace("/", "").replace("\\", "")
    text = _MULTI_DOT.sub(".", text)
    return text.strip().strip(".").strip()
```

- [ ] **Step 4: Run the tests to verify they pass**

Run:
```bash
MSYS_NO_PATHCONV=1 docker cp arm/ripper/sanitize.py arm-dev:/opt/arm/arm/ripper/sanitize.py
MSYS_NO_PATHCONV=1 docker compose -f docker-compose.dev.yml exec -w /opt/arm arm-dev python3 -m pytest test/unittest/test_ripper_sanitize.py -v
```
Expected: `7 passed`.

- [ ] **Step 5: Lint**

Run:
```bash
MSYS_NO_PATHCONV=1 docker compose -f docker-compose.dev.yml exec -w /opt/arm arm-dev flake8 arm/ripper/sanitize.py test/unittest/test_ripper_sanitize.py --max-complexity=15 --max-line-length=120 --show-source --statistics
```
Expected: exit 0, no output.

- [ ] **Step 6: Commit**

```bash
git add arm/ripper/sanitize.py test/unittest/test_ripper_sanitize.py
git commit -m "Add sanitize_label for untrusted disc labels"
```

---

### Task 2: List-form `dd` in `rip_data` + `build_dd_command`

**Files:**
- Modify: `arm/ripper/utils.py` (add `import shlex`; add `build_dd_command`; rewrite `rip_data` lines ~487-509)
- Modify: `test/unittest/test_ripper_sanitize.py` (add `build_dd_command` tests)

**Interfaces:**
- Consumes: `arm.ripper.sanitize.sanitize_label` (Task 1).
- Produces: `build_dd_command(devpath, out_path, params) -> list` — list-form (no-shell) `dd` argv.

- [ ] **Step 1: Write the failing test**

Add this class to `test/unittest/test_ripper_sanitize.py` (and add the import at the top, next to the existing sanitize import):

```python
from arm.ripper.utils import build_dd_command   # noqa: E402
```

```python
class TestBuildDdCommand(unittest.TestCase):

    def test_returns_list_with_dd_and_operands(self):
        cmd = build_dd_command("/dev/sr0", "/home/arm/raw/x.part", "bs=1M conv=noerror")
        self.assertIsInstance(cmd, list)
        self.assertEqual(cmd[0], "dd")
        self.assertEqual(cmd[1], "if=/dev/sr0")
        self.assertEqual(cmd[2], "of=/home/arm/raw/x.part")
        self.assertEqual(cmd[3:], ["bs=1M", "conv=noerror"])

    def test_destination_is_single_element_no_shell_splitting(self):
        # A destination containing shell metacharacters must remain ONE argv element.
        dest = '/home/arm/raw/a b"; rm -rf ~.part'
        cmd = build_dd_command("/dev/sr0", dest, "")
        self.assertIn(f"of={dest}", cmd)
        self.assertEqual(len([c for c in cmd if c.startswith("of=")]), 1)

    def test_empty_params(self):
        cmd = build_dd_command("/dev/sr0", "/x.part", "")
        self.assertEqual(cmd, ["dd", "if=/dev/sr0", "of=/x.part"])
```

- [ ] **Step 2: Run the test to verify it fails**

Run:
```bash
MSYS_NO_PATHCONV=1 docker cp test/unittest/test_ripper_sanitize.py arm-dev:/opt/arm/test/unittest/test_ripper_sanitize.py
MSYS_NO_PATHCONV=1 docker compose -f docker-compose.dev.yml exec -w /opt/arm arm-dev python3 -m pytest test/unittest/test_ripper_sanitize.py::TestBuildDdCommand -v
```
Expected: FAIL — `ImportError: cannot import name 'build_dd_command'`.

- [ ] **Step 3: Add `import shlex` to `utils.py`**

In `arm/ripper/utils.py`, the existing line 6 is `import subprocess`. Add directly below it:

```python
import shlex
```

- [ ] **Step 4: Add the `build_dd_command` helper to `utils.py`**

Also add, near the top-level helpers (e.g. just above `def rip_data(job):`), and import `sanitize_label` with the other `arm.ripper` imports:

```python
from arm.ripper.sanitize import sanitize_label
```

```python
def build_dd_command(devpath, out_path, params):
    """Build a list-form (no-shell) ``dd`` argv for ripping a data disc.

    Passing argv as a list means the destination path is a single argument;
    shell metacharacters in it are never interpreted. ``params`` is the
    admin-configured ``DATA_RIP_PARAMETERS`` string, split into separate args.
    """
    return ["dd", f"if={devpath}", f"of={out_path}", *shlex.split(params or "")]
```

- [ ] **Step 5: Rewrite `rip_data` to sanitize the label and run `dd` list-form**

In `arm/ripper/utils.py`, replace the current head of `rip_data` (the default-label block plus the `cmd = f'dd ...'` construction and the `subprocess.check_output(cmd, shell=True)` call). Change the default-label block:

```python
    success = False
    if job.label == "" or job.label is None:
        job.label = "data-disc"
```

to:

```python
    success = False
    if job.label == "" or job.label is None:
        job.label = "data-disc"
    # Sanitize the (attacker-controllable) disc label before it becomes a path.
    job.label = sanitize_label(str(job.label))
    if not job.label:
        job.label = "data-disc"
```

Then replace this block (currently lines ~505-509):

```python
    cmd = f'dd if="{job.devpath}" of="{incomplete_filename}" {cfg.arm_config["DATA_RIP_PARAMETERS"]} 2>> ' \
          f'{os.path.join(job.config.LOGPATH, job.logfile)}'
    logging.debug(f"Sending command: {cmd}")
    try:
        subprocess.check_output(cmd, shell=True).decode("utf-8")
```

with:

```python
    dd_cmd = build_dd_command(job.devpath, incomplete_filename, cfg.arm_config["DATA_RIP_PARAMETERS"])
    log_path = os.path.join(job.config.LOGPATH, job.logfile)
    logging.debug(f"Sending command: {dd_cmd}")
    try:
        with open(log_path, "a", encoding="utf-8") as log_fh:
            subprocess.check_output(dd_cmd, stderr=log_fh).decode("utf-8")
```

Leave the rest of the `try`/`except` body (the `move_files_main`, success flag, and `CalledProcessError` handling) unchanged.

- [ ] **Step 6: Run the new tests + confirm the module imports**

Run:
```bash
MSYS_NO_PATHCONV=1 docker cp arm/ripper/utils.py arm-dev:/opt/arm/arm/ripper/utils.py
MSYS_NO_PATHCONV=1 docker compose -f docker-compose.dev.yml exec -w /opt/arm arm-dev python3 -m pytest test/unittest/test_ripper_sanitize.py -v
```
Expected: `10 passed` (7 sanitize + 3 build_dd_command). The successful collection also proves `arm/ripper/utils.py` still imports cleanly.

- [ ] **Step 7: Lint**

Run:
```bash
MSYS_NO_PATHCONV=1 docker compose -f docker-compose.dev.yml exec -w /opt/arm arm-dev flake8 arm/ripper/utils.py test/unittest/test_ripper_sanitize.py --max-complexity=15 --max-line-length=120 --show-source --statistics
```
Expected: exit 0.

- [ ] **Step 8: Commit**

```bash
git add arm/ripper/utils.py test/unittest/test_ripper_sanitize.py
git commit -m "rip_data: run dd list-form (no shell) and sanitize the label"
```

---

### Task 3: Sanitize `job.label` at its source in `arm/models/job.py`

**Files:**
- Modify: `arm/models/job.py` (imports; `:178`; `:201`)

**Interfaces:**
- Consumes: `arm.ripper.sanitize.sanitize_label` (Task 1).

- [ ] **Step 1: Add the import**

In `arm/models/job.py`, next to the existing `from arm.ripper import music_brainz` (line 13), add:

```python
from arm.ripper.sanitize import sanitize_label
```
(This is safe: `arm.ripper.sanitize` is stdlib-only, so it adds no import cycle even though `job.py` is a model.)

- [ ] **Step 2: Sanitize the lsdvd-derived label**

Change (currently line 178):

```python
            lsdvdlbl = str(subprocess.check_output(command, shell=True).strip(), 'utf-8')
            self.label = lsdvdlbl
```

to:

```python
            lsdvdlbl = str(subprocess.check_output(command, shell=True).strip(), 'utf-8')
            self.label = sanitize_label(lsdvdlbl)
```

- [ ] **Step 3: Sanitize the udev `ID_FS_LABEL`**

Change (currently lines 200-201):

```python
            if key == "ID_FS_LABEL":
                self.label = value
```

to:

```python
            if key == "ID_FS_LABEL":
                self.label = sanitize_label(value)
```

(Leave the following `if value == "iso9660":` check on the raw `value` — `sanitize_label("iso9660")` is `"iso9660"`, so the disctype detection is unaffected either way.)

- [ ] **Step 4: Confirm the model imports and the full suite is green**

Run:
```bash
MSYS_NO_PATHCONV=1 docker cp arm/models/job.py arm-dev:/opt/arm/arm/models/job.py
MSYS_NO_PATHCONV=1 docker compose -f docker-compose.dev.yml exec -w /opt/arm arm-dev python3 -c "import arm.models.job; print('job.py imports OK')"
MSYS_NO_PATHCONV=1 docker compose -f docker-compose.dev.yml exec -w /opt/arm arm-dev python3 -m pytest test/unittest/ -v
```
Expected: `job.py imports OK`; then all tests pass (previous 34 + 7 sanitize + 3 build_dd_command = 44 passed).

- [ ] **Step 5: Lint**

Run:
```bash
MSYS_NO_PATHCONV=1 docker compose -f docker-compose.dev.yml exec -w /opt/arm arm-dev flake8 arm/models/job.py --max-complexity=15 --max-line-length=120 --show-source --statistics
```
Expected: exit 0.

- [ ] **Step 6: Commit**

```bash
git add arm/models/job.py
git commit -m "Sanitize disc label at its udev/lsdvd sources"
```

---

### Task 4: Full verification

**Files:** none (verification only).

- [ ] **Step 1: Full suite in the container**

Run:
```bash
MSYS_NO_PATHCONV=1 docker compose -f docker-compose.dev.yml exec -w /opt/arm arm-dev python3 -m pytest test/unittest/ 2>&1 | tail -3
```
Expected: `44 passed` (34 prior + 7 sanitize + 3 build_dd_command).

- [ ] **Step 2: flake8 on all changed files under CI flags**

Run:
```bash
MSYS_NO_PATHCONV=1 docker compose -f docker-compose.dev.yml exec -w /opt/arm arm-dev flake8 arm/ripper/sanitize.py arm/ripper/utils.py arm/models/job.py test/unittest/test_ripper_sanitize.py --max-complexity=15 --max-line-length=120 --show-source --statistics
```
Expected: exit 0.

- [ ] **Step 3: Confirm no remaining `shell=True` on a label path**

Run:
```bash
MSYS_NO_PATHCONV=1 docker compose -f docker-compose.dev.yml exec -w /opt/arm arm-dev grep -n "shell=True" arm/ripper/utils.py
```
Expected: no line inside `rip_data` (the `dd` call). Any remaining `shell=True` in `utils.py` must interpolate only trusted values — confirm none embed `job.label`.

- [ ] **Step 4: No commit** (verification only). Proceed to finishing the branch (PR to the fork).

Note: do not run bare `flake8 .` locally — the untracked `Autorippr/` dir baked into the dev image reports pre-existing findings; CI checks out only tracked files and is unaffected.

---

## Self-Review

**Spec coverage:**
- `sanitize_label` (stdlib-only, minimal, look-preserving, examples) → Task 1. ✓
- List-form `dd` (no `shell=True`), stderr via file handle, `build_dd_command` pure helper → Task 2. ✓
- Idempotent re-sanitize in `rip_data` before path construction → Task 2 Step 5. ✓
- Sanitize at source (`ID_FS_LABEL` + `lsdvd`) → Task 3. ✓
- `lsdvd` command left `shell=True` (trusted devpath) — unchanged, its output sanitized → Task 3 Step 2 (only the assignment changes). ✓
- Tests: malicious neutralized, benign preserved, `build_dd_command` single-arg destination → Task 1 + Task 2 tests. ✓
- Success criteria (no shell on label path, sanitized at every source + before dd, normal labels unchanged, suite green, flake8 clean) → Tasks 2, 3, 4. ✓

**Placeholder scan:** No TBD/TODO/"handle edge cases"; all code shown in full.

**Type/name consistency:** `sanitize_label(raw) -> str` and `build_dd_command(devpath, out_path, params) -> list` are used identically across Tasks 1–3. Test counts are consistent (7 sanitize + 3 build_dd = 10 in the new file; full suite 34 + 10 = 44). `job.config.LOGPATH`/`job.logfile` and `cfg.arm_config["DATA_RIP_PARAMETERS"]` match the existing `rip_data` code.
