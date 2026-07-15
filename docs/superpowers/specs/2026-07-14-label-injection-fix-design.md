# Fix disc-label shell injection in `rip_data` (+ label sanitization)

**Goal:** Close a confirmed command-injection vulnerability where a crafted optical-disc volume label reaches a `shell=True` `dd` command, and harden the label at its source so an attacker-controlled label can never break out of a shell or escape its intended directory.

**Severity:** A data disc whose filesystem label is e.g. `` x`id>/tmp/out` `` or `x"; touch /tmp/pwned; echo "` causes arbitrary command execution as the ripper process (privileged in the ARM container) the moment the disc is ripped.

## Background — verified data flow

- `arm/models/job.py:200-201` — `parse_udev()` sets `self.label = value` directly from the disc's `ID_FS_LABEL` udev property. Attacker-controlled (the label is written when the disc is authored/formatted). No sanitization.
- `arm/models/job.py:174-178` — for DVDs with no label, `self.label` is set from `lsdvd` "Disc Title" output (also disc-derived, untrusted).
- `arm/ripper/utils.py:490,496,501,505` — `rip_data()` builds `raw_path` / `incomplete_filename` from `str(job.label)` and interpolates them into:
  ```python
  cmd = f'dd if="{job.devpath}" of="{incomplete_filename}" {cfg.arm_config["DATA_RIP_PARAMETERS"]} 2>> {log}'
  subprocess.check_output(cmd, shell=True)
  ```
  Double quotes do not prevent breakout (`"`, `$(...)`, backticks). **CONFIRMED INJECTABLE.**

Audit result (whole ripper): this is the **only** confirmed injectable shell sink. `handbrake.py`/`ffmpeg.py` already use `shlex.quote`; `makemkv.py` uses list-form argv; mount/umount and the `lsdvd` command interpolate only the **trusted** `job.devpath` (udev `/dev/srX`). Path traversal via the label (e.g. `../../x` used in `os.path.join`) is a related, non-shell risk that the source-sanitization layer also closes.

## Scope

- **In scope:** remove the shell from `rip_data`'s `dd` call; add a minimal, look-preserving label sanitizer applied at the label's source and (idempotently) in `rip_data`.
- **Out of scope:** the `lsdvd {devpath} | grep | cut` command at `job.py:176` keeps `shell=True` — its only interpolated value is the trusted `devpath`, so it is not injectable; its *output* is sanitized at the assignment. No change to `handbrake`/`ffmpeg`/`makemkv` (already safe). CORS and maintainability refactors remain separate tracks.

## Global constraints

- Python 3.9–3.12; flake8 `--max-complexity=15 --max-line-length=120` clean.
- New sanitizer module must be stdlib-only (import only `re`) so it is importable from both `arm/models/job.py` and `arm/ripper/utils.py` without an import cycle, and unit-testable in isolation.
- No behavior change for normal disc labels (labels without path separators or control characters must pass through unchanged).

## Architecture

### Component 1 — `arm/ripper/sanitize.py` (new, stdlib-only)

