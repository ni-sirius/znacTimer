# znacTime — Migration Status and Native Release Plan

> Repository layout: the Python project now lives in `projects/znacpy/`.
> Unless explicitly repository-wide, source paths and commands in this plan
> are relative to that project directory. The release-tree checker remains
> at repository-root `scripts/check_release_tree.py` (use
> `../../scripts/check_release_tree.py` from the project). Packaging and CI
> examples below are design sketches and need those working-directory paths.

> Current-state review: **2026-09-14**, application version declared in
> [`pyproject.toml`](../../../projects/znacpy/pyproject.toml), SQLite schema **6**.
> The modular refactor, PySide6 migration, and SQLite production cutover are implemented.
> The remaining major work is native packaging, GitHub Actions, and release verification.
> “Implemented” describes the checked-in application, not a verified native package.

## Completed migration work

The former Phases 1–5 are closed implementation work. Their original step-by-step
instructions remain in Git history rather than being presented as future tasks here.

| Area | Current implementation | Evidence |
|---|---|---|
| Core extraction | Models, calendar/time helpers, calculation, and validation are independent of GUI code. | [core/](../../../projects/znacpy/znactime/core/), calculator/time/calendar tests |
| Storage separation | A repository protocol, storage errors, SQLite implementation, legacy import, and explicit export modules separate persistence from widgets. | [repository.py](../../../projects/znacpy/znactime/storage/repository.py), [storage/sqlite/](../../../projects/znacpy/znactime/storage/sqlite/) |
| Qt migration and binding | PySide6 is the production UI; Tkinter/tksheet and PyQt6 are no longer application backends. | [Qt UI](../../../projects/znacpy/znactime/ui/qt/), [project metadata](../../../projects/znacpy/pyproject.toml), [universal lock](../../../projects/znacpy/uv.lock) |
| Application launcher | The launcher sets the application identity, acquires the database ownership lock, and injects a SQLite repository into the window. `tracker.py` is a compatibility wrapper. | [__main__.py](../../../projects/znacpy/znactime/__main__.py), [tracker.py](../../../projects/znacpy/tracker.py) |
| SQLite cutover | Time records, schedules, work limits, breaks/timer state, month status, and closed results are stored in SQLite; edits use transactions and revisions. | [SQLite repository](../../../projects/znacpy/znactime/storage/sqlite/repository.py), [Qt model](../../../projects/znacpy/znactime/ui/qt/model.py) |
| Per-user database location | The live database already uses `QStandardPaths.AppLocalDataLocation`, independently of the working directory. | [database_path()](../../../projects/znacpy/znactime/ui/qt/first_launch.py) |
| Legacy import | Validated, staged first import and subsequent protected merges preserve source files; completed imports produce private reports and recognize repeated snapshots. | [legacy_csv_import.py](../../../projects/znacpy/znactime/storage/legacy_csv_import.py), [SQLite importer](../../../projects/znacpy/znactime/storage/sqlite/legacy_import.py) |
| First launch and recovery | Create/import/exit, interrupted-setup recovery, corruption handling, verified pre-upgrade backups, and failed-schema-upgrade recovery are implemented. | [first_launch.py](../../../projects/znacpy/znactime/ui/qt/first_launch.py), [bootstrap.py](../../../projects/znacpy/znactime/storage/sqlite/bootstrap.py) |
| Background operations | Legacy inspection/import and explicit backup use cancellable worker tasks with worker-owned repository connections where needed. | [background.py](../../../projects/znacpy/znactime/ui/qt/background.py), [app.py](../../../projects/znacpy/znactime/ui/qt/app.py) |
| Month lifecycle | Closing stores results transactionally; controlled reopening permits corrections without rewriting later closed months and exposes carry-over discontinuities. | [database dictionary](../../../docs/DATABASE_SCHEMA.md), [lifecycle tests](../../../projects/znacpy/tests/test_month_lifecycle_ui.py) |
| Exports and backup | Month CSV, PDF, and verified database backup are explicit user-selected operations with atomic publication and protected-destination checks. Current CSV exports use schema v3. | [csv_export.py](../../../projects/znacpy/znactime/storage/csv_export.py), [csv_format.py](../../../projects/znacpy/znactime/storage/csv_format.py), [atomic_file.py](../../../projects/znacpy/znactime/storage/atomic_file.py) |
| Regression coverage | Core, SQLite, migration/recovery, UI, timer, themes, exports, and release-source checks have existing automated tests. | [tests/](../../../projects/znacpy/tests/), [check_release_tree.py](../../../scripts/check_release_tree.py) |

