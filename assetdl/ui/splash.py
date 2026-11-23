"""Start-up splash, in the style of the CSR2 Workshop one: the CSR2 logo with ASSETS under it,
a thin red progress bar with what it's doing, and the credits along the bottom
(assets/csr2_logo.png, bonk_logo.png, nitro4csr.png)."""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import QApplication, QLabel, QProgressBar, QVBoxLayout, QWidget, QHBoxLayout

from assetdl import AUTHOR, VERSION
from assetdl.config import resource
from assetdl.ui import theme
from assetdl.ui.widgets import credit


class Wordmark(QWidget):
    """assets/brand.png: the CSR2 logo with ASSETS spanning its width (a drawn one if it's missing)."""

    HEIGHT = 172

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(self.HEIGHT)
        logo = resource("brand.png")
        self.pixmap = QPixmap(str(logo)) if logo.exists() else None
        if self.pixmap is not None and self.pixmap.isNull():
            self.pixmap = None

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        r = self.rect()
        if self.pixmap is not None:
            ratio = self.devicePixelRatioF()
            scaled = self.pixmap.scaledToHeight(int(self.HEIGHT * ratio), Qt.SmoothTransformation)
            scaled.setDevicePixelRatio(ratio)
            p.drawPixmap(int((r.width() - scaled.width() / ratio) / 2), 0, scaled)
            return
        big = QFont(theme.FONT, 54, QFont.Black)
        big.setItalic(True)
        big.setLetterSpacing(QFont.AbsoluteSpacing, -1)
        p.setFont(big)
        p.setPen(QColor(theme.TEXT))
        p.drawText(QRectF(0, 0, r.width(), 100), Qt.AlignHCenter | Qt.AlignBottom, "CSR2")
        # red underline stroke
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(theme.ACCENT))
        stroke = QPainterPath()
        cx = r.width() / 2
        stroke.addRoundedRect(QRectF(cx - 90, 106, 180, 4), 2, 2)
        p.drawPath(stroke)
        small = QFont(theme.FONT, 13, QFont.Bold)
        small.setLetterSpacing(QFont.AbsoluteSpacing, 9)
        p.setFont(small)
        p.setPen(QColor(theme.ACCENT_TEXT))
        p.drawText(QRectF(0, 116, r.width(), 30), Qt.AlignHCenter | Qt.AlignVCenter, "ASSETS")


class Splash(QWidget):
    W, H = 580, 370

    def __init__(self):
        super().__init__(None, Qt.SplashScreen | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(self.W, self.H)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(36, 30, 36, 22)
        lay.setSpacing(0)
        lay.addStretch(1)
        lay.addWidget(Wordmark(self))
        lay.addStretch(1)

        self.status = QLabel("Starting")
        self.status.setStyleSheet(f"color: {theme.MUTED}; font-size: 9pt;")
        lay.addWidget(self.status)
        lay.addSpacing(8)
        self.bar = QProgressBar()
        self.bar.setRange(0, 1000)
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(4)
        lay.addWidget(self.bar)
        lay.addSpacing(18)

        foot = QHBoxLayout()
        made = credit("bonk_logo.png", f"made by <b>{AUTHOR}</b>", 22)
        thanks = credit("nitro4csr.png", "Special thanks to <b>Nitro4CSR</b>", 22)
        ver = QLabel(f"v{VERSION}")
        ver.setStyleSheet(f"color: {theme.MUTED}; font-size: 8pt;")
        foot.addWidget(made)
        foot.addStretch(1)
        foot.addWidget(thanks)
        foot.addStretch(1)
        foot.addWidget(ver)
        lay.addLayout(foot)

        screen = QApplication.primaryScreen().availableGeometry()
        self.move(screen.center().x() - self.W // 2, screen.center().y() - self.H // 2)
        self._anim = None

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 16, 16)
        p.fillPath(path, QColor("#0d0d0d"))
        p.setPen(QColor(theme.BORDER))
        p.drawPath(path)
        # faint red glow at the top edge
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(theme.ACCENT))
        p.drawRoundedRect(QRectF(self.W / 2 - 60, 0, 120, 3), 1.5, 1.5)

    def set_progress(self, text: str, fraction: float):
        self.status.setText(text)
        self.bar.setValue(int(max(0.0, min(1.0, fraction)) * 1000))

    def fade_in(self):
        self.setWindowOpacity(0.0)
        self.show()
        self._fade(0.0, 1.0, 220)

    def fade_out(self, then=None):
        anim = self._fade(1.0, 0.0, 220)
        anim.finished.connect(self.close)
        if then:
            # Not straight from the animation's signal: ``then`` may open a dialog with its own event
            # loop, and Qt's animations can't run while one animation's callback is still in progress.
            anim.finished.connect(lambda: QTimer.singleShot(0, then))

    def _fade(self, start, end, ms):
        self._anim = QPropertyAnimation(self, b"windowOpacity", self)
        self._anim.setDuration(ms)
        self._anim.setStartValue(start)
        self._anim.setEndValue(end)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.start()
        return self._anim
