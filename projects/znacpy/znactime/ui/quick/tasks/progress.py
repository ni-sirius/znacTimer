"""Bounded worker-to-GUI progress snapshots for one background task."""

from threading import Lock


class TaskProgressBuffer:
    """Keep only the latest update without queuing a Qt event for every report."""

    def __init__(self):
        self._lock = Lock()
        self._accepting = True
        self._latest = None

    def report(self, phase: str, completed: int, total: int):
        with self._lock:
            if self._accepting:
                self._latest = (phase, completed, total)

    def take(self):
        with self._lock:
            latest, self._latest = self._latest, None
            return latest

    def finish(self):
        """Freeze the producer's final value until the GUI consumes it."""
        with self._lock:
            self._accepting = False

    def close(self):
        """Retire this task and return/clear its final pending update."""
        with self._lock:
            self._accepting = False
            latest, self._latest = self._latest, None
            return latest
