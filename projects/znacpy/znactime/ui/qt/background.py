from __future__ import annotations

import threading

from PySide6.QtCore import QObject, QThread, Signal, Slot
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QProgressBar,
    QVBoxLayout,
)


class _TaskWorker(QObject):
    progress = Signal(str, int, int)
    succeeded = Signal(object)
    failed = Signal(object)

    def __init__(self, task):
        super().__init__()
        self._task = task
        self._cancelled = threading.Event()

    def cancel(self):
        self._cancelled.set()

    @Slot()
    def run(self):
        try:
            result = self._task(
                progress=self.progress.emit,
                cancelled=self._cancelled.is_set,
            )
        except Exception as error:
            self.failed.emit(error)
            return
        self.succeeded.emit(result)


class _TaskDialog(QDialog):
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self._running = True
        self.result_value = None
        self.error = None

        self.status = QLabel("Starting…", self)
        self.progress = QProgressBar(self)
        self.progress.setRange(0, 0)
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        self.cancel_button = self.buttons.button(
            QDialogButtonBox.StandardButton.Cancel
        )

        layout = QVBoxLayout(self)
        layout.addWidget(self.status)
        layout.addWidget(self.progress)
        layout.addWidget(self.buttons)

    @Slot(str, int, int)
    def update_progress(self, phase: str, completed: int, total: int):
        self.status.setText(phase)
        if total > 0:
            self.progress.setRange(0, total)
            self.progress.setValue(min(completed, total))
        else:
            self.progress.setRange(0, 0)

    @Slot(object)
    def complete(self, result):
        self.result_value = result
        self._running = False
        super().accept()

    @Slot(object)
    def fail(self, error):
        self.error = error
        self._running = False
        super().reject()

    def request_cancel(self, cancel):
        if not self._running:
            return
        cancel()
        self.cancel_button.setEnabled(False)
        self.status.setText("Cancelling…")
        self.progress.setRange(0, 0)

    def reject(self):
        if self._running:
            self.cancel_button.click()
            return
        super().reject()

    def closeEvent(self, event):
        if self._running:
            self.cancel_button.click()
            event.ignore()
            return
        super().closeEvent(event)


def run_background_task(parent, title: str, task):
    """Run task(progress=..., cancelled=...) while a modal Qt dialog stays responsive."""
    dialog = _TaskDialog(title, parent)
    thread = QThread()
    worker = _TaskWorker(task)
    worker.moveToThread(thread)

    thread.started.connect(worker.run)
    worker.progress.connect(dialog.update_progress)
    worker.succeeded.connect(dialog.complete)
    worker.failed.connect(dialog.fail)
    worker.succeeded.connect(worker.deleteLater)
    worker.failed.connect(worker.deleteLater)
    worker.succeeded.connect(thread.quit)
    worker.failed.connect(thread.quit)
    dialog.cancel_button.clicked.connect(
        lambda: dialog.request_cancel(worker.cancel)
    )

    thread.start()
    dialog.exec()
    thread.quit()
    thread.wait()

    if dialog.error is not None:
        raise dialog.error
    return dialog.result_value
