from __future__ import annotations

import threading

from PySide6.QtCore import QThreadPool, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QApplication, QDialog, QHBoxLayout, QProgressBar, QPushButton, QVBoxLayout)

from assetdl import APP_NAME, VERSION
from assetdl.assets import human_size
from assetdl.config import Settings
from assetdl import updater
from assetdl.ui import theme
from assetdl.ui.widgets import label
from assetdl.ui.workers import Task


class UpdateDialog(QDialog):
    def __init__(self, info: updater.UpdateInfo, settings: Settings, parent=None):
        super().__init__(parent)
        self.info, self.settings = info, settings
        self.stop = threading.Event()
        self.new_file = None
        self._signals = None
        self.setWindowTitle(f"{APP_NAME} - update")
        self.setObjectName("Root")
        self.setMinimumWidth(560)
        self.setStyleSheet(f"QDialog#Root {{ background: {theme.BG}; }}")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 24, 28, 20)
        lay.setSpacing(12)
        lay.addWidget(label("NEW UPDATE DETECTED", "Section"))
        lay.addWidget(label(f"Version {info.version} is out", "PageTitle"))
        lay.addWidget(label(f"Current Version: {VERSION}", "Muted"))

        self.status = label("", "Muted", wrap=True)
        lay.addWidget(self.status)
        self.bar = QProgressBar()
        self.bar.setRange(0, 1000)
        self.bar.setTextVisible(False)
        self.bar.hide()
        lay.addWidget(self.bar)

        row = QHBoxLayout()
        self.skip_btn = QPushButton("Skip this version")
        self.skip_btn.setObjectName("Flat")
        self.skip_btn.clicked.connect(self._skip)
        self.page_btn = QPushButton("Release page")
        self.page_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(info.page_url)))
        self.later_btn = QPushButton("Later")
        self.later_btn.clicked.connect(self._later)
        self.go_btn = QPushButton("Update now")
        self.go_btn.setObjectName("Primary")
        self.go_btn.setMinimumWidth(130)
        self.go_btn.clicked.connect(self._go)
        row.addWidget(self.skip_btn)
        row.addStretch(1)
        row.addWidget(self.page_btn)
        row.addWidget(self.later_btn)
        row.addWidget(self.go_btn)
        lay.addLayout(row)

        ok, why = updater.can_self_update()
        if ok and not info.asset_url:
            ok, why = False, f"This release has no {updater.asset_name_for()}; get it from the release page."
        if not ok:
            self.go_btn.setText("Download page")
            self.go_btn.clicked.disconnect()
            self.go_btn.clicked.connect(lambda: (QDesktopServices.openUrl(QUrl(info.page_url)), self.accept()))
            self.page_btn.hide()
            self.status.setText(why)
        elif info.size:
            self.status.setText(f"Download: {human_size(info.size)}. The app restarts when it's done.")

    def _skip(self):
        self.settings.skipped_version = self.info.version
        self.settings.save()
        self.reject()

    def _later(self):
        self.stop.set()
        self.reject()

    def _go(self):
        if self.new_file is not None:
            self._install()
            return
        for b in (self.go_btn, self.skip_btn, self.page_btn):
            b.setEnabled(False)
        self.later_btn.setText("Cancel")
        self.bar.show()
        self.status.setText("Downloading …")
        task = Task(lambda report: updater.download(self.info, lambda d, t: report((d, t)), self.stop))
        task.signals.progress.connect(self._progress)
        task.signals.done.connect(self._downloaded)
        task.signals.failed.connect(self._failed)
        self._signals = task.signals
        QThreadPool.globalInstance().start(task)

    def _progress(self, dt):
        done, total = dt
        self.bar.setValue(int(1000 * done / total) if total else 0)
        self.status.setText(f"Downloading … {human_size(done)}" + (f" of {human_size(total)}" if total else ""))

    def _downloaded(self, path):
        self.new_file = path
        self.bar.setValue(1000)
        self._install()

    def _install(self):
        try:
            exe = updater.install(self.new_file)
        except Exception as exc:
            self._failed(f"couldn't replace the program: {exc}")
            return
        self.status.setText(f"Updated to {self.info.version}. Restarting …")
        try:
            updater.restart(exe)
        except Exception as exc:
            self.status.setText(f"Updated to {self.info.version}. Start the app again to use it ({exc}).")
            self.go_btn.setText("Close")
            self.go_btn.setEnabled(True)
            self.go_btn.clicked.disconnect()
            self.go_btn.clicked.connect(QApplication.quit)
            return
        QTimer.singleShot(300, QApplication.quit)

    def _failed(self, err: str):
        if self.stop.is_set():
            return
        self.bar.hide()
        self.status.setText(f"The update failed: {err}")
        self.status.setStyleSheet(f"color: {theme.ERR};")
        self.later_btn.setText("Close")
        for b in (self.go_btn, self.skip_btn, self.page_btn):
            b.setEnabled(True)
        self.new_file = None
        self.go_btn.setText("Try again")
