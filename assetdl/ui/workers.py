"""Background work without freezing the window."""

from __future__ import annotations

import traceback

from PySide6.QtCore import QObject, QRunnable, Signal


class Signals(QObject):
    done = Signal(object)
    failed = Signal(str)
    progress = Signal(object)


class Task(QRunnable):
    """Runs ``fn(report, *args)``; ``report(x)`` emits ``progress``. Result -> ``done``."""

    def __init__(self, fn, *args):
        super().__init__()
        self.fn, self.args = fn, args
        self.signals = Signals()
        self.setAutoDelete(True)

    def run(self):
        def safe(signal, *args):
            try:
                signal.emit(*args)
            except RuntimeError:          # the window closed while this was running: nobody to tell
                pass

        try:
            result = self.fn(lambda x: safe(self.signals.progress, x), *self.args)
        except RuntimeError as exc:
            if "deleted" in str(exc):
                return
            traceback.print_exc()
            safe(self.signals.failed, str(exc))
        except Exception as exc:              # noqa: BLE001
            traceback.print_exc()
            safe(self.signals.failed, str(exc) or type(exc).__name__)
        else:
            safe(self.signals.done, result)
