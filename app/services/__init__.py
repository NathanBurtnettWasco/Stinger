"""
Services layer for Stinger.

Contains:
- State machine for test workflow
- Test execution logic
- UI bridge for communication
"""
from __future__ import annotations

from typing import Any, Callable, Optional

from PyQt6.QtCore import QObject, QRunnable, QThreadPool, pyqtSignal


class _WorkerSignals(QObject):
    finished = pyqtSignal(object, object)


class _Worker(QRunnable):
    def __init__(self, fn: Callable[[], Any]) -> None:
        super().__init__()
        self._fn = fn
        self.signals = _WorkerSignals()

    def run(self) -> None:
        try:
            result = self._fn()
            error: Optional[Exception] = None
        except Exception as exc:
            result = None
            error = exc
        self.signals.finished.emit(result, error)


def run_async(fn: Callable[[], Any], callback: Callable[[Any, Optional[Exception]], None]) -> _Worker:
    worker = _Worker(fn)
    worker.signals.finished.connect(callback)
    QThreadPool.globalInstance().start(worker)
    return worker