Verification during this review: `python -m unittest discover -s tests -q` completed
successfully on the local Windows source environment: **311 tests run, 2 skipped**.
The release-source allowlist check also passed. Native packages and GitHub-hosted runs
remain unverified; these local results do not close the platform acceptance checklist.

Do not recreate these components or reintroduce CSV autosave, automatic PDF-on-close,
or `.flag` writes into the production flow. Closing a month and exporting it are separate
operations. Closed results remain protected until the explicit reopen transition;
“closed months can never be reopened” is an obsolete requirement.

## Current architecture and storage contract

```text
znactime/
├── __main__.py             # identity, ownership lock, startup, Qt event loop
├── config.py               # app/version constants; legacy CSV DATA_DIR remains here
├── core/                   # GUI-independent records, validation, calculation
├── storage/
│   ├── repository.py       # semantic storage protocol
│   ├── sqlite/             # schema v6, migrations, repository, bootstrap, import
│   ├── legacy_csv_import.py
│   ├── legacy_import_log.py
│   ├── csv_export.py       # explicit month export
│   ├── pdf_export.py
│   ├── atomic_file.py
│   ├── csv_store.py        # retained legacy helpers, not live persistence
│   └── paths.py            # retained legacy CSV layout helpers
└── ui/qt/                  # PySide6 window, model, table, timer, themes, settings
tests/                      # top-level unittest suite
scripts/                    # release-source check, import verifier, screenshots
```

Keep `core/` and storage implementation independent of GUI libraries. The Qt composition
root resolves the database path and passes it to storage. The Qt model uses repository
records and methods; SQL and driver details remain in storage.

### Live database and settings

Startup sets `ORGANIZATION_NAME = "znac"` and `APP_NAME = "znacTime"` before resolving:

```python
root = QStandardPaths.writableLocation(
    QStandardPaths.StandardLocation.AppLocalDataLocation
)
database = Path(root) / "znactime.db"
```

