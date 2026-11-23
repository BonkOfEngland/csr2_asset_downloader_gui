"""Small shared widgets."""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, Qt, QTimer, Signal
from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QColor, QGuiApplication, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton,
                               QStackedWidget, QVBoxLayout, QWidget)

from assetdl.config import resource
from assetdl.ui import theme

_PIX: dict = {}


def asset_pixmap(name: str, height: int) -> QPixmap | None:
    """assets/<name> scaled to ``height`` logical pixels (sharp on high-DPI screens), or None."""
    ratio = QGuiApplication.instance().devicePixelRatio() if QGuiApplication.instance() else 1.0
    key = (name, height, ratio)
    if key not in _PIX:
        path = resource(name)
        pix = QPixmap(str(path)) if path.exists() else QPixmap()
        if pix.isNull():
            _PIX[key] = None
        else:
            pix = pix.scaledToHeight(int(height * ratio), Qt.SmoothTransformation)
            pix.setDevicePixelRatio(ratio)
            _PIX[key] = pix
    return _PIX[key]


def credit(icon: str, html: str, size: int = 18, style: str = "") -> QWidget:
    """A small round logo followed by text, e.g. the 'made by' line."""
    w = QWidget()
    lay = QHBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(6)
    pix = asset_pixmap(icon, size)
    if pix is not None:
        pic = QLabel()
        pic.setPixmap(pix)
        pic.setFixedSize(size, size)
        lay.addWidget(pic)
    text = QLabel(html)
    text.setStyleSheet(style or f"color: {theme.MUTED}; font-size: 8pt;")
    lay.addWidget(text)
    return w


def label(text: str, name: str = "", wrap: bool = False) -> QLabel:
    w = QLabel(text)
    if name:
        w.setObjectName(name)
    w.setWordWrap(wrap)
    return w


def card() -> QFrame:
    f = QFrame()
    f.setObjectName("Card")
    return f


class Choice(QPushButton):
    """A big checkable option: title, description and an example line."""

    def __init__(self, title: str, text: str, example: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("Choice")
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(4)
        t = label(title)
        t.setStyleSheet("font-size: 11pt; font-weight: 700;")
        d = label(text, "Muted", wrap=True)
        lay.addWidget(t)
        lay.addWidget(d)
        if example:
            e = label(example, "Mono")
            e.setStyleSheet(f"color: {theme.ACCENT_TEXT}; font-family: '{theme.MONO}';")
            lay.addSpacing(4)
            lay.addWidget(e)
        for w in (t, d) + ((e,) if example else ()):
            w.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setMinimumHeight(96)


class FolderPicker(QWidget):
    changed = Signal(str)

    def __init__(self, path: str = "", parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        self.edit = QLineEdit(path)
        self.edit.textChanged.connect(self.changed)
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse)
        lay.addWidget(self.edit, 1)
        lay.addWidget(browse)

    def _browse(self):
        path = QFileDialog.getExistingDirectory(self, "Where should the assets be saved?", self.edit.text())
        if path:
            self.edit.setText(path)

    def path(self) -> str:
        return self.edit.text().strip()


class Switch(QPushButton):
    """A small on/off toggle."""

    def __init__(self, checked: bool = False, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(checked)
        self.setFixedSize(42, 24)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet("QPushButton { border: none; background: transparent; padding: 0; }")

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        on = self.isChecked()
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(theme.ACCENT if on else theme.SURFACE_3))
        p.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 11, 11)
        p.setBrush(QColor("white" if on else "#9a9a9a"))
        x = self.width() - 21 if on else 3
        p.drawEllipse(x, 3, 18, 18)


