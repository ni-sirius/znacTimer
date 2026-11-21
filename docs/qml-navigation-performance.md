# QML month navigation investigation

Measured on Windows with Python 3.12 / PySide6 6.11.1 on 2026-10-27.

The delay came primarily from presentation updates. A month load notified QML
three times: after reading metadata, during recalculation, and after loading.
The model also reset before calculation and then refreshed every cell again.
Each cell instantiated hidden date text, font metrics, gradients, and
interruption repeaters, including columns where those items could never appear.
This adds QML object creation and binding work to the shared Widgets model.

The controller now emits one state update after loading calculated rows. The
model publishes those rows in one reset, and date / interruption components load
only in their respective columns. Edits, theme changes, and conflict reloads keep
their existing notification paths.

## Local profile

Fresh temporary SQLite database and settings; show the QML window, wait 100 ms,
then select February 2024, June 2024, December 2025, and January 2024. Time each
`selectMonth()` plus `QApplication.processEvents()` with `time.perf_counter()`
while `cProfile` is enabled. Both runs used the native platform and default
window dimensions. This measures local event processing, not input-to-display
latency or a direct Widgets comparison; profiler overhead is included.

| Measurement | Before fixes | After navigation fix |
| --- | ---: | ---: |
| Individual switches | 582–761 ms | 176–193 ms |
| Four switches, total | 2.74 s | 0.75 s |
| Controller state reads | 264 | 88 |
| Model role reads | 15,265 | 7,635 |
| Month layout calculations | 12 | 4 |

The measured total improved approximately 3.6 times. Database reads were not
the dominant cost in this fixture. Results for populated databases and different
graphics drivers should be measured separately if navigation remains slow.
