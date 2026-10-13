"""Run blocking work off the UI thread with progress + cancellation.

    task = run_task(do_scan, on_result=..., on_error=..., on_progress=...)
    task.cancel()

The worker callable receives a ``TaskHandle`` as its first argument and should call
``handle.progress(frac, text)`` and check ``handle.cancelled`` periodically.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

log = logging.getLogger(__name__)


class _Signals(QObject):
    progress = Signal(float, str)
    result = Signal(object)
    error = Signal(object)
    finished = Signal()


@dataclass
class TaskHandle:
    _signals: _Signals
    _cancelled: bool = False

    def progress(self, frac: float, text: str = "") -> None:
        self._signals.progress.emit(max(0.0, min(1.0, frac)), text)

    @property
    def cancelled(self) -> bool:
        return self._cancelled

    def raise_if_cancelled(self) -> None:
        if self._cancelled:
            raise TaskCancelled()


class TaskCancelled(Exception):
    pass


class _Worker(QRunnable):
    def __init__(self, fn, args, kwargs, handle: TaskHandle):
        super().__init__()
        self._fn, self._args, self._kwargs, self._handle = fn, args, kwargs, handle

    def run(self) -> None:
        sig = self._handle._signals
        try:
            result = self._fn(self._handle, *self._args, **self._kwargs)
            if not self._handle.cancelled:
                sig.result.emit(result)
        except TaskCancelled:
            pass
        except Exception as e:  # noqa: BLE001 - surfaced to on_error
            log.exception("task failed")
            sig.error.emit(e)
        finally:
            sig.finished.emit()


class Task:
    def __init__(self, handle: TaskHandle, worker: _Worker):
        self._handle = handle
        self._worker = worker

    def cancel(self) -> None:
        self._handle._cancelled = True

    @property
    def cancelled(self) -> bool:
        return self._handle.cancelled


def run_task(
    fn: Callable[..., Any],
    *args,
    on_result: Callable[[Any], None] | None = None,
    on_error: Callable[[Exception], None] | None = None,
    on_progress: Callable[[float, str], None] | None = None,
    on_finished: Callable[[], None] | None = None,
    pool: QThreadPool | None = None,
    **kwargs,
) -> Task:
    signals = _Signals()
    if on_result:
        signals.result.connect(on_result)
    if on_error:
        signals.error.connect(on_error)
    if on_progress:
        signals.progress.connect(on_progress)
    if on_finished:
        signals.finished.connect(on_finished)
    handle = TaskHandle(signals)
    worker = _Worker(fn, args, kwargs, handle)
    (pool or QThreadPool.globalInstance()).start(worker)
    return Task(handle, worker)