The Windows resolver was checked during this review and produces
`%LOCALAPPDATA%\znac\znacTime\znactime.db` with the current identity. On macOS and Linux,
resolve the path through Qt on that target and report it in the release documentation;
do not construct it from a guessed home-directory layout. Qt provides platform-specific
per-user locations through [QStandardPaths](https://doc.qt.io/qt-6/qstandardpaths.html).

Database sidecars, startup/application locks, import reports, staging files, and recovery
files derive from the database location. Exported CSV/PDF files and explicit backups go
to destinations selected by the user. UI preferences use the existing explicit
`QSettings("znacTime", "znacTime")` namespace. Startup and the main window now share that
same settings object; the earlier default `znac/znacTime` startup read was inconsistent
with the namespace used to save preferences. Time records and timer state are not stored
in `QSettings`.

**Keep the existing database location.** Packaging does not require `platformdirs`,
moving SQLite into another directory, or a new location-migration mechanism. Changing
organization/application names risks making existing data or settings appear missing
and is outside the release work.

### What the remaining `data/` references mean

- `config.DATA_DIR`, `storage/paths.py`, and `csv_store.py` retain the old CSV layout for
  legacy helpers/tests. Their presence does not describe the live database location.
- First-launch and subsequent CSV-import dialogs suggest `Path.cwd() / "data"` if it
  exists, otherwise the home directory. This is an import-folder suggestion; the user
  chooses and confirms the source. It is not a runtime storage destination.
- Legacy `.flag` files help interpret imported month status. Existing CSV files, flags,
  historical summaries, and PDFs remain untouched; they are not live write targets.
  The current importer recognizes monthly CSV files and matching flags, not every file
  in a historical folder.
- Source-folder discovery beside a frozen executable could improve the import dialog,
  but is optional convenience work. Manual folder selection already exists.

### Scope and reference documents

[README.md](../../../projects/znacpy/README.md) describes current usage and
[docs/DATABASE_SCHEMA.md](../../../docs/DATABASE_SCHEMA.md) describes the implemented schema.
[SQLITE_MIGRATION_PLAN.md](SQLITE_MIGRATION_PLAN.md) retains the detailed migration design
and release checks. Its August checkpoint and original requirements include superseded
items such as schema v1, synchronous legacy import, CSV v2 output, and no reopening.
Use the current implementation and database dictionary for those behaviors; do not turn
obsolete requirements back into new migration tasks. Retain the established backup,
validation, source-preservation, and recovery guarantees.

Year/all-data CSV export, database encryption, authenticated synchronization, automatic
updates, and optional legacy-helper cleanup are separate follow-up work. They are not
prerequisites for packaging the current month-export application. Startup schema upgrade
and recovery calls still run directly from first launch; any responsiveness improvement
there should be scoped separately from the already-implemented background import/backup.

## Phase 6 — Remaining Packaging & Distribution Work

**Goal:** package the current PySide6/SQLite application first for Windows x64 and
macOS on Apple silicon without changing its storage identity or implemented behavior.
Build from one cross-platform dependency lock through the same local and GitHub Actions
entry point, verify both native packages, and publish the exact tested artifacts. Linux
and macOS x64 are explicitly deferred until this two-target delivery flow is stable.

Sections 6.1–6.7 below are implementation tasks. Section 6.8 is the remaining packaged
release acceptance checklist, not a list of missing application features. Phase numbering
is retained so existing references to Phase 6 remain useful.

### 6.0 — Preserve and verify existing storage behavior in frozen builds

The move away from `data/` is **complete for production persistence**. The remaining
release gate is proving that the installed/frozen application preserves that behavior:

### Disposition of the original eight prerequisites

The earlier version of this plan contained eight location-migration prerequisites. They
were written before the current SQLite implementation was compared with the plan. This
audit records the disposition of each original point so a removed implementation proposal
is not mistaken for completed work.

1. **Add `platformdirs`, regenerate the dependency lock, and add it to project metadata —
   dependency metadata migrated; the `platformdirs` part is superseded.**

   `pyproject.toml` and the cross-platform `uv.lock` now own the dependencies and do not
   contain `platformdirs`. It was proposed to replace a working-directory `data/` root,
   but production persistence already uses Qt's cross-platform
   `QStandardPaths.AppLocalDataLocation`. Adding a second path resolver would duplicate Qt
   and could change the identity of existing installations.

2. **Make `storage/paths.py` own platform data/document locations and remove
   `config.DATA_DIR` — not done; superseded for production storage.**

   `storage/paths.py` and `config.DATA_DIR` now serve retained legacy CSV helpers and tests.
   They do not select the live database. The live path is already platform-correct through
   Qt. Removing these names is optional legacy cleanup and must be evaluated against CSV
   compatibility helpers; it is not a packaging prerequisite. Export-dialog defaults may
   use Qt's `DocumentsLocation` without introducing another dependency.

3. **Move `database_path()` into storage and route all persistent files through it —
   behavior complete; the proposed module move was not done.**

   The Qt composition root resolves the path and injects the same target into the process
   lock, bootstrap/recovery flow, and SQLite repository. Database sidecars, locks, staging,
   recovery files, and import logs derive from that target. Startup and the main window now
   also share the existing `QSettings("znacTime", "znacTime")` object. No live persistence
   derives from `Path.cwd()` or the bundle directory. `Path.cwd() / "data"` remains only a
   suggested source in a user-confirmed legacy import dialog. Keeping the Qt-specific
   resolver at the UI/composition boundary avoids importing PySide6 into storage.

4. **Add a one-time migration from old SQLite/data locations, including automatic frozen
   executable discovery — not done; no supported old SQLite location needs relocation.**

   The SQLite cutover already created the live database in `AppLocalDataLocation`. Legacy
   CSV is handled through the existing explicit Create/Import/Exit flow and later manual
   merge action. The app does not automatically probe or import `data/` beside an executable,
   because finding a folder is not enough authority to modify the live ledger. Repeated CSV
   snapshots are identified by fingerprint and do not import twice. Discovery beside the
   executable remains an optional dialog convenience, not a data migration requirement.

5. **Preserve legacy CSV and migrate databases only through validated, backup-first,
   atomic operations — complete for supported inputs; arbitrary SQLite relocation is not
   implemented.**

   Legacy CSV sources are never modified. CSV import uses full preflight, a staging
   database, integrity/relationship validation, atomic promotion, and a user-readable
   import log. Forward SQLite schema migrations create and validate a recovery backup,
   migrate transactionally, reopen and validate, and retain recovery evidence on failure.
   The app refuses to overwrite a populated setup destination. Moving an arbitrary SQLite
   database from an undocumented location is intentionally unsupported because there is no
   recognized prior production SQLite location to migrate.

6. **Mark migration complete only after reopen and integrity/schema validation; keep
   interrupted work retryable — complete for setup/import and schema migrations.**

   New-database creation and legacy import publish staged databases only through the
   bootstrap flow. Interrupted `.creating` and `.migrating` states are inspected and can be
   completed or archived without silent deletion. Schema upgrades use verified backups,
   transaction rollback, post-commit reopen validation, and a retryable failure marker.
   There is no separate “location migration complete” marker because point 4's location
   migration is not applicable.

7. **Keep CSV/PDF/backup destinations user-selected and default them to Documents —
   partially done.**

   All three operations are user-selected, reject protected SQLite destinations, and use
   atomic publication or SQLite's verified backup API. The dialogs currently receive a
   suggested filename rather than an explicit `QStandardPaths.DocumentsLocation` path.
   The Documents default is still open. It is a usability improvement, not a condition for
   keeping the database writable outside the installed bundle.

8. **Add cross-platform path, frozen/source discovery, migration, recovery, and export
   default tests — partially done.**

   Existing tests cover isolated database targets, working-directory independence,
   database/lock/backup placement outside an installed-application directory, stable
   settings identity, first launch, repeated import, staging recovery, schema migration,
   backup validation, corruption handling, and protected export destinations. The suite
   uses temporary paths and does not access the developer's live database. Tests for the
   superseded automatic executable discovery/location migration are not needed. Still open:
   native `QStandardPaths` verification in Windows x64 and macOS arm64 jobs; the explicit
   Documents default if point 7 is implemented; and frozen-package plus clean-machine
   install/upgrade/uninstall acceptance.

### Active Phase 6.0 release gate

- [x] Preserve Qt's existing production database location and application identity.
- [x] Allow an explicit Python test root without consulting the real user-data directory.
- [x] Pass one resolved target through locking, bootstrap/recovery, and repository startup.
- [x] Pass one stable settings object through startup and the main window.
- [x] Cover the local storage/startup prerequisites with isolated automated tests.
- [ ] Decide and implement the optional Documents-directory dialog default.
- [ ] Run storage-path and recovery tests on every GitHub Actions native runner.
- [ ] Complete frozen-package and clean-machine upgrade/uninstall acceptance after the
      packages exist.

### 6.1 — Delivery architecture

The initial delivery scope has exactly two native targets:

| Target | GitHub-hosted runner | Architecture | Candidate artifact |
|---|---|---|---|
| `windows-x64` | `windows-2022` | x64 | `znacTime-<VERSION>-windows-x64-Setup.exe` |
| `macos-arm64` | `macos-15` | Apple silicon arm64 | `znacTime-<VERSION>-macos-arm64.dmg` |

PyInstaller is not a cross-compiler. Windows must be built on Windows and the
Apple-silicon package on an arm64 macOS runner. A local build produces only the package
for its current host. GitHub Actions supplies the native hosts but does not own a second
implementation of the build. See the
[PyInstaller project documentation](https://pyinstaller.org/en/stable/) and
[GitHub-hosted runner reference](https://docs.github.com/en/actions/reference/runners/github-hosted-runners).

Use one flow locally and in CI:

```text
pyproject.toml
      ↓
   uv.lock
      ↓
uv run python packaging/build.py
      ↓
 znactime.spec
      ↓
PyInstaller bundle
      ↓
native installer or DMG
      ↓
 dist/release/
```

Linux and macOS x64 are deferred until this two-target flow is stable.

### 6.2 — One cross-platform dependency model with uv

Adopt `uv` for project environments and dependency locking.

The uv project lock is universal and can represent platform-specific distributions in one
file; see the [uv project structure and lockfile documentation](https://docs.astral.sh/uv/concepts/projects/layout/).

1. Add `projects/znacpy/pyproject.toml` as the only hand-edited source of Python
   requirements:
   - `[project].dependencies` owns direct runtime dependencies;
   - `[dependency-groups].build` owns PyInstaller and Python packaging tools;
   - `[build-system]` selects and pins the backend that installs the package and GUI script;
   - `[project].requires-python` records the supported Python range.
2. Commit one generated `projects/znacpy/uv.lock`. It contains the exact transitive
   resolution, platform distributions, and hashes for Windows x64 and macOS arm64.
   It is generated by uv and never edited manually.
3. Limit the universal resolution to CPython on those two supported environments and
   require both environments to resolve binary distributions.
4. Keep the exact interpreter selection in `.python-version`. The broader
   `requires-python` range expresses compatibility and is not a second exact patch pin.
5. Pin the uv release used by GitHub Actions. Updating uv and regenerating the lock is a
   reviewed dependency change.
6. The former `requirements.in`, `requirements.txt`, and `requirements-dev.txt` entry
   points have been removed. Do not reintroduce them as parallel authorities.
7. Replace `tests/test_dependency_lock.py` with checks for the declared dependency
   groups and two target environments. CI enforces lock freshness with
   `uv sync --locked`; tests must not duplicate package versions or wheel hashes.

This replaces the previous proposal for per-platform runtime and build lock files.
Dependency versions must not be copied into workflows, packaging scripts, or tests.

### 6.3 — Project metadata, entry points, and version

Define standard metadata in `pyproject.toml`:

```toml
[build-system]
requires = ["hatchling==<reviewed version>"]
build-backend = "hatchling.build"

[project]
name = "znactime"
version = "<current application version>"
requires-python = ">=3.12,<3.13"
dependencies = [
    "PySide6==<reviewed version>",
    "reportlab==<reviewed version>",
]

[project.gui-scripts]
znactime = "znactime.__main__:main"

[dependency-groups]
build = [
    "pyinstaller==<reviewed version>",
]
```

Concrete versions are selected during implementation; this plan intentionally does not
create another version list.

Use `pyproject.toml` as the single application-version source. Replace the hard-coded
`znactime.config.VERSION` value with
`importlib.metadata.version("znactime")`. Existing modules may continue importing
`VERSION` from `config.py`, but no second fallback version literal is allowed. The
About dialog, title, build script, package metadata, artifact names, and tag validation
must all read the installed project metadata. Remove hard-coded versions from README
badges; a release badge may derive from GitHub tags.

The entry points are:

- development: `uv run znactime`;
- module compatibility: `uv run python -m znactime`;
- frozen application: `packaging/launcher.py` calling `znactime.__main__.main()`;
- package build: `uv run python packaging/build.py`.

`tracker.py` may remain temporarily for compatibility but is not used by packaging or CI.

### 6.4 — Shared packaging implementation and local flow

Add this structure:

```text
projects/znacpy/
├── .python-version
├── pyproject.toml
├── uv.lock
├── packaging/
│   ├── build.py
│   ├── launcher.py
│   ├── znactime.spec
│   ├── smoke_native.py
│   ├── windows/
│   │   ├── icon.ico
│   │   └── znactime.iss
│   └── macos/
│       ├── icon.icns
│       └── entitlements.plist
└── dist/release/
```

The local flow from `projects/znacpy` is:

```text
uv sync --locked --group build
uv run znactime
uv run python packaging/build.py --mode unsigned
```

`packaging/build.py` is the only build entry point. It must:

1. Detect the host when `--target auto` is used.
2. Accept explicit `windows-x64` and `macos-arm64` targets in CI.
3. Reject host/target mismatches.
4. Read the version from installed project metadata.
5. Validate assets and locate/version-check native tools.
6. Invoke `python -m PyInstaller --clean --noconfirm packaging/znactime.spec`.
7. Run the platform's native packaging stage.
8. Support `--mode unsigned` and `--mode release`; release mode must fail if signing
   inputs are unavailable and must never silently fall back to unsigned output.
9. Write final packages, checksums, notices, smoke reports, and a build manifest only to
   `dist/release/`.
10. Record commit, version, target, host, Python, uv, lock digest, PyInstaller, and
    native-tool versions in the manifest.

Use checked Python subprocess calls. Do not duplicate this logic in PowerShell, Bash, or
workflow YAML.

The shared PyInstaller spec sets the project root in `pathex`, uses
`packaging/launcher.py`, collects only required Qt modules/plugins, and includes theme
JSON, PNG assets, and third-party notices. Platform-specific icon and bundle settings may
branch in the spec; dependency versions may not.

### 6.5 — Native package requirements

#### Windows x64

1. Produce a PyInstaller one-directory bundle and include its complete runtime directory.
2. Build a per-user installer from a checked-in Inno Setup definition with stable
   `AppId`, upgrade metadata, Start-menu shortcut, and uninstall entry.
3. Never install, move, or delete the user's database.
4. Pin and verify Inno Setup rather than relying on an incidental runner installation.
5. Allow unsigned pull-request candidates. Release mode signs and timestamps the
   application, generated uninstaller, and final Setup executable, then verifies them.
6. Perform clean Windows 11 acceptance for install, launch, upgrade, uninstall, data
   preservation, recovery, and PDF export.

#### macOS arm64

1. Produce a native arm64 `znacTime.app` with a stable bundle identifier, version,
   `icon.icns`, required Qt resources, and no writes inside the bundle.
2. Unsigned CI candidates may use ad-hoc signing only for smoke execution; they are not
   public release artifacts.
3. Release mode imports a Developer ID Application identity into a temporary keychain and
   signs nested code in the correct order with Hardened Runtime and reviewed entitlements.
4. Notarize and staple the application, then create, sign, notarize, staple, and validate
   the DMG.
5. Change no bundle content after signing; generate checksums after notarization/stapling.
6. Perform clean macOS acceptance for quarantined Finder launch, first launch, upgrade,
   stable settings/data identity, recovery, and PDF export.

Signing and notarization are required for public release, not for proving the first
unsigned GitHub Actions build flow.

### 6.6 — GitHub Actions flow

Implement two workflows:

| Workflow/event | Purpose | Credentials |
|---|---|---|
| `ci.yml`: pull requests and default-branch pushes | Sync, test, build, and smoke-test two unsigned candidates | Read-only token; no signing secrets |
| `release.yml`: version tags | Repeat in release mode, sign, notarize, aggregate, and create a draft release | Scoped platform signing environments |

Both workflows use the same matrix:

```text
windows-x64  → windows-2022 → x64
macos-arm64  → macos-15     → arm64
```

Use explicit runner labels, pin production actions to reviewed full commit SHAs, and keep
default `permissions: contents: read`. Grant write or OIDC only to jobs that require it.
Never use `pull_request_target` to build contributor code.

Each unsigned job performs:

```text
checkout
install the pinned uv release
uv python install
uv sync --locked --group build
uv run python ../../scripts/check_release_tree.py
uv run python -m unittest discover -s tests -v
uv run python packaging/build.py --target <target> --mode unsigned
uv run python packaging/smoke_native.py --target <target>
upload dist/release/*
```

Project commands run from `projects/znacpy`. Workflow YAML supplies only event policy,
runner, target, permissions, timeout, and artifact retention. It must not repeat
dependency/application versions, PyInstaller flags, package commands, or artifact-name
logic.

Use distinct artifact names containing target, run ID, and attempt. Upload completed
Setup EXE and DMG files, not loose PyInstaller directories or an unpackaged `.app`.

### 6.7 — Verification and trusted release

Add a bounded diagnostic mode:

```text
--smoke-test --data-dir <temporary-path> --report <path>
```

It runs before normal first-launch dialogs and never accesses real user data. The packaged
smoke test starts the bundled executable outside the checkout, without `PYTHONPATH` or
development Qt paths, and verifies:

- the native Windows or Cocoa Qt plugin starts;
- icons and themes load;
- a temporary SQLite database can be created, edited, closed, and reopened;
- PDF export succeeds;
- data remains outside the bundle;
- the process exits within a timeout and writes a machine-readable report.

Hosted runners do not prove clean-machine independence or Finder/Start-menu integration;
record separate clean-system acceptance for each release candidate.

Trusted release flow:

1. Validate a `vX.Y.Z` tag against the single project version and release branch.
2. Run both native jobs from the resolved tag commit with `--mode release`.
3. Expose Apple credentials only to macOS and Windows credentials only to Windows.
4. Verify signatures/notarization and smoke-test the final packages.
5. Generate checksums and manifests after signing/stapling.
6. Aggregate exactly one Setup EXE and one arm64 DMG from the same commit/version; any
   failed or missing target blocks publication.
7. Create a draft GitHub Release without overwriting an unexpected existing release.
8. Accept the exact downloads on clean machines, compare checksums, and publish the
   existing draft without rebuilding.

### 6.8 — Delivery checklist and definition of done

- [x] `pyproject.toml` is the only hand-edited source of Python dependency versions.
- [ ] One reviewed `uv.lock` resolves and installs on Windows x64 and macOS arm64.
- [x] Obsolete requirements files and hard-coded dependency expectations are removed.
- [ ] Python, uv, PyInstaller, and native packaging tools have designated single pins.
- [ ] `uv run znactime` launches on both targets.
- [ ] The same `packaging/build.py` builds locally and in GitHub Actions.
- [ ] The build rejects host/target mismatches and writes a complete manifest.
- [ ] The release-tree allowlist accepts only reviewed TOML, lock, workflow, SPEC,
      Python-version, installer, PLIST, ICO, and ICNS inputs and still rejects user data,
      credentials, caches, and build output.
- [ ] Both GitHub-hosted jobs pass the automated suite and packaged smoke test.
- [ ] Windows install, launch, upgrade, and uninstall preserve user data.
- [ ] The macOS arm64 DMG is signed, notarized, stapled, and passes Gatekeeper.
- [ ] Frozen/source upgrades retain the Qt-resolved database and settings identity.
- [ ] First launch, import, interrupted setup, migration, recovery, backup, themes,
      CSV/PDF export, and month close/reopen work in both artifacts.
- [ ] Version displays, package metadata, tag, artifact names, checksums, and manifests
      derive from the same project version.
- [ ] Artifacts include notices and exclude user data, credentials, fixtures, settings,
      caches, and developer paths.
- [ ] A failed job, stale lock, missing asset, signing/notarization failure, or inconsistent
      version/checksum blocks draft release creation.
- [ ] The exact tested candidate is published and the previous supported release remains
      available for executable rollback.

---

## Maintenance responsibilities

| Layer | Owns | Can change without breaking |
|---|---|---|
| `core/` | domain logic | storage, UI |
| `storage/` | SQLite, migrations/recovery, legacy import, CSV/PDF export | core, UI |
| `ui/qt/` | Qt widgets | core, storage |
| `tests/` | all of core + storage | UI (headless) |

---

## Invariants during release work

- Preserve current Qt storage/settings identities and SQLite data across upgrades.
- Keep time records authoritative in SQLite; legacy CSV/flags are import inputs only.
- Preserve current CSV v3 export and legacy-version import behavior.
- Keep month close/reopen transactional and export failure independent of month status.
- Preserve validated backups, recovery evidence, and original legacy sources.
- Package only reviewed application resources and third-party notices, never user data.
