# Desktop QML migration

## Objective

Make Qt Quick/QML the default UI for `projects/znacpy`, with one shared interface
on Windows and macOS. Preserve the Python domain calculations, SQLite schema,
existing data location, settings namespace, optimistic concurrency checks, and
explicit confirmations for destructive or overwriting operations.

## Implementation sequence

1. Expose the existing SQLite-backed month model to QML. Add named roles for
   display, editing, badges, day status, expected end time, and accessibility.
   Route validation and persistence failures through an injectable notification
   handler so QML does not depend on table widgets.
2. Add a QObject application controller for month navigation, balances, date
   rollover, workday start/pause/resume/stop, close/reopen previews and
   confirmations, work schedules, appearance, clipboard, import/export, and
   backup. Keep repository revision checks and protected export destinations.
   Run long imports and backups in cancellable worker threads.
3. Build the shared QML window, menu, month header, editable calendar table,
   interruption editor, workday bar, settings, notifications, confirmations,
   file pickers, and task progress. Support keyboard navigation, copy/paste,
   light/dark/system appearance, and startup sizing. Use a shared surface
   component as the future integration point for native macOS glass.
4. Switch the normal launcher to the QML window. Keep the established native
   startup/recovery dialogs, which run before the main window, and retain the
   Widgets implementation for regression comparison. No schema or dependency
   update is required: PySide6 6.11.1 already includes Qt Quick.
5. Bundle QML sources and Qt Quick plugins, exercise the real QML engine in the
   isolated packaged smoke test, document the new architecture, and run the
   existing regression suite plus controller and QML interaction tests.

## Acceptance checks

- The normal entry point creates a QML application window with the complete
  month view and persists edits across repository reopen.
- Existing stored data and work schedules require no conversion.
- Invalid edits, stale revisions, closed months, future month closure, and unsafe
  export destinations retain their existing safeguards.
- Workday actions, interruption periods/durations, expected end display,
  close/reopen, schedules, CSV/PDF export, legacy import, and backups remain usable.
- Real QML components load without engine errors in offscreen integration tests;
  light/dark appearance, editing, navigation, and dialogs are exercised.
- Packaging includes QML assets and smoke diagnostics verify the QML runtime.
- Windows checks run locally. Native macOS rendering, menus, file dialogs, and
  packaging require the existing macOS CI job and a Mac visual pass.

## Native glass boundary

Translucent QML surfaces are not Apple's native Liquid Glass. This migration
creates the common QML interface and a styling boundary; a native AppKit bridge
can be added there after testing on macOS 26. It does not claim to ship or verify
native Liquid Glass from the Windows development environment.

## Validation record

Implemented on 2026-10-16. All five implementation steps above are complete.

- Full regression suite: **491 tests run, 2 skipped, no failures**. This includes
  21 new controller tests and 10 real QML interaction tests.
- QML checks exercise mouse/keyboard time editing, Escape cancellation,
  interruption periods, special days, settings, light/dark/system themes,
  navigation, resizing, notifications, and chained close/reopen confirmations.
- Controller checks cover saved data, stale edits and close previews, workday
  transitions, elapsed time, expected end time, rollover, schedules, clipboard,
  protected destinations, CSV/PDF exports, threaded backups, legacy imports,
  and cancellation.
- Normal application startup/event-loop/shutdown checked with an isolated
  temporary database: exit code 0.
- Windows x64 PyInstaller executable built successfully, including QML sources
  and Qt Quick plugins. Final isolated packaged smoke test: exit code 0; all
  isolation, Qt, SQLite, themes, QML, and PDF checks passed.
- Local build: `projects/znacpy/build/qml-validation/dist/znacTime/znacTime.exe`.
  Smoke report: `projects/znacpy/build/qml-validation/smoke-report-final.json`.
- README screenshots regenerated from the actual QML UI using synthetic records
  and isolated preferences; dashboard, interruption editor, and closed-month
  renders inspected. The screenshot generator no longer uses the Widgets UI.
