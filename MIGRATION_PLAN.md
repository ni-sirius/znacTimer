# znacTime — Migration Status and Native Release Plan

> Current-state review: **2026-09-14**, application **0.5.3**, SQLite schema **6**.
> The modular refactor, PySide6 migration, and SQLite production cutover are implemented.
> The remaining major work is native packaging, GitHub Actions, and release verification.
> “Implemented” describes the checked-in application, not a verified native package.

## Completed migration work

The former Phases 1–5 are closed implementation work. Their original step-by-step
instructions remain in Git history rather than being presented as future tasks here.

| Area | Current implementation | Evidence |
|---|---|---|
| Core extraction | Models, calendar/time helpers, calculation, and validation are independent of GUI code. | [core/](znactime/core/), calculator/time/calendar tests |
| Storage separation | A repository protocol, storage errors, SQLite implementation, legacy import, and explicit export modules separate persistence from widgets. | [repository.py](znactime/storage/repository.py), [storage/sqlite/](znactime/storage/sqlite/) |
| Qt migration and binding | PySide6 is the production UI; Tkinter/tksheet and PyQt6 are no longer application backends. | [Qt UI](znactime/ui/qt/), [requirements.in](requirements.in) |
| Application launcher | The launcher sets the application identity, acquires the database ownership lock, and injects a SQLite repository into the window. `tracker.py` is a compatibility wrapper. | [__main__.py](znactime/__main__.py), [tracker.py](tracker.py) |
| SQLite cutover | Time records, schedules, work limits, breaks/timer state, month status, and closed results are stored in SQLite; edits use transactions and revisions. | [SQLite repository](znactime/storage/sqlite/repository.py), [Qt model](znactime/ui/qt/model.py) |
| Per-user database location | The live database already uses `QStandardPaths.AppLocalDataLocation`, independently of the working directory. | [database_path()](znactime/ui/qt/first_launch.py) |
| Legacy import | Validated, staged first import and subsequent protected merges preserve source files; completed imports produce private reports and recognize repeated snapshots. | [legacy_csv_import.py](znactime/storage/legacy_csv_import.py), [SQLite importer](znactime/storage/sqlite/legacy_import.py) |
| First launch and recovery | Create/import/exit, interrupted-setup recovery, corruption handling, verified pre-upgrade backups, and failed-schema-upgrade recovery are implemented. | [first_launch.py](znactime/ui/qt/first_launch.py), [bootstrap.py](znactime/storage/sqlite/bootstrap.py) |
| Background operations | Legacy inspection/import and explicit backup use cancellable worker tasks with worker-owned repository connections where needed. | [background.py](znactime/ui/qt/background.py), [app.py](znactime/ui/qt/app.py) |
| Month lifecycle | Closing stores results transactionally; controlled reopening permits corrections without rewriting later closed months and exposes carry-over discontinuities. | [database dictionary](docs/DATABASE_SCHEMA.md), [lifecycle tests](tests/test_month_lifecycle_ui.py) |
| Exports and backup | Month CSV, PDF, and verified database backup are explicit user-selected operations with atomic publication and protected-destination checks. Current CSV exports use schema v3. | [csv_export.py](znactime/storage/csv_export.py), [csv_format.py](znactime/storage/csv_format.py), [atomic_file.py](znactime/storage/atomic_file.py) |
| Regression coverage | Core, SQLite, migration/recovery, UI, timer, themes, exports, and release-source checks have existing automated tests. | [tests/](tests/), [check_release_tree.py](scripts/check_release_tree.py) |

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

[README.md](README.md) describes current usage and
[docs/DATABASE_SCHEMA.md](docs/DATABASE_SCHEMA.md) describes the implemented schema.
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

**Goal:** package the current PySide6/SQLite application for Windows, Ubuntu/Linux, and
macOS without changing its storage identity or implemented behavior. Build from pinned
inputs on GitHub, verify the native packages, and publish the exact tested artifacts.

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