class Segmented(QWidget):
    """Two or more joined toggle buttons; emits the chosen key."""

    picked = Signal(str)

    def __init__(self, options: list[tuple[str, str]], parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.buttons = {}
        n = len(options)
        for i, (key, text) in enumerate(options):
            b = QPushButton(text)
            b.setCheckable(True)
            b.setAutoExclusive(True)
            b.setCursor(Qt.PointingHandCursor)
            radius = ("border-top-left-radius: 8px; border-bottom-left-radius: 8px;" if i == 0 else "") + \
                     ("border-top-right-radius: 8px; border-bottom-right-radius: 8px;" if i == n - 1 else "")
            b.setStyleSheet(f"""
                QPushButton {{ border-radius: 0; {radius} padding: 6px 14px; background: {theme.SURFACE_2};
                               color: {theme.MUTED}; border: 1px solid {theme.BORDER}; }}
                QPushButton:checked {{ background: {theme.ACCENT}; color: white; border-color: {theme.ACCENT_HOVER}; }}""")
            b.clicked.connect(lambda _=False, k=key: self.picked.emit(k))
            lay.addWidget(b)
            self.buttons[key] = b
        if options:
            self.buttons[options[0][0]].setChecked(True)

    def set(self, key: str):
        if key in self.buttons:
            self.buttons[key].setChecked(True)


class SlideStack(QStackedWidget):
    """A stacked widget that slides the new page in sideways.

    The page switches straight away; the slide is only decoration, so if the animation can't run
    for any reason the right page is still shown (and a timer puts it in place regardless).
    """

    DURATION = 260

    def slide_to(self, index: int):
        if index == self.currentIndex() or not (0 <= index < self.count()):
            return
        running = getattr(self, "_anim", None)
        if running is not None:
            running.stop()
        direction = 1 if index > self.currentIndex() else -1
        self.setCurrentIndex(index)
        page = self.currentWidget()
        page.move(direction * self.width(), 0)
        anim = QPropertyAnimation(page, b"pos", self)
        anim.setDuration(self.DURATION)
        anim.setStartValue(QPoint(direction * self.width(), 0))
        anim.setEndValue(QPoint(0, 0))
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.start()
        self._anim = anim
        QTimer.singleShot(self.DURATION + 120, lambda p=page: p.move(0, 0) if p is self.currentWidget() else None)


def _draw_icon(kind: str, colour: str, size: int = 36) -> QPixmap:
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    p.scale(size / 24, size / 24)                 # draw on a 24x24 grid
    pen = QPen(QColor(colour), 2.0, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    if kind == "search":
        p.drawEllipse(QRectF(4, 4, 12, 12))
        p.drawLine(QPointF(14.5, 14.5), QPointF(20, 20))
    elif kind == "list":
        for y in (6, 12, 18):
            p.drawLine(QPointF(9, y), QPointF(20, y))
            p.drawPoint(QPointF(4.5, y))
    elif kind == "gear":
        import math
        p.drawEllipse(QRectF(5.5, 5.5, 13, 13))
        p.drawEllipse(QRectF(9.5, 9.5, 5, 5))
        teeth = QPen(QColor(colour), 3.0, Qt.SolidLine, Qt.FlatCap)
        p.setPen(teeth)
        for i in range(8):
            a = math.radians(i * 45)
            p.drawLine(QPointF(12 + 6.5 * math.cos(a), 12 + 6.5 * math.sin(a)),
                       QPointF(12 + 9.5 * math.cos(a), 12 + 9.5 * math.sin(a)))
    elif kind == "badge":                         # New Cars: a scalloped "new" badge with a plus
        import math
        path = QPainterPath()
        for i in range(25):
            a = math.pi * i / 12 - math.pi / 2
            r = 9.5 if i % 2 == 0 else 7.8
            pt = QPointF(12 + r * math.cos(a), 12 + r * math.sin(a))
            path.moveTo(pt) if i == 0 else path.lineTo(pt)
        p.drawPath(path)
        p.drawLine(QPointF(12, 8.5), QPointF(12, 15.5))
        p.drawLine(QPointF(8.5, 12), QPointF(15.5, 12))
    elif kind == "stack":                         # Global Libraries: stacked layers
        for dy in (0, 4.5, 9):
            path = QPainterPath()
            path.moveTo(12, 3.5 + dy)
            path.lineTo(20.5, 7.5 + dy)
            path.lineTo(12, 11.5 + dy)
            path.lineTo(3.5, 7.5 + dy)
            path.closeSubpath()
            p.drawPath(path)
    elif kind == "car":                           # Car Assets: a side-on car
        body = QPainterPath()
        body.moveTo(2.5, 16)
        body.lineTo(2.5, 12.5)
        body.quadTo(3, 11, 5.5, 10.5)
        body.lineTo(8, 7)
        body.quadTo(9, 6, 11, 6)
        body.lineTo(15, 6)
        body.quadTo(16.5, 6, 17.5, 7.5)
        body.lineTo(19.5, 10.5)
        body.quadTo(21.5, 11, 21.5, 13)
        body.lineTo(21.5, 16)
        p.drawPath(body)
        p.drawLine(QPointF(9.5, 16), QPointF(14.5, 16))
        p.drawEllipse(QRectF(5, 14, 4, 4))
        p.drawEllipse(QRectF(15, 14, 4, 4))
    elif kind == "scene":                         # Scenes: a framed landscape
        p.drawRoundedRect(QRectF(3, 4.5, 18, 15), 2.5, 2.5)
        p.drawPolyline([QPointF(3.5, 17), QPointF(9, 11), QPointF(13, 15), QPointF(15.5, 12.5),
                        QPointF(20.5, 17)])
        p.drawEllipse(QRectF(14.5, 7, 3, 3))
    elif kind in ("collapse", "expand"):
        d = -1 if kind == "collapse" else 1
        for x in (9, 15):
            p.drawPolyline([QPointF(x - 2.5 * d, 7), QPointF(x + 2.5 * d, 12), QPointF(x - 2.5 * d, 17)])
    p.end()
    pix.setDevicePixelRatio(size / 18)
    return pix


def nav_icon(kind: str, checkable: bool = True) -> QIcon:
    """A sidebar icon: grey normally, white when the page is selected."""
    icon = QIcon()
    icon.addPixmap(_draw_icon(kind, theme.MUTED), QIcon.Normal, QIcon.Off)
    icon.addPixmap(_draw_icon(kind, theme.TEXT), QIcon.Active, QIcon.Off)
    if checkable:
        icon.addPixmap(_draw_icon(kind, theme.TEXT), QIcon.Normal, QIcon.On)
        icon.addPixmap(_draw_icon(kind, theme.TEXT), QIcon.Active, QIcon.On)
    return icon