- Existing JSON theme files also supply QML colors. Release source allowlist and
  whitespace checks pass. Database schema and dependency pins are unchanged.

Remaining platform validation: run macOS CI and review native menus, file dialogs,
and rendering on a Mac. Native Apple Liquid Glass is a separate enhancement as
described above. Existing startup/recovery dialogs and the regression Widgets
frontend remain in the source tree intentionally.

## Styling parity follow-up

The QML presentation now follows the current Widgets implementation:

- Year, Month, and Today at the left of the compact header; carry-over and the
  outlined month action with an open/closed lock at the right.
- Original 2:2:1:1:2:1:1 column weights, font-based row heights, nine-pixel week
  gaps at 1x scaling, stacked date/weekday labels, and calendar week at the right
  of the Date cell. QML reuses the Widgets presentation measurements and badge
  wrapping helpers through `ui/quick/layout.py`.
- Shared badge color and contrast calculations for both frontends, full-width
  Special day badges, separate interruption chips, expected-end outlines, date
  gradients, current-day rules, table header colors, scrollbar, and shadow.
- Compact workday status, editable day badge, purple primary control, and pink
  Stop day control in their original positions.
- Rounded period controls, menus, dialog buttons, and inputs; settings navigation
  at the left and separate hours/minutes controls for work schedules.
- Inline Special day and interruption editing. The advanced interruption dialog
  remains available with Ctrl+Enter.

Validation: 493 tests run, 2 skipped, no failures. Real pointer and keyboard edits,
inline period editing, header order, column proportions, and settings Save buttons
checked. Light/dark screenshots compared with a rendered Widgets reference using
the same font and window dimensions; README screenshots regenerated accordingly.
The final 12 QML interaction checks also passed after the last control-state and
small-window adjustments. The refreshed Windows executable passed all isolated
packaged smoke checks; report: `projects/znacpy/build/qml-validation/style-smoke-report.json`.

## QML shutdown follow-up

The QML engine is now destroyed synchronously during shutdown, while the Python
controller and month model are still alive. Previously, `deleteLater()` could
remain pending after the application event loop stopped, leaving bindings alive
as their controller was released. Shutdown is idempotent and also cleans up an
engine whose root component failed to load.

Regression checks cover shutdown with the interruption editor open and shutdown
after the event loop has stopped. UI tests and the packaged smoke check now
include warnings emitted during teardown. Validation: 495 tests run, 2 skipped,
no failures; release source allowlist and whitespace checks pass.
The rebuilt Windows executable passed all packaged smoke checks with empty
stderr; report: `projects/znacpy/build/qml-validation/shutdown-smoke-report.json`.

## Menu and badge sizing follow-up

Custom menu popups now retain a 200-pixel minimum width and grow to fit their
widest action. The custom background had removed Fusion's implicit minimum,
leaving a 12-pixel popup containing only its padding.

Time and interruption badges now use the larger of their planned width and
their rendered text width plus padding. This includes bold glyph overhangs that
can exceed the Python font advance measurement by a pixel and cause elision.

Validation: 497 tests run, 2 skipped, no failures. Regression checks open every
menu, click a menu action, and verify complete time/period labels at normal and
minimum window widths using real fonts. Light/dark menu and badge previews were
reviewed in `projects/znacpy/build/qml-sizing-light` and `qml-sizing-dark`.
The sizing checks also pass at 125% display scaling. The rebuilt Windows
executable passed every packaged smoke check with empty stderr; report:
`projects/znacpy/build/qml-validation/sizing-smoke-report.json`.

## Movable dialog windows follow-up

