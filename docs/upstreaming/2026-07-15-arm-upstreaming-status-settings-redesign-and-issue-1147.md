# ARM Upstreaming — Status & Research

**Last updated:** 2026-07-15
**Purpose:** Single place to resume the effort of contributing this fork's work back to the
upstream ARM project. Covers (1) the **Ripper Settings page redesign** and (2) the
**"Don't change ownership of the Completed folder" issue (#1147)**.

**Resurface keywords:** upstreaming, upstream PR, ripper settings redesign, settings UI,
issue 1147, completed folder ownership, chown, permissions, UI-Safety-Updates-Settings-Restructure,
3.0_devel, cherry-pick onto upstream.

---

## 0. Ground truth: fork vs upstream

- `origin`  = `github.com/conradstorz/automatic-ripping-machine` (this **personal fork**)
- `upstream` = `github.com/automatic-ripping-machine/automatic-ripping-machine`
- The fork's `main` is **34 commits ahead / 0 behind** `upstream/main` — it carries unrelated
  fork work (Docker dev env, dev-server banner, security hardening, disc-label injection fix).
- **Golden rule for any upstream PR:** branch off `upstream/<base>` and **cherry-pick only the
  feature's commits** onto it. Never PR from the fork's `main` — it would drag in all 34 commits.

Default stance remains "work stays on the fork," but the user is now open to upstreaming
*select, genuinely polished* pieces, weighed case by case.

---

## 1. Work item A — Ripper Settings page redesign

### 1.1 What it is / why
The old Ripper Settings tab rendered every `arm.yaml` key as a flat `KEY: value` text box with
help hidden behind an info icon — the user called it "unusable." The redesign groups the ~83 keys,
gives each the right control (toggle / dropdown / number+unit / path / text), shows human labels +
the raw `KEY` chip + always-visible help, and adds live search and a sticky side-nav index.

### 1.2 Scope of the change — **presentation only, save path untouched**
It is a presentation + input-widget change over an **unchanged** save contract. Same field
`name=KEY`, same POST to `/save_settings`, same `build_arm_cfg`. The one functional nuance is an
*improvement*: booleans are backed by hidden inputs that always serialize `true`/`false`, fixing a
latent bug where an unchecked checkbox could silently drop that key from `arm.yaml`.

Files:
| File | Change |
|---|---|
| `arm/ui/settings/ripper_fields.py` (**new**) | Display model: `GROUPS`, curated `FIELDS` map, `humanize()`, `build_field_model()`. Guarantees every key yields exactly one field (unmapped keys → "Advanced"/text), so nothing is ever dropped on save. |
| `arm/ui/settings/settings.py` | Added one context var: `ripper_groups=build_field_model(...)` (around line 144). Nothing else. |
| `arm/ui/settings/templates/settings/ripper.html` (**rewritten**) | Grouped, typed controls, inline help, search, side-nav. Scoped under `#rs-root`. Preserves `#settings` / `#ripperSettings` form + `form.hidden_tag()`. |
| `test/unittest/test_ui_ripper_fields.py` (**new**) | 9 tests for the field model (coverage, fallback, humanization, bool serialization). |

Verified: 83/83 keys covered at model, rendered-template, and `build_arm_cfg` round-trip levels;
full suite 92 passed; flake8 clean; toggle + search exercised in a real headless browser.

Parent page wiring: `settings.html` (the tabbed page) does `{% include 'settings/ripper.html' %}`
at line ~90.

### 1.3 Branches & PR
- **Fork feature branch:** `feature/ripper-settings-redesign` → **PR #4 open on the fork.**
  Commits: `4329fdc` (redesign) · `b0848a0` (nav/header backgrounds) · `392427a` (scroll offset).
- **Clean upstream-ready branch (local only, not pushed):** `upstream-ripper-settings-redesign`,
  cherry-picked onto `upstream/main`. Commits: `5d5037dc` · `191cea21` · `307bc967`. Contains
  **only the 4 redesign files**, zero conflicts. Ready to push + PR whenever.

### 1.4 Optional old/new toggle (idea only — NOT built)
To soften the blow for users who prefer the old layout, we could ship both templates and let the
user toggle. Low-risk because both POST identically. Cheapest approach: recover the old template
as `ripper_classic.html` (`git show 4329fdc~1:arm/ui/settings/templates/settings/ripper.html`),
add a conditional `{% include %}`, and pick via a **cookie/query-param** + a "Classic view ⇄ New
view" link (no DB, no migration; ~1 hour TDD). A `UISettings` DB column is the heavier alternative.
**Framing if upstreamed:** pitch the toggle as a *temporary migration path* (new UI default,
classic available a release or two, then retired), not a permanent dual UI — much easier maintainer sell.

### 1.5 ⚠️ Upstream overlap — competing effort in flight
Upstream already has a **large settings overhaul** on branch
`upstream/UI-Safety-Updates-Settings-Restructure` (~1,791 lines). It's a **different architecture**:

| | Our redesign | Upstream's in-flight branch |
|---|---|---|
| Approach | Python field-model + curated map + rewritten `ripper.html` | JSON-driven dynamic forms (`ripperFormConfig.json`, `dynamic_form.html`, `forms_custom_validators.py`) |
| Scope | Ripper settings page only | All settings pages + validation + utils |
| Status | Done, tested | Active WIP |

A full competing rewrite of `ripper.html` dropped in cold risks being closed as duplicate or told
to fold into their JSON approach. **Etiquette: talk first** (issue/discussion with screenshots +
branch link, acknowledging their parallel work) rather than a cold PR.

### 1.6 Decision (2026-07-15)
**Keep local for now.** Wait a few days to see whether the upstream settings-restructure effort is
progressing before deciding whether/how to join in. Both branches parked; nothing public.

**How to check upstream momentum later:**
```
git fetch upstream
git log --oneline -5 upstream/UI-Safety-Updates-Settings-Restructure   # still moving?
git log --oneline upstream/main..upstream/UI-Safety-Updates-Settings-Restructure | wc -l
```
If **stalled** → our standalone redesign is a stronger offering. If **actively merging** → fold our
ideas into their JSON-driven approach instead.

---

## 2. Work item B — Issue #1147 "Don't Change Ownership of the Completed Folder"

**Upstream issue:** #1147 (opened 2024-06-12 by @Queuecumber). Tags: `enhancement`,
**`Good first issue`**. Milestones: ARM backlog + **v3.0**.
**Pre-blessed:** maintainer @shitwolfymakes agreed to the direction and stated the intended v3.0
solution: *"have the file write use the permissions and owner of the destination dir if
technically possible."* Reporter confirmed that satisfies the request.

### 2.1 Code research — where ownership/perms get touched today
| Path | What it does | Already opt-out? |
|---|---|---|
| Startup shell `scripts/docker/runit/arm_user_files_setup.sh` | `check_folder_ownership` (lines 18–33) only **checks** & `exit 1`s — does **not** chown. Subdir loop (62–71) chowns **only dirs it had to create** (`if [[ ! -d ]]`). `chown -R arm:arm /opt/arm` is the install dir, not media. | A **pre-existing mounted `completed` folder is not chowned at startup** anymore. |
| After each rip: `set_permissions()` `arm/ripper/utils.py:573` (called from `arm/ripper/arm_ripper.py:97`) | `chmod` only (no chown), only on the **job's own output folder**. | Gated by `SET_MEDIA_PERMISSIONS`. |
| UI "Fix perms" button: `fix_permissions()` `arm/ui/utils.py:519` (wired at `arm/ui/jobs/jobs.py:335`) | `chmod` + optional `chown`. Manual, not automatic. | chown gated by `SET_MEDIA_OWNER` (+ `CHOWN_USER`/`CHOWN_GROUP`). |

### 2.2 ⚠️ The wrinkle — may be **partially fixed already**
The reporter's symptom ("at startup the owner changes") looks like it was **largely addressed** by
later hardening of the startup script (the `! -d` guard + check-only ownership function appear to
postdate the June-2024 issue). **First step is confirmation, not code** — verify on current
`main`/`3.0_devel` what's still reproducible so we don't rebuild something already done.

### 2.3 The real remaining feature
The unbuilt work = the maintainer's v3.0 wish: an **inherit-from-destination mode** — instead of
applying configured `CHMOD_VALUE`/`CHOWN_USER`, `os.stat()` the destination folder and reuse its
uid/gid/mode when writing completed files.

### 2.4 Effort estimate — small-to-medium, ~½–1 day
- **Logic (~30 lines):** an "inherit" branch in `set_permissions()` and `fix_permissions()` —
  read `os.stat(destination)`, apply that instead of config values. Clean to TDD on a temp dir.
- **New config key** (e.g. `INHERIT_MEDIA_OWNER`) is the fiddly part — config keys are threaded
  through **five** places: `setup/arm.yaml`, `arm/ui/comments.json`, the **`Config` DB model**
  (`arm/models/config.py` — confirmed real columns, e.g. `SET_MEDIA_OWNER` at line 40), an
  **Alembic migration** (`arm/migrations/`), and the per-job snapshot. Copy the `SET_MEDIA_OWNER`
  pattern next door. The migration is the main newcomer gotcha.
- **Bonus:** adding it to the UI is now trivial thanks to the settings redesign — one entry in
  `ripper_fields.py`.

### 2.5 Next steps (before writing code)
Post a short comment on #1147 that **claims the issue** and confirms scope:
1. "Is the startup-chown symptom still reproducible on current `main`/`3.0_devel`, or already fixed?
   I'd scope this to the inherit-destination-perms behavior described for v3.0 — correct?"
2. **Which base branch?** Tagged v3.0 + active `upstream/3.0_devel` exists → almost certainly
   targets **`3.0_devel`, not `main`**. Branch off `upstream/3.0_devel` (same clean cherry-pick approach).

(Claude offered to draft this comment — do that when ready to engage.)

---

## 3. Reusable upstreaming playbook (learned this session)
1. `git fetch upstream`.
2. Confirm the **base branch** the maintainers want (`main` vs `3.0_devel` vs a feature branch).
   Check the issue/PR labels & milestones.
3. Create a branch off `upstream/<base>`; **cherry-pick only the feature's commits** (verify the
   feature's files are untouched by unrelated fork commits so the cherry-pick is clean:
   `git log upstream/<base>..main -- <files>` should be empty).
4. `git diff --stat upstream/<base>..HEAD` to confirm the branch is feature-only.
5. When parallel/competing upstream work exists → **issue/discussion first**, screenshots +
   branch link, acknowledge their effort; don't drop a cold competing PR.
6. Run tests + flake8 (`--max-line-length=120`, `--max-complexity=15`) before proposing.

---

## 4. Quick-reference refs
- Fork PR: **#4** (`feature/ripper-settings-redesign`) — redesign commits `4329fdc` `b0848a0` `392427a`.
- Local upstream-ready branch: `upstream-ripper-settings-redesign` (off `upstream/main`) —
  `5d5037dc` `191cea21` `307bc967`.
- Upstream competing branch: `upstream/UI-Safety-Updates-Settings-Restructure`.
- Upstream v3 dev branch: `upstream/3.0_devel`.
- Issue: `automatic-ripping-machine/automatic-ripping-machine#1147`.
- Key code: `arm/ripper/utils.py:573` (`set_permissions`), `arm/ui/utils.py:519` (`fix_permissions`),
  `scripts/docker/runit/arm_user_files_setup.sh` (startup chown), `arm/models/config.py` (config columns).
