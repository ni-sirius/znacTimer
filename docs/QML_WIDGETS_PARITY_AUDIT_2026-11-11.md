# QML / Qt Widgets feature-parity and architecture audit

Date: 2026-11-11. Scope: `projects/znacpy`, current working tree, including the
pre-existing local QML/layout/theme/test changes. This is an audit, not a parity
fix. All runtime checks used temporary SQLite databases and isolated settings.
No personal records were opened or changed.

## Assessment

**QML has broad domain-feature coverage, but does not yet have interaction
parity with Widgets.** Two reproduced defects can write to a different field or
day than the one the user was editing. The reported badge-click behavior is
also a confirmed regression, already specified by the Widgets regression suite.

The shared calculation/model/repository implementation is a strong foundation.
The main architectural gaps are uncoordinated edit sessions, competing selection
state, and modal editors addressed by row number rather than durable day identity.
Passing the current tests does not establish parity for those interactions.

## Sources and interpretation

- [Functional requirements](architecture/FUNCTIONAL_REQUIREMENTS.md): FR-001
  through FR-071; current domain, persistence, lifecycle, and menu requirements.
- [QML migration plan](qml-migration-plan.md): preservation goals, keyboard and
  accessibility expectations, retained startup Widgets dialogs, acceptance checks.
- [Current architecture contract](projects/znacpy/MIGRATION_PLAN.md#current-architecture-and-storage-contract)
  and [SQLite design boundaries](projects/znacpy/SQLITE_MIGRATION_PLAN.md#enforced-architecture-rules).
  Historical schema/CSV/no-reopen instructions are superseded by the functional
  requirements and current implementation, as the migration plan itself explains.
- The retained Widgets implementation and its tests define established behavior
  where the written requirements do not describe interactions precisely.
- [Navigation investigation](qml-navigation-performance.md): presentation-update
  history; existing measurements are not a direct Widgets/QML performance comparison.

P1 means a defect that can persist data to an unintended destination. P2 means
a material functional or keyboard regression. P3 means a smaller usability gap.
Runtime observations below are distinguished from source-confirmed differences.

## Findings, in priority order

### F01 — P1: An open interruption dialog can save into the wrong month

**Reproduced.** The dialog retains only `editRow` and `editColumn`. At midnight,
`ApplicationController.tick()` changes the selected month. Save subsequently
calls `editCell()` against that new month's model using the old row number.

Reproduction: create October 1 and November 1, 2026 with `08:00–17:00` and a
30-minute interruption. At simulated October 31, 23:59, open October row 0's
advanced interruption editor and change the duration to `00:45`. Advance the
controller clock to November 1, 00:00, call `tick()`, then Save. October remains
30 minutes; **November becomes 45 minutes**.

Sources: [InterruptionEditor.qml](../projects/znacpy/znactime/ui/quick/qml/InterruptionEditor.qml),
lines 8, 22–26, 53–56;
[controller.py](../projects/znacpy/znactime/ui/quick/controller.py), lines 221–234.
The Widgets interruption editor is attached to a model index and is disposed
with its view reset; the persistent QML modal editor introduces this extra path.

Required change: bind an edit session to the original work date, field, and
revision. A context change must either finish/cancel the session explicitly or
reject Save and require reopening. Never reinterpret an old row in a new model.
Repository revision checks cannot detect this particular mistake: the UI submits
a write to the wrong day using that day's current model record.

### F02 — P1: Tab advances the editor, but paste still targets the previous cell

**Reproduced.** Qt's edit navigation changes `selectionModel.currentIndex`, while
`selectedRow`/`selectedColumn` remain unchanged. Copy, paste, Delete, and custom
arrow handling read those separate properties.

Reproduction: set Start=`08:00`, End=`17:00`; edit Start, press Tab, then Enter.
The actual current column is End (`3`), but `selectedColumn` remains Start (`2`).
Copy produces `08:00`. Paste `09:30` changes **Start to `09:30`**, leaving End
at `17:00`.

Sources: [MonthTable.qml](../projects/znacpy/znactime/ui/quick/qml/MonthTable.qml),
lines 16–19, 34–43, 142–165, 369–375. Widgets
`MonthTableView.copy_selection()` / `paste_selection()` use the view's actual
selection/current index (`ui/qt/table.py`, lines 1822–1856).

Required change: make the Qt current index and selection model authoritative.
Synchronize all navigation, clipboard operations, and edit completion with it;
remove independent coordinates that can become stale.

### F03 — P2: Clicking another badge finishes one edit and opens another

**Reproduced; matches the user's report.** Start draft `09:15` is committed when
End is clicked, but End immediately opens its own editor. The same occurs when
leaving an interruption editor. Clicking the workday badge also routes straight
into another table editor.

Widgets explicitly consumes the click that finishes an existing badge edit,
including its release, across table and player views. A subsequent click may
open the new editor. Its tests also protect Enter completion, clicks on ordinary
buttons, and rapid subsequent clicks from leaving a stale suppression flag.

Sources: [badge_edit.py](../projects/znacpy/znactime/ui/qt/badge_edit.py),
`_BadgeEditSession.eventFilter()`;
[test_badge_click_editing.py](../projects/znacpy/tests/test_badge_click_editing.py),
tests beginning at lines 124, 134, 151, 178, 190;
[MonthTable.qml](../projects/znacpy/znactime/ui/quick/qml/MonthTable.qml), lines
45–60, 200–205, 291, 320. QML has no corresponding session coordinator.

Required change: coordinate every badge activation at pointer press time, before
focus changes can hide the prior session. Consume only the gesture that ends
that session. Keep both interruption inputs in one session and preserve the
ordinary button action when a button finishes an edit.

### F04 — P2: Modifier clicks edit instead of preserving selection

**Reproduced.** Ctrl-click on a time badge opens an editor. Shift-click on another
badge opens an editor and replaces the anchor with the clicked cell, losing the
intended rectangular range. Disjoint Ctrl selections and mouse-drag range
selection are not implemented by these QML input paths.

`CellBadge.clicked()` carries no pointer modifiers; its handlers unconditionally
call `selectCell(..., false)` and edit. The cell-wide fallback checks Shift but
does not exclude Ctrl. `selectCell()` only sets the current index with
`ItemSelectionModel.NoUpdate`; it does not actually select a range. A keyboard
Shift-right range copies correctly through the custom anchor properties, but
the Qt selection model still reports `hasSelection == false`.

Sources: [CellBadge.qml](../projects/znacpy/znactime/ui/quick/qml/CellBadge.qml),
lines 14, 52–58; [MonthTable.qml](../projects/znacpy/znactime/ui/quick/qml/MonthTable.qml),
lines 34–43, 200–205, 291, 320. Widgets enables `ExtendedSelection` in
`ui/qt/table.py`, lines 1873–1874, and tests Ctrl-click at
`test_badge_click_editing.py:202`.

Required change: propagate pointer modifiers, preserve the selection anchor,
and use real Qt range selection. Centralize modifier and edit-session rules so
badges and the cell background cannot disagree.

### F05 — P2: Typing into a selected cell no longer starts editing

**Reproduced.** Select an editable Start cell without leaving an editor open,
then press `9`: focus stays on `monthTable`; no editor opens. Widgets enables
`AnyKeyPressed` as well as `EditKeyPressed`. QML enables only `EditKeyPressed`
and handles Enter/F2 explicitly, with no printable-key path.

Sources: `ui/qt/badge_edit.py:69–72`;
`ui/quick/qml/MonthTable.qml:117,142–169`.

Required change: restore typing-to-edit and verify that the initiating character
replaces the selected text correctly. Closed/read-only cells must remain protected.

### F06 — P2: Established time-input behavior was not migrated

**Source-confirmed; blank default also reproduced.** Widgets pre-fills an unset
Start/End editor with the current local `HH:MM` and selects it. QML opens an
empty field. The one-click-then-Enter workflow therefore no longer records the
current time.

Widgets also filters inline clock and interruption start/end inputs to digits
and colons. QML's corresponding `TextField`s have no validator. Persistence
validation still rejects invalid values, so this is an input-behavior regression,
not evidence that invalid times reach SQLite.

Sources: `ui/qt/table.py:346–350,1300–1325`;
`ui/quick/qml/MonthTable.qml:377–389`;
`ui/quick/qml/InlineInterruptionEditor.qml:42–71`.
Existing Widgets tests:
`test_all_time_editors_accept_only_digits_and_colons` and
`test_time_editor_paste_rejects_other_characters_and_day_editor_keeps_text`
in `tests/test_qt_model_interruption.py`.

Required change: use a shared clock-input component, with the existing lexical
filter and unset-time default. Keep free text in Special day and keep semantic
time/range validation in Python.

### F07 — P2: Menu action mnemonics are missing

**Source-confirmed direct requirement gap.** FR-070 requires mnemonic access keys
for every menu and submenu action where supported. QML supplies `&` only in
top-level menu titles; all child action texts lack mnemonics. Widgets defines
them for Import, exports, backup, Exit, approvals, settings, and About.

Sources: `ui/quick/qml/Main.qml:64–97`; `ui/qt/menu.py:27–72`;
`tests/test_menu.py::MenuBarTest.test_menu_mnemonics_and_platform_quit_shortcut`.

FR-071 also requires both the platform-standard Quit binding and portable Ctrl+Q.
QML declares only `StandardKey.Quit`; Widgets explicitly includes the portable
fallback. Treat the missing explicit fallback as a portability/coverage gap;
this audit does not claim the shortcut failed on every platform.

Required change: restore per-action mnemonic markers and verify actual keyboard
activation through the custom menu delegates, plus native and portable Quit keys.

### F08 — P3: Several information interactions are missing

**Source-confirmed.** Completed interruption badges in Widgets expose
`period duration / total pause duration` on hover, including closed-month
periods. QML receives `total_pause_time` through the model but never renders a
corresponding tooltip.

The Widgets date-problem indicator can be clicked and opened with
Enter/Space. Its carry-over information button also supports click and Space.
QML substitutes hover-only tooltips; its date indicator is a `Rectangle`, and
the carry-over information icon is a `Label`. Full-date hover text on the Date
cell is also absent from the QML bindings.

Sources: `ui/qt/table.py:805–811,1079–1128,1684–1700`;
`ui/qt/header.py:84–96`; `ui/quick/qml/MonthTable.qml:258–275,307–321`;
`ui/quick/qml/MonthHeader.qml:97–104`.
Widgets tooltip tests live at `tests/test_qt_model_interruption.py:965–1064`
and `tests/test_qt_header.py:98–130`.

Required change: restore duration tooltips and actionable information controls
with keyboard and accessibility actions. Accessible descriptions alone do not
preserve these keyboard interactions.

### F09 — P3: The workday badge edits a distant table cell instead of itself

**Reproduced.** Clicking the footer badge opens `specialCellEditor` in today's
table row and scrolls there. In the probe the editor was at scene Y=519.5 while
the clicked badge was at Y=693. Widgets edits the footer badge in place using a
proxy over the same source day. The QML `Rectangle` badge also has no equivalent
focusable view or keyboard activation handler.

Sources: `ui/quick/qml/Main.qml:122–130`;
`ui/quick/qml/MonthTable.qml:60`;
`ui/quick/qml/WorkdayBar.qml:29–43`; `ui/qt/day_badge.py:17–107`.

Required change: restore an editor hosted by the footer badge, sharing day
identity and the edit-session coordinator with the table. If relocation is an
intentional product change, document and explicitly accept that divergence.

### F10 — P3: Opening the current month does not ensure today is visible

**Source-confirmed and reproduced for current-month navigation.** Widgets calls
`ensure_today_visible()` after a loaded month's geometry update. QML emits its
scroll-to-today signal only from the explicit Today action; normal month loads
and startup have no equivalent.

Probe: simulated November 30, 2026, window height 500, navigate to November.
The table stayed at `contentY=0` with viewport height 232 and content height
1020; today's final row was outside the viewport. The explicit Today action
does scroll correctly.

Sources: `ui/qt/table.py:1571–1600,1910–1924`;
`ui/quick/controller.py:158–171,207–217`;
`ui/quick/qml/Main.qml:251`.

Required change: position today's row after a current-month load/initial layout.
Preserve the user's scroll position during ordinary edits and resizing.

## Requirements coverage

These are coverage assessments, not a claim that every FR was individually
re-executed through both frontends.

| Requirement / capability | Assessment | Evidence or gap |
|---|---|---|
| FR-001–006, FR-065: calculations and frozen results | Shared implementation; existing regression coverage | QML reuses `MonthTableModel`, calculator, repository, CSV export. |
| FR-007: non-persisted expected end | Covered by shared model and QML/controller checks | `test_edits_persist_and_expected_end_is_never_saved`; QML expected outlines bind the shared badge role. |
| FR-008–022: schedules | Shared repository; QML save/conflict tests present | `test_schedule_changes_update_expected_time_and_persist_setting`, `test_schedule_snapshot_rejects_concurrent_change`. |
| FR-023–030: virtual months / materialization | Shared repository/model; navigation and persistence tests present | `test_navigation_is_read_only_and_crosses_years`, `test_edits_persist_and_expected_end_is_never_saved`. |
| FR-031–035, FR-066: classifications, colors, invalid ranges | Shared model/repository; QML validation checks present | No separate calculation or persistence write path in QML. Editor lexical/default behavior still differs: F06. |
| FR-036–044: import and CSV export | Operations present; shared storage | QML controller tests cover workers, import merge, export and destination protection. See shared documentation gap below. |
| FR-045–056: close/reopen/carry | Implemented; shared repository plus QML/controller tests | Close/reopen confirmations, stale close snapshots, carry/discontinuity bindings retained. No native Mac validation in this audit. |
| FR-057–058: stale writes / identity | Repository checks retained; frontend destination handling incomplete | Existing stale-write tests pass, but F01/F02 bypass the user's intended destination rather than SQLite validation. |
| FR-059–061: timer and timestamps | Shared repository; controller transition/elapsed/rollover tests present | Start, pause, resume, stop, replacement confirmation, and worker thread ownership retained. |
| FR-062–064: upgrades / recovery | Intentionally shared startup path | Retaining Widgets recovery dialogs is explicitly allowed by the QML plan. |
| FR-067–069: menu order and Data commands | Commands present; order retained | QML supplies handlers for all five Data actions. FR-069's constructor contract remains specific to the Widgets class. |
| FR-070 | Missing in QML | F07. |
| FR-071 | Incomplete explicit parity / platform verification | F07; platform-specific binding check remains necessary. |
| Clipboard | Present, with material gaps | F02/F04. QML rejects an entire destination range containing read-only/out-of-bounds cells; Widgets skips those cells. This stricter paste policy is a behavior change requiring a decision, not automatically a defect. |
| Appearance, settings, sizing, dialogs | Implemented with existing QML tests | Theme switching, startup keys, resizing, movable modal hosts, Save/Cancel/Escape/native close, chained confirmations, shutdown. |
| Native macOS behavior | Not verified by this Windows audit | Native menus, shortcuts, rendering, file dialogs and packaging need Mac checks, as already stated in the migration plan. |

The README says import completion links to its normalization report, but neither
main-window completion implementation examined here includes the report path in
its completion message (`ui/qt/app.py:1092`, `ui/quick/controller.py:516`). The
storage report is still generated. This is an inherited documentation/UX gap,
not a newly missing QML feature.

## Architecture review

1. **Keep the domain/storage reuse.** `QuickMonthModel(MonthTableModel)` preserves
   repository validation, revisions, special-day schedule resolution, expected-end
   presentation, immutable snapshots, and calculations. There is no reason to
   redesign SQLite or duplicate the domain model for this parity work.
2. **Add explicit interaction ownership.** Use one edit-session coordinator shared
   by table badges, interruption inputs, footer badge, and modal editors. It should
   own target identity, draft, commit/cancel, and the pointer gesture that dismisses
   a session. Derive current cell/ranges from `QItemSelectionModel`. F01–F04 show
   why row integers and independent QML flags are insufficient.
3. **Extract shared presentation code from Widgets modules.**
   `ui/quick/layout.py:5–11` imports constants and private `_date_fonts` /
   `_interruption_badge_rows` from the actual Widgets table implementation.
   Shared model, colors, mapper, settings, and layout contracts belong in neutral
   UI modules. Existing startup recovery dialogs can remain Widgets. This is a
   maintainability concern, not a claim that all Widgets dependencies violate the
   accepted migration design.
4. **Clarify repository composition and enforce the documented boundary.**
   `ui/quick/controller.py:21,471,508` directly constructs `SQLiteRepository` in
   workers, as the old application also does. This contradicts the strict
   protocol-only UI rule in the SQLite design. Inject a worker repository factory
   from composition/startup, or document a narrow composition exception. Preserve
   worker-owned connections. The existing boundary test at
   `tests/test_sqlite_repository.py:2213` checks driver imports and selected old
   files, not the promised complete UI-to-storage import boundary.
5. **Reduce duplicated application workflows.** Navigation, timer display,
   schedules, close/reopen, imports, backups, and exports exist independently in
   `ui/qt/app.py` and `ui/quick/controller.py`. Extract reusable application actions
   incrementally and have both frontends adapt them. Preserve explicit confirmation
   decisions and stable errors. A wholesale UI rewrite would add unnecessary risk.
6. **Use one clock and neutral parsers in presentation logic.** QML interruption
   editors manually split and rebuild semicolon/hyphen strings; Python already
   owns their semantics and persistence validation. Structured period data and
   shared operations reduce divergence. They also make durable edit targets and
   rollover tests easier to express.

## Requirements and test changes needed

The functional requirements document is strong on storage/domain behavior but
does not explicitly capture most badge and keyboard contracts, and its ownership
and test references still point predominantly to Widgets. Add atomic UI
requirements and trace each to both adapters:

- UI-P001: A badge gesture during another active edit finishes that session and
  does not open the clicked badge; the next independent gesture may open it.
- UI-P002: Both interruption inputs share one session; Enter, Escape, button
  clicks, and rapid subsequent clicks do not leave stale click suppression.
- UI-P003: Ctrl/Shift clicks and drag gestures change selection without beginning
  an edit; clipboard operations use the actual current cell/range after Tab.
- UI-P004: Edit sessions retain their original work date, field, and revision
  across refreshes and clock changes; stale or changed context cannot retarget Save.
- UI-P005: Printable-key editing, unset-time defaults, and lexical time filtering
  retain their established behavior; closed months stay read-only.
- UI-P006: Information controls and menus retain keyboard activation and the
  period/total/full-date information currently exposed by Widgets.
- UI-P007: The workday badge edits in place and shares edit exclusion with the table.
- UI-P008: Loading the current month reveals today; edits/resizes preserve scroll.

Prioritize F01/F02 before expanding visual work, then port the full existing
`BadgeClickEditingTest` behavior set to real QML pointer events. Use shared
scenario data/assertions with frontend-specific drivers. Controller-only tests
and direct QML function invocation cannot prove pointer/focus/keyboard parity.
Add actual keyboard paths for opening and saving the advanced editor, including
month rollover while it is visible. Exercise both theme modes, read-only months,
and normal/minimum window sizes for the affected interactions.

## Verification record

- Focused existing suite: **57 tests passed** (`tests.test_quick_ui`,
  `tests.test_quick_controller`, `tests.test_badge_click_editing`).
- Additional isolated audit probes: **17 observations completed without harness
  failures**, covering badge switch, non-editable-cell click, Ctrl/Shift clicks,
  printable keys, footer editor location, interruption switching, normal timer
  refresh, Tab commit/current-index drift, range copy, button completion, rollover,
  current-month scrolling, wrong-target paste, and empty-clock defaults.
  These probes record behavior; an OK harness result does **not** mean parity passed.
- Reproduced positive controls: a normal same-day `tick()` preserved the draft;
  clicking Today or the primary workday button committed the draft. The audit
  therefore does not report a general focus-loss/draft-loss defect.
- Full regression suite: **507 tests run in 226.305 seconds, 2 skipped, no
  failures**. The existing suite therefore passes despite the reproduced gaps.
- `git diff --check` passed. The pre-existing tracked modifications were preserved;
  the only new reviewable source-tree artifact is this report.

Commands from `projects/znacpy`:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_quick_ui tests.test_quick_controller tests.test_badge_click_editing -q
.\.venv\Scripts\python.exe -m unittest discover -s tests -q
.\.venv\Scripts\python.exe build/qml-parity-audit/probe.py
```

The audit probe is a local build artifact at `projects/znacpy/build/qml-parity-audit/probe.py`;
it reuses the existing QML test harness and is outside normal test discovery.
Manual reproduction steps and source references above remain in this report.
No application implementation files or existing tests were changed by this audit.

## Remediation tracking

The assessment above records the original audit. Subsequent fixes are tracked here.

| Finding | Status | Regression coverage |
|---|---|---|
| F01 | Fixed | Modal rollover and reloaded revision rejection; FR-072. |
| F02 | Fixed | Tab followed by copy, paste, and Delete uses the actual current cell; FR-073. |
| F03 | Fixed | Shared pointer-press edit exclusion across badges and interruption fields; FR-074. |
| F04 | Fixed | Ctrl/Shift and drag selections use the Qt selection model without editing; FR-075. |
| F05 | Fixed | Printable-key editing preserves initiating and subsequent characters; FR-076. |
| F06 | Fixed | Shared lexical clock filter and injected-clock defaults, including packaged component; FR-077. |
| F07 | Fixed | Action mnemonics and deduplicated native/portable Quit bindings; FR-070/071. |
| F08 | Fixed | Shared period/total tooltips, full-date hover, and pointer/keyboard/accessibility information controls; FR-078/079. |
| F09 | Fixed | Footer hosts its own keyboard-accessible revision-bound editor and shares edit exclusion; FR-080. |
| F10 | Fixed | Today revealed after startup/month layout; edit and resize scroll preservation; FR-081. |

Post-remediation verification: **524 tests run, 2 skipped, no failures**
(248.673 seconds), including 17 added regression tests. Three additional isolated
checks passed for rapid subsequent badge clicks, Ctrl+Enter opening the advanced
editor, and footer editing across month rollover. Light/dark dashboard previews
were generated and inspected; the source release allowlist and whitespace checks
passed. Preview artifacts are under `projects/znacpy/build/qml-parity-fixes/`.
No release executable was rebuilt, and native macOS checks remain outstanding.