Settings, the cell editor, notifications, confirmations, task progress, and
About now share `AppDialog.qml`. Each keeps its QML content and standard button
handling inside a separate `ApplicationWindow` with `Qt.Dialog` flags, an OS
title bar and close button, and a transient relationship to the main window.
Application modality matches the original Widgets dialogs; this also avoids
requesting attached sheets on macOS. Qt documents the window flags and transient
parent behavior in [Window](https://doc.qt.io/qt-6/qml-qtquick-window.html), and
application modality in [QDialog](https://doc.qt.io/qt-6/qdialog.html#modal-prop).

Dialogs are positioned once on opening and constrained to the owner's screen.
UI updates do not reset a moved window's position. Native close uses the same
rejection path as Cancel and Escape; the progress window requests cancellation
and stays present until the worker finishes. Hiding the main window also hides
its dialogs, so they cannot keep the application alive after exit.

Validation: 501 tests run, 2 skipped, no failures. The 20 QML interaction checks
cover native frame flags, separate modal hosts, independent positioning, Save,
Cancel, Escape, title-bar close, task cancellation, dropdown keyboard selection,
confirmation chaining, and shutdown with a dialog open. Light/dark client content
previews were reviewed in `projects/znacpy/build/qml-dialog-windows`. Native macOS
window decoration and dragging still require validation on a Mac.

The rebuilt Windows executable passed every packaged smoke check with empty
stderr; report: `projects/znacpy/build/qml-validation/dialog-windows-smoke-report.json`.

## Interaction parity fixes — 2026-11-11

The ten behavioral findings in the
[QML / Widgets parity audit](QML_WIDGETS_PARITY_AUDIT_2026-11-11.md) were addressed
in separate commits, with regression coverage and requirement traceability.
Modal edits retain day identity and revision. The Qt selection model supplies
the current cell and selected ranges, including after Tab, Ctrl/Shift clicks,
and dragging. A shared edit session consumes the badge gesture that finishes an
existing edit, and the workday badge now edits in place through that same session.

Printable-key editing, current-time defaults, lexical clock filtering, action
mnemonics, native/portable Quit bindings, interruption duration tooltips, and
keyboard-accessible information controls are restored. Current-month loads reveal
today after layout while ordinary edits and resizing preserve scroll position.
Shared tooltip formatting lives outside the frontend-specific packages. New
clock and information components are included in the packaging asset list.

FR-070/071 now trace both frontends; FR-072–081 document the interaction contracts.
Native macOS validation remains a platform follow-up. These source changes do
not imply a rebuilt release executable or removal of the retained Widgets UI.

Validation: **524 tests run, 2 skipped, no failures**, including 17 added
regression tests. Additional rapid-click, advanced-editor keyboard, and footer
rollover checks passed. Light/dark previews were generated and dashboard renders
reviewed in `projects/znacpy/build/qml-parity-fixes/`. The release-source allowlist
and whitespace checks passed.

## Tooltip appearance follow-up

Time information, pause durations, dates, and header/footer hints now share
`AppToolTip.qml`. It uses the theme's panel surface, text, and border colors with
10-pixel corners and wrapped plain text. Opening fades and scales in over
140 ms; closing fades out over 90 ms. The shared component is included in the
packaging asset list. Runtime checks cover both themes, animation completion,
long-message wrapping, and repeated closing. Light/dark popup previews were
reviewed under `projects/znacpy/build/qml-tooltip-style/`.

Validation: 68 QML interaction and packaging tests passed. The release-source
allowlist and whitespace checks passed.

Hover tooltips now wait 500 ms before opening. Leaving the target cancels the
pending display; explicit click, keyboard, and accessibility activation remains
immediate. The shared timer applies to time, pause, date, and header/footer hints.
Three targeted QML interaction checks passed for delay/cancellation, immediate
activation, and the existing theme/animation behavior.

## Blank pause drafts

Closing an inline pause editor with both endpoints blank now discards the draft
without warning or database writes. This also preserves an existing duration or
period when both fields are cleared. The advanced editor skips empty period rows
and blank duration drafts; saving unchanged pauses does not increment revisions.
Explicit Remove actions still delete pauses, while partially entered invalid
pauses still show validation messages. A start without an end remains a valid
active pause.

Validation: all 47 QML interaction tests passed, including four new regression
tests covering blank drafts, unchanged persisted revisions, partial input, and
explicit removal. Whitespace checks passed.
