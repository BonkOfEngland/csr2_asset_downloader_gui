from __future__ import annotations

import sys
import time

from PySide6.QtCore import QThreadPool, QTimer
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import QApplication

from assetdl import APP_NAME, VERSION
from assetdl.config import Settings, resource
from assetdl.ui import theme

SPLASH_MIN_SECONDS = 1.4


def main() -> int:
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(f"BonkOfEngland.{APP_NAME}")
        except Exception:
            pass
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(VERSION)
    app.setStyle("Fusion")
    app.setFont(QFont(theme.FONT, 10))
    app.setStyleSheet(theme.QSS)
    for name in ("icon.ico", "icon.png"):
        if resource(name).exists():
            app.setWindowIcon(QIcon(str(resource(name))))
            break

    from assetdl.session import open_session
    from assetdl.ui.main_window import MainWindow
    from assetdl.ui.setup import SetupDialog
    from assetdl.ui.splash import Splash
    from assetdl.ui.workers import Task

    from assetdl import updater
    try:
        updater.cleanup()
    except Exception:
        pass

    settings = Settings.load()
    splash = Splash()
    splash.fade_in()
    started = time.monotonic()
    state = {}

    def open_main(session):
        window = MainWindow(settings, session)
        state["window"] = window
        window.show()

    def after_splash():
        if not settings.setup_done:
            if SetupDialog(settings).exec() != SetupDialog.Accepted:
                app.quit()
                return
            open_main(None)
        else:
            open_main(state.get("session"))

    def finish(session=None):
        state["session"] = session
        wait = max(0, SPLASH_MIN_SECONDS - (time.monotonic() - started))
        QTimer.singleShot(int(wait * 1000), lambda: splash.fade_out(then=after_splash))

    if settings.setup_done:
        splash.set_progress("Starting", 0.02)
        task = Task(lambda report: open_session(settings, lambda t, f: report((t, f))))
        task.signals.progress.connect(lambda tf: splash.set_progress(*tf))
        task.signals.done.connect(finish)
        task.signals.failed.connect(lambda err: finish(None))
        state["task"] = task.signals
        QThreadPool.globalInstance().start(task)
    else:
        splash.set_progress("Welcome", 1.0)
        finish(None)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