```
sanitize_label(raw: str) -> str
```
Removes only what is dangerous for use as a single path component, preserving readable characters:
1. Return `raw` unchanged if it is falsy (`""`/`None` handled by caller's default).
2. Remove ASCII control characters and DEL: `[\x00-\x1f\x7f]`.
3. Remove path separators: `/` and `\`.
4. Collapse runs of two or more dots to a single dot (`re.sub(r"\.{2,}", ".", s)`) — neutralizes `..` traversal.
5. Strip leading/trailing whitespace and dots.

Kept intact: letters, digits, spaces, and punctuation such as `& : ( ) - _ ! , '`. Shell metacharacters (`` ` ``, `$`, `"`, `;`, `|`, …) are intentionally **not** stripped — with the list-form `dd` (Component 2) they are harmless literal filename characters, and stripping them would butcher legitimate labels.

Examples:
| Input | Output |
|-------|--------|
| `Tom & Jerry` | `Tom & Jerry` |
| `The Matrix (1999)` | `The Matrix (1999)` |
| `../../etc/passwd` | `etcpasswd` |
| `x"; rm -rf ~; echo "` | `x"; rm -rf ~; echo "` (harmless literal once dd is list-form) |
| `..` | `` (empty → caller applies `data-disc`) |
| `a\x00b/c` | `abc` |

### Component 2 — list-form `dd` in `arm/ripper/utils.py`

Add a pure, testable builder:
```
build_dd_command(devpath: str, out_path: str, params: str) -> list[str]
    return ["dd", f"if={devpath}", f"of={out_path}", *shlex.split(params or "")]
```
`rip_data()` changes:
- After the empty-label default, set `job.label = sanitize_label(str(job.label))` (idempotent belt-and-suspenders so paths built below are safe regardless of source), re-applying the `data-disc` default if sanitization empties it.
- Replace the `cmd = f'dd ...'` + `subprocess.check_output(cmd, shell=True)` with:
  ```python
  dd_cmd = build_dd_command(job.devpath, incomplete_filename, cfg.arm_config["DATA_RIP_PARAMETERS"])
  log_path = os.path.join(job.config.LOGPATH, job.logfile)
  with open(log_path, "a", encoding="utf-8") as log_fh:
      subprocess.check_output(dd_cmd, stderr=log_fh).decode("utf-8")
  ```
  No `shell=True`; stderr goes to the logfile via the file handle instead of a shell `2>>` redirect. `dd` uses `if=`/`of=` operands, so no quoting is needed in list form.

### Component 3 — sanitize at the source in `arm/models/job.py`

- `import` `sanitize_label` from `arm.ripper.sanitize` (job.py already imports `from arm.ripper import music_brainz`, so importing another stdlib-only `arm.ripper` module introduces no cycle).
- `parse_udev()` `ID_FS_LABEL` branch: `self.label = sanitize_label(value)` (keep the existing `iso9660` disctype check on the raw value or the sanitized value — `iso9660` is unaffected by sanitization).
- The `lsdvd` branch: `self.label = sanitize_label(lsdvdlbl)`.

## Data flow

Disc insert → `parse_udev` reads `ID_FS_LABEL` → **sanitize_label** → `job.label` (safe single path component) → used everywhere as directory/file names. Data rip → `rip_data` re-sanitizes (idempotent) → `build_dd_command` (list-form argv) → `subprocess.check_output(dd_cmd, stderr=log_fh)` — no shell anywhere on the path.

## Error handling

- `sanitize_label(None)`/empty → returns as-is; `rip_data` already defaults empty labels to `data-disc`, and re-applies the default if sanitization empties a label (e.g. `..`).
- Opening the logfile for stderr uses a context manager; a failure raises as before (rip fails and is recorded) — no behavior regression versus the previous `2>>` which would also fail the command.
- `shlex.split` of `DATA_RIP_PARAMETERS` (admin config, trusted): an unbalanced-quote value raises `ValueError`; acceptable — it is an admin misconfiguration surfaced at rip time. (The previous shell form would have mis-parsed it silently.)

## Testing

New `test/unittest/test_ripper_sanitize.py` (imports `arm.ripper.sanitize` only — no app/db):
- Malicious labels are neutralized: `../../etc/passwd`, `..`, `a/b\c`, a label with `\x00`/control chars, and a shell-breakout label — assert output contains no `/`, no `\`, no leading dot, and (for `..`) is empty.
- Benign labels are preserved unchanged: `Tom & Jerry`, `The Matrix (1999)`, `Depeche Mode - Violator`.
- `build_dd_command`: returns a `list`, element 0 is `"dd"`, the destination appears as exactly one argv element (proving no shell splitting), and `DATA_RIP_PARAMETERS` like `"bs=1M conv=noerror"` splits into separate elements.

Manual/integration note: `rip_data` itself invokes `dd` on a real device and is not unit-tested; the pure helpers (`sanitize_label`, `build_dd_command`) carry the security-relevant logic and are fully covered. Full suite + flake8 run in the dev container and under CI across 3.9–3.12.

## Success criteria

- `rip_data` no longer uses `shell=True`; the `dd` invocation is list-form with stderr redirected via a file handle.
- `job.label` is sanitized at every untrusted source and (idempotently) before path construction in `rip_data`.
- A crafted volume label cannot execute commands or escape the raw/completed directories.
- Normal labels are unchanged (no path separators/control chars → identical output).
- New unit tests pass across 3.9–3.12; flake8 clean; existing suite still green.
