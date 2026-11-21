"""Run one background operation while publishing its state on the GUI thread."""

from PySide6.QtCore import QObject, Property, QThread, QTimer, Signal, Slot

from znactime.ui.qt.background import _TaskWorker
from znactime.ui.quick.tasks.progress import TaskProgressBuffer


class TaskRunner(QObject):
    """Own task threads and progress; callers handle results and error policy.

    Call start/cancel/shutdown from the GUI thread. Tasks receive only the
    thread-safe progress callback and the worker's cooperative cancellation
    check. Successful results and failures are delivered on the GUI thread.
    """

    busyChanged = Signal()
    progressChanged = Signal()
    failed = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._thread = None
        self._worker = None
        self._success = None
        self._busy = False
        self._progress = {"title": "", "phase": "", "completed": 0, "total": 0}
        self._shutting_down = False
        self._progress_buffer = None
        self._progress_timer = QTimer(self)
        self._progress_timer.setInterval(100)
        self._progress_timer.timeout.connect(self._flush_progress)

    @Property(bool, notify=busyChanged)
    def busy(self):
        return self._busy

    @Property("QVariantMap", notify=progressChanged)
    def progress(self):
        return dict(self._progress)

    def start(self, title, task, success):
        """Start task(progress=..., cancelled=...); reject overlapping work.

        The success callback runs after the thread has stopped, final progress
        is published, and busy is cleared. Failures emit failed(error) instead.
        """
        if self._busy or self._shutting_down:
            return False
        if self._thread is not None:
            self._thread.wait()
            self._thread.deleteLater()
        progress_buffer = TaskProgressBuffer()

        def run_task(*, progress, cancelled):
            try:
                return task(progress=progress_buffer.report, cancelled=cancelled)
            finally:
                progress_buffer.finish()

        thread = QThread(self)
        worker = _TaskWorker(run_task)
        self._thread, self._worker, self._success = thread, worker, success
        self._progress_buffer = progress_buffer
        self._busy = True
        self._progress = {"title": title, "phase": "Starting…", "completed": 0, "total": 0}
        thread.started.connect(worker.run)
        worker.succeeded.connect(self._task_done)
        worker.failed.connect(self._task_failed)
        self._progress_timer.start()
        self.progressChanged.emit()
        self.busyChanged.emit()
        if self._shutting_down:
            # A start-state observer closed the owner before work began. The
            # worker still belongs to the GUI thread, so dispose it here.
            worker.deleteLater()
            thread.deleteLater()
            self._thread = self._worker = None
            self._busy = False
            self.busyChanged.emit()
            return False
        # Publish the initial UI before starting storage work, as before the
        # extraction. Delaying affinity transfer also makes early shutdown safe.
        worker.moveToThread(thread)
        thread.finished.connect(worker.deleteLater)
        thread.start()
        return True

    @Slot()
    def _flush_progress(self):
        if self._progress_buffer is not None:
            update = self._progress_buffer.take()
            if update is not None:
                self._publish_progress(*update)

    def _stop_progress(self, *, flush):
        self._progress_timer.stop()
        progress_buffer, self._progress_buffer = self._progress_buffer, None
        if progress_buffer is not None:
            update = progress_buffer.close()
            if flush and update is not None:
                self._publish_progress(*update)

    def _publish_progress(self, phase, completed, total):
        self._progress.update(phase=phase, completed=completed, total=total)
        self.progressChanged.emit()

    def _finish_task(self):
        self._thread.quit()
        self._thread.wait()
        self._worker = None
        self._stop_progress(flush=not self._shutting_down)
        self._busy = False
        # Capture the old callback before observers can start another task.
        success, self._success = self._success, None
        self.busyChanged.emit()
        return success

    @Slot(object)
    def _task_done(self, result):
        if self._shutting_down:
            return
        success = self._finish_task()
        if success and not self._shutting_down:
            success(result)

    @Slot(object)
    def _task_failed(self, error):
        if self._shutting_down:
            return
        self._finish_task()
        if not self._shutting_down:
            self.failed.emit(error)

    @Slot()
    def cancel(self):
        if self._worker is not None:
            self._worker.cancel()
            self._stop_progress(flush=False)
            if self._progress["phase"] != "Cancelling…":
                self._progress["phase"] = "Cancelling…"
                self.progressChanged.emit()

    def shutdown(self):
        if self._shutting_down:
            return
        self._shutting_down = True
        self._stop_progress(flush=False)
        self.cancel()
        self._success = None
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait()
        self._worker = None
        self._busy = False