1. **Add `platformdirs`, regenerate `requirements.txt`, and add it to `pyproject.toml` —
   not done; the `platformdirs` part is superseded.**

   `requirements.in` still contains only PySide6 and reportlab, the current hash lock does
   not contain `platformdirs`, and `pyproject.toml` does not exist yet. `platformdirs` was
   proposed to replace a working-directory `data/` root, but production persistence already
   uses Qt's cross-platform `QStandardPaths.AppLocalDataLocation`. Adding a second path
   resolver would duplicate Qt and could change the identity of existing installations.
   Creating `pyproject.toml` remains required by Phase 6.2 for package metadata and the GUI
   entry point; it does not require `platformdirs`.

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
   native `QStandardPaths` verification in Windows, Ubuntu, macOS arm64, and macOS x64
   jobs; the explicit Documents default if point 7 is implemented; and frozen-package plus
   clean-machine install/upgrade/uninstall acceptance.

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

### 6.1 — Verified feasibility and missing release inputs

**GitHub Actions can build all target packages on GitHub-hosted machines.** Use
PyInstaller to bundle Python, PySide6, and the application, then use a separate native
packaging tool for each OS. PyInstaller is not a cross-compiler and does not itself create
an Inno Setup installer, DMG, or Debian package. See the
[PyInstaller project documentation](https://github.com/pyinstaller/pyinstaller/blob/develop/README.rst).

Repository review and documentation verification: **2026-09-14**. This is an implementation
plan, not evidence of successful builds on GitHub. The repository currently has:

- A PySide6 application, CPython 3.12 baseline, and `znactime.__main__.main()` launcher.
- `requirements.txt` with binary-only, SHA-256-verified **Windows x64 wheels only**.
  Reusing it on Linux or macOS will fail hash verification for platform-specific wheels.
- A standard-library `unittest` suite; `requirements-dev.txt` adds no test framework.
- `scripts/check_release_tree.py`, whose allowlist currently rejects workflow YAML,
  packaging metadata, installer scripts, and new icons.
- No GitHub Actions workflow, PyInstaller spec, native installer definitions, or frozen
  application smoke-test command. Phase 6.0 frozen-build storage verification remains open.

Before enabling release automation:

1. Add runtime locks at `requirements/locks/<target>.txt` for the four targets in 6.3.
   Resolve and review every transitive wheel on its native runner, preserving exact
   versions, `--only-binary=:all:`, and `--require-hashes`. Keep `requirements.in` as the
   shared declaration; retain Pillow as a locked transitive runtime dependency. Keep the root Windows installation entry point documented and in sync.
2. Add separate `requirements/build/<target>.txt` locks for PyInstaller, its hooks and
   transitive dependencies. Constrain shared dependencies to the runtime resolution and
   run `python -m pip check` after installation. Regenerate locks in a reviewed change,
   never during a release job. Update `tests/test_dependency_lock.py` to validate each
   target rather than its current hard-coded single Windows resolution.
3. Record one exact CPython 3.12 patch in `packaging/python-version.txt`. Pin downloaded
   installer/AppImage tools by version and checksum. Log runner image, Python, dependency,
   and packaging-tool versions in a build manifest; OS-version runner labels still receive
   image updates. Pinned inputs do not imply byte-identical signed/notarized output.
4. Add `znactime.spec`, `packaging/launcher.py`, `packaging/windows/znactime.iss`,
   `packaging/macos/entitlements.plist`, Linux desktop/control templates, native icons,
   and the shared scripts described in 6.7. The launcher only imports and invokes
   `znactime.__main__.main()`; PyInstaller needs a script path, not a console-entry-point
   string such as `znactime.__main__:main`. Set the spec's `pathex` to the repository root
   so the launcher under `packaging/` can resolve `znactime` without an editable install.
5. Extend the release-tree allowlist and its tests for these exact reviewed inputs,
   including `.github/workflows/`. Preserve rejection of databases, backups, credentials,
   and unrelated files. Generated output belongs under `build/` and `dist/` only.

### 6.2 — Project metadata, entry point, version, and icons

1. Add `pyproject.toml` and define the GUI entry point:

   ```toml
   [project.gui-scripts]
   znactime = "znactime.__main__:main"
   ```

   `znactime/__main__.py` already exposes `main()`; retain and test that function rather
   than creating a second launcher. `tracker.py` may remain only as a compatibility entry
   point and must not be used by packaged builds.
2. Keep one editable source asset and provide release-ready `icon.icns` for macOS,
   `icon.ico` for Windows, and `icon.png` for Linux. Include the current Qt PNG/theme
   assets in the bundle, and fail the build if a required asset is absent.
3. Keep `znactime.config.VERSION` as the application version source. The spec and installer
   scripts must import or receive that value; the Git tag, About/title text, bundle
   metadata, installer metadata, and all artifact names must match it.
4. The artifact must include third-party license notices and must exclude real/test user
   data, credentials, caches, local settings, and developer paths.

### 6.3 — Native build matrix and supported-system policy

Use four explicit jobs, all checking out the same commit. The labels and architectures
below are available on standard
[GitHub-hosted runners](https://docs.github.com/en/actions/reference/runners/github-hosted-runners).
Avoid `*-latest` so an alias migration does not silently change the build baseline.

| Target / lock name | `runs-on` | setup-python architecture | First release package |
|---|---|---|---|
| `windows-x64` | `windows-2022` | `x64` | `znacTime-<VERSION>-windows-x64-Setup.exe` |
| `linux-x64` | `ubuntu-22.04` | `x64` | `znactime_<VERSION>_amd64.deb` and `znacTime-<VERSION>-linux-x86_64.AppImage` |
| `macos-arm64` | `macos-15` | `arm64` | `znacTime-<VERSION>-macos-arm64.dmg` |
| `macos-x64` | `macos-15-intel` | `x64` | `znacTime-<VERSION>-macos-x86_64.dmg` |

Initial acceptance targets: Windows 11 x64, Ubuntu Desktop 22.04 and 24.04 x64, and
macOS 15 on both architectures. Test the AppImage additionally on a named, supported
Fedora release and record that version before claiming Fedora support. Windows/Linux
ARM64 and older macOS releases are outside this first acceptance matrix.

The pinned PySide6 6.11.1 release provides Windows x64, Linux x86_64 wheels tagged
`manylinux_2_34`, and macOS `13_0_universal2` wheels. These tags establish dependency
constraints, not proof that the final application supports every matching system. Verify
the full resolution, including Essentials, Addons, Shiboken, and Pillow, on each runner.
See [PySide6 wheel metadata](https://pypi.org/project/PySide6/6.11.1/#files) and
[Essentials wheel metadata](https://pypi.org/project/PySide6-Essentials/6.11.1/#files).

Build Linux on the oldest supported Ubuntu baseline: PyInstaller does not bundle glibc,
and an AppImage cannot erase a newer build's glibc requirement. If the dependencies stop
working on 22.04, review the dependency or supported-OS policy explicitly; do not silently
switch to `ubuntu-latest`. See
[PyInstaller's Linux compatibility guidance](https://pyinstaller.org/en/stable/usage.html#making-gnu-linux-apps-forward-compatible).

Use the PyInstaller PySide6 hooks for Qt libraries/plugins, plus explicit collection of
the app's PNG and theme JSON files and any reportlab/Pillow resources the smoke tests show
are needed. Do not indiscriminately collect every Qt module. Verify the native platform
plugin (`windows`, `cocoa`, `xcb` and any supported Wayland plugin), image loading, fonts,
themes, SQLite, and PDF export in the frozen application. A passing headless test does
not establish that the desktop platform plugin can load.

### 6.4 — macOS package, signing, and notarization

1. Produce `dist/znacTime.app` with a stable bundle identifier and explicit native target
   architecture (`arm64` or `x86_64`). Publish separate DMGs initially. A later universal2
   build requires a universal2 Python and every collected native dependency to contain
   both slices; a universal2 PySide6 wheel alone is insufficient. See
   [PyInstaller macOS architecture support](https://pyinstaller.org/en/stable/feature-notes.html#macos-multi-arch-support).
2. In the trusted release job, import a Developer ID Application certificate into a
   temporary keychain. Sign collected code from the inside out using PyInstaller's signing
   support and reviewed entitlements, with Hardened Runtime and timestamping. Verify the
   complete app; do not use `codesign --deep` as a substitute for correct signing order.
3. Archive the signed app with `ditto`, submit that ZIP using `xcrun notarytool submit
   ... --wait`, require an Accepted result, and staple/validate the `.app` ticket.
4. Use the runner's `hdiutil` to create a DMG containing the stapled app and an Applications
   shortcut. Sign the DMG, submit it for notarization, then staple/validate the DMG ticket.
   This gives both the copied app and the download container offline tickets. No bundle
   content changes are permitted after signing. Hash the final stapled DMG.
5. Check `codesign --verify --deep --strict`, `xcrun stapler validate`, and Gatekeeper
   assessment. Rehearse Finder launch of a quarantined download, app-local data access,
   exports, and same-identity upgrade on both architectures. See
   [Apple's automated notarization workflow](https://developer.apple.com/documentation/security/customizing-the-notarization-workflow).

### 6.5 — Windows package and installer

1. Produce the one-directory `dist/znacTime/znacTime.exe` bundle; the installer must include
   the whole directory, including PyInstaller's runtime subdirectory. This avoids one-file
   extraction at each launch.
2. Compile the checked-in `.iss` with a pinned Inno Setup `ISCC.exe`. Use a stable `AppId`,
   `PrivilegesRequired=lowest`, a per-user application directory, Start-menu shortcut,
   version metadata, and uninstall entry. Do not install or delete user data. See
   [Inno Setup's privilege setting](https://jrsoftware.org/ishelp/topic_setup_privilegesrequired.htm).
3. Choose and validate unattended signing before enabling signed releases: use a
   cloud/HSM-backed Authenticode provider supported from an ephemeral Windows runner.
   A certificate requiring a locally attached USB token cannot simply be uploaded as a
   GitHub secret. Prefer provider-supported OIDC; otherwise scope provider credentials
   to the release signing job.
4. Sign and timestamp the application before compiling the installer; configure signing
   for the generated uninstaller, then sign/timestamp the final Setup EXE. Verify signatures
   with SignTool. Signing identifies the publisher but does not guarantee a warning-free
   first download; EV certificates no longer automatically bypass SmartScreen. See
   [Microsoft's SmartScreen guidance](https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/smartscreen-reputation).
5. Test silent install/uninstall in CI and Start-menu launch, upgrade, data preservation,
   PDF export, and recovery on a clean Windows 11 system. A Windows Server build runner
   is not a substitute for the supported desktop acceptance test.

### 6.6 — Linux package

1. Produce one PyInstaller one-directory bundle on `ubuntu-22.04`; use it as input for both
   the Ubuntu installer and portable Linux download.
2. **Ubuntu native package:** stage the bundle under `/opt/znactime/`, an executable launcher
   under `/usr/bin/znactime`, and desktop/icon files under `/usr/share/`. Add reviewed
   `DEBIAN/control` metadata (`Package: znactime`, `Architecture: amd64`, mapped version,
   description, maintainer, and runtime dependencies). Build with
   `dpkg-deb --build --root-owner-group`. Install with `sudo apt install ./<package>.deb`
   so declared system dependencies resolve. Package install/removal must not create or
   erase per-user databases. See the
   [Ubuntu dpkg-deb manual](https://manpages.ubuntu.com/manpages/jammy/man1/dpkg-deb.1.html).
3. **AppImage:** stage an AppDir containing the same bundle, executable `AppRun`, desktop
   file, and icon; package it with a version/checksum-pinned `appimagetool`. Account for
   executable modes and Qt plugin paths. If additional native-library deployment is
   necessary, review it explicitly rather than running two independent Qt bundlers.
4. Inspect unresolved shared libraries and derive `.deb` runtime dependencies from the
   shipped binaries and Qt plugins, then validate on clean 22.04 and 24.04 installations.
   CI must provision Xvfb and required X11/xcb, xkbcommon, font, and GL libraries. See
   [Qt's Linux platform-plugin requirements](https://doc.qt.io/qt-6/linux-requirements.html).
5. Exercise the actual `xcb` plugin with `xvfb-run -a` in CI. Test desktop launch under
   X11 and Ubuntu's Wayland session (document whether this uses native Wayland or XWayland).
   Test AppImage mounting with FUSE on a desktop; use `--appimage-extract-and-run` when
   runner FUSE support is unavailable. The latter does not verify FUSE mounting. Document
   `chmod +x` and the fallback in release instructions. See
   [AppImage FUSE guidance](https://docs.appimage.org/user-guide/troubleshooting/fuse.html).
6. Both formats must write only to the Phase 6.0 locations. Publish SHA-256 checksums and
   a detached signature of the Linux checksum manifest using a protected release key;
   document how to verify it. GitHub Release assets are direct downloads, not an APT
   repository. APT repository signing, RPM, Flatpak, and automatic updates are later work.

### 6.7 — CI/CD with GitHub Actions

Implement in two stages: first prove all four unsigned package builds, then enable trusted
tag signing and draft release creation. Phase 6.0 verifies existing storage behavior
in those packages; no new database-location migration is required.

#### Workflow events and job boundaries

| Workflow/event | Work | Publication and credentials |
|---|---|---|
| `ci.yml`: `pull_request`, default-branch pushes | Four native test jobs; package smoke builds after packaging inputs exist | Read-only token; no signing secrets |
| `ci.yml`: `workflow_dispatch` | Manually exercise the same four candidate builds | Unsigned CI downloads only; macOS may use ad-hoc signing for execution |
| `release.yml`: push of `v*` tag | Validate tag, build/test all targets, platform signing/notarization, test final packages, aggregate | Trusted tag jobs only; create a draft GitHub Release after every target passes |

Protect release tags against unauthorized creation/movement, require their commit to be
on the reviewed release branch, and restrict signing environments to those tags. Use
`pull_request`, never a privileged `pull_request_target` checkout to run contributor code.
Keep default `permissions: contents: read`; grant `contents: write` only to the final
release job and `id-token: write` only where a chosen signing provider needs OIDC.
Pin actions to reviewed full commit SHAs in production. See
[GitHub's workflow security guidance](https://docs.github.com/en/actions/reference/security/secure-use).

Use the following **design skeleton for the unsigned build stage**. Referenced scripts,
lockfiles, and Python-version file are planned deliverables, not existing commands. Action
major tags are shown for readability; resolve them to reviewed SHAs before activation.
The same build logic should be shared by both workflows without granting CI signing access.

```yaml
name: Native package candidates
on:
  pull_request:
  workflow_dispatch:
permissions:
  contents: read
jobs:
  package:
    strategy:
      fail-fast: false
      matrix:
        include:
          - {target: windows-x64, os: windows-2022, arch: x64}
          - {target: linux-x64, os: ubuntu-22.04, arch: x64}
          - {target: macos-arm64, os: macos-15, arch: arm64}
          - {target: macos-x64, os: macos-15-intel, arch: x64}
    runs-on: ${{ matrix.os }}
    timeout-minutes: 45
    steps:
      - uses: actions/checkout@v7
        with:
          persist-credentials: false
      - uses: actions/setup-python@v7
        with:
          python-version-file: packaging/python-version.txt
          architecture: ${{ matrix.arch }}
      - run: python scripts/prepare_native_tools.py --target ${{ matrix.target }}
      - run: python -m pip install --require-hashes --only-binary=:all: -r requirements/locks/${{ matrix.target }}.txt -r requirements/build/${{ matrix.target }}.txt
      - run: python -m pip check
      - run: python scripts/check_release_tree.py
      - run: python -m unittest discover -s tests -v
        env:
          QT_QPA_PLATFORM: offscreen
      - run: python scripts/build_native.py --target ${{ matrix.target }} --mode unsigned
      - run: python scripts/smoke_native.py --target ${{ matrix.target }}
      - uses: actions/upload-artifact@v7
        with:
          name: candidate-${{ matrix.target }}-${{ github.run_id }}-${{ github.run_attempt }}
          path: dist/release/*
          if-no-files-found: error
          retention-days: 14
          compression-level: 0
```

`setup-python` supports selecting the interpreter/architecture; `upload-artifact` requires
distinct matrix artifact names and does not preserve Unix file modes in its default
archive. Upload completed DMG/EXE/DEB/AppImage files, not a loose `.app` or AppDir; use a
tar archive if transferring an unpackaged bundle. Restore the executable bit before
testing a downloaded AppImage. See [setup-python](https://github.com/actions/setup-python)
and [upload-artifact](https://github.com/actions/upload-artifact).

#### Shared script contracts and frozen-app verification

- `prepare_native_tools.py`: install/locate the pinned native packaging tools; verify
  downloaded checksums; provision Ubuntu runtime/Xvfb prerequisites and log tool versions.
  Use explicit platform subprocesses with checked exit codes. Do not rely on incidental
  preinstalled runner software or a shell syntax shared across PowerShell and Bash.
- `build_native.py`: validate host architecture and version, call
  `python -m PyInstaller --clean --noconfirm znactime.spec`, then the platform packager.
  Accept explicit `unsigned` or `release` mode. Release mode must fail if required signing
  credentials or notarization are missing; never silently fall back to unsigned output.
  Write only final packages, checksums, notices, and per-target build manifests to
  `dist/release/`; manifests include commit, version, target, tools, and dependency locks.
- `smoke_native.py`: install/extract/mount the produced package, start its **bundled
  executable**, and require a bounded successful exit plus a machine-readable report.
  Add a diagnostic `--smoke-test --data-dir <temporary-path> --report <path>` mode to the
  existing launcher, handled before normal first-launch dialogs. Restrict the data override
  to this diagnostic mode. It must instantiate the Qt window, render assets/themes,
  create/edit/reopen a synthetic SQLite record, and export a PDF without user interaction.
  Run outside the checkout from an unrelated working directory with no `PYTHONPATH`,
  external Qt plugin path, or development-environment library fallback. On Linux use Xvfb
  with `QT_QPA_PLATFORM=xcb`; on Windows/macOS use their native platform backend.
- Keep automated package checks separate from clean desktop acceptance. Hosted runners
  include Python and developer tools; they cannot prove independence from those tools or
  successful Finder/Start-menu integration. Record clean-VM/manual results for every
  supported platform and architecture, including upgrade and migration tests from 6.8.

#### Trusted release sequence and artifact promotion

1. Trigger from `push.tags: ['v*']`; a validation job rejects malformed tags and mismatches
   with `znactime.config.VERSION`, resolves the tag to a commit, and checks release-branch
   ancestry. All downstream jobs check out that resolved commit. For initial releases use
   `vX.Y.Z`; if prerelease suffixes are added later, define explicit Windows numeric and
   Debian/macOS metadata mappings rather than claiming all formats accept the same string.
2. Run the four native jobs with `fail-fast: false`. Each tests, builds, signs/packages,
   verifies signatures, and smoke-tests the final package. Give only relevant platform
   jobs their signing environments. Do not inject Apple/Windows credentials into Linux
   or contributor builds. Set longer bounded timeouts for notarization and serialize
   release attempts for the same tag with `cancel-in-progress: false`.
3. Apple prerequisites: Developer ID membership/certificate, certificate password, signing
   identity, and a notarization App Store Connect API key/issuer/key ID (or documented
   Apple-ID credentials). Import into an ephemeral keychain; clean the keychain and key
   files in an `always()` cleanup step. Windows prerequisites: the chosen hosted signing
   account/identity and its GitHub authentication configuration. Linux prerequisites:
   checksum-signing identity and published verification key. Keep material in scoped
   GitHub environment secrets or the provider, never in artifacts or logs.
4. Generate package SHA-256 checksums **after** all signing, notarization, and stapling.
   Upload uniquely named artifacts and record their IDs. The aggregate job must
   `needs` all platform jobs, download artifacts from this run, require all five expected
   packages, verify checksums and consistent commit/version, and reject missing/duplicate
   assets. Do not publish a partial release when one platform fails.
5. Create a **draft** GitHub Release for the already-existing tag using `gh release create`
   with `--verify-tag --draft`, attaching the exact packages, checksums/signatures, manifests,
   notices, and release notes. Use the job's `GITHUB_TOKEN` as `GH_TOKEN`; no personal token
   is needed for same-repository release uploads. Fail on an unexpected existing release
   instead of overwriting reviewed assets. See
   [GitHub CLI release creation](https://cli.github.com/manual/gh_release_create).
6. Perform clean-machine acceptance on these final downloads and compare their checksums
   with the build record. Publish the existing draft after sign-off; do not rebuild or
   retag a `-rc` binary as a different final version. If a change is needed, create a new
   version/tag and candidate. Preserve the previous release for executable rollback.

Standard hosted runners are available for public and private repositories; public standard
runner usage is free, while private usage consumes the account's allowance and may incur
charges. Confirm the repository's Actions permissions, available minutes/artifact storage,
and signing-account access before activation. GitHub hosting does not supply signing
identities. See the [hosted-runner reference](https://docs.github.com/en/actions/reference/runners/github-hosted-runners).

### 6.8 — Distribution checklist and definition of done

- [ ] Frozen/source launches and same-identity upgrades find the existing Qt-resolved
      database and preferences. All database-related writes stay outside the bundle;
      exports/backups remain user-selected.
- [ ] Runtime and build dependencies are pinned, and `znactime.spec` builds from a clean
      environment on every target operating system.
- [ ] All four GitHub-hosted jobs pass with reviewed platform locks and native tooling;
      the expanded release-tree and dependency-lock checks pass.
- [ ] Each artifact launches on a clean OS installation with no Python or developer tools.
- [ ] The existing automated suite passes on all targets. Packaged acceptance verifies
      edits persist to SQLite, timer start/pause/resume/stop and restart recovery,
      carry-over, controlled close/reopen, CSV v3/PDF export, backup, themes, and validation.
- [ ] First launch handles create-new, legacy CSV import, an existing SQLite database,
      interrupted migration, and corrupt-database recovery without silent data loss.
- [ ] Migration rehearsal preserves open/closed months, per-day values, carry-over,
      schedule history, year-boundary data, import logs, and recovery evidence.
- [ ] macOS `.dmg` artifacts are signed, notarized, stapled, and open without a Gatekeeper
      override on every supported architecture.
- [ ] The signed Windows installer creates a Start-menu shortcut, upgrades cleanly, and
      uninstalls without deleting user data.
- [ ] The Ubuntu `.deb` installs/upgrades/removes successfully on 22.04 and 24.04 without
      deleting user data; its desktop entry launches the bundled executable.
- [ ] The Linux AppImage passes Ubuntu 22.04/24.04 and the recorded Fedora acceptance
      target, including FUSE and extract-and-run checks, with no writes inside its image.
- [ ] PDF export and month close/reopen work in every frozen artifact, with all required
      reportlab, Pillow, Qt plugin, icon, and theme resources bundled.
- [ ] The About/title version, package metadata, release tag, installer metadata, artifact
      filenames, and checksums agree on all three platforms.
- [ ] Artifacts contain required third-party notices and no user data, credentials, test
      fixtures, local settings, caches, or developer paths.
- [ ] Release notes state the user-data/export locations, backup and recovery procedure,
      known limitations, and standard SQLite (non-app-encrypted) storage model.
- [ ] The exact release candidate tested is the artifact published, and the previous
      supported artifact remains available for executable rollback without deleting or
      downgrading user data.
- [ ] Signing/notarization failures, a failed platform job, missing assets, and mismatched
      versions/checksums block release creation; contributor workflows have no signing access.

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
