"""First-run setup, after the splash: how cars are listed, where the files go, and the Player ID that unlocks
New Cars."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (QButtonGroup, QDialog, QHBoxLayout, QLabel, QLineEdit, QPushButton,
                               QVBoxLayout, QWidget)

from assetdl import APP_NAME
from assetdl.config import Settings
from assetdl.ui import theme
from assetdl.ui.widgets import Choice, FolderPicker, SlideStack, label


class Dots(QWidget):
    def __init__(self, count: int, parent=None):
        super().__init__(parent)
        self.count, self.index = count, 0
        self.setFixedSize(count * 22, 10)

    def set(self, index: int):
        self.index = index
        self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        for i in range(self.count):
            on = i == self.index
            p.setBrush(QColor(theme.ACCENT_HOVER if on else theme.SURFACE_3))
            p.drawRoundedRect(i * 22, 2, 16 if on else 6, 6, 3, 3)


class SetupDialog(QDialog):
    def __init__(self, settings: Settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle(f"{APP_NAME} - setup")
        self.setObjectName("Root")
        self.setMinimumSize(640, 480)
        self.setStyleSheet(f"QDialog#Root {{ background: {theme.BG}; }}")

        root = QVBoxLayout(self)
        root.setContentsMargins(34, 30, 34, 24)
        root.setSpacing(18)
        root.addWidget(label("FIRST-TIME SETUP", "Section"))

        self.stack = SlideStack()
        self.stack.addWidget(self._names_page())
        self.stack.addWidget(self._folder_page())
        self.stack.addWidget(self._player_page())
        root.addWidget(self.stack, 1)

        nav = QHBoxLayout()
        self.dots = Dots(self.stack.count())
        self.back = QPushButton("Back")
        self.back.setObjectName("Flat")
        self.next = QPushButton("Next")
        self.next.setObjectName("Primary")
        self.next.setMinimumWidth(110)
        self.back.clicked.connect(lambda: self._go(self.page - 1))
        self.next.clicked.connect(self._next)
        nav.addWidget(self.dots)
        nav.addStretch(1)
        nav.addWidget(self.back)
        nav.addWidget(self.next)
        root.addLayout(nav)
        self._go(0)

    # pages
    def _names_page(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)
        lay.addWidget(label("How should cars be listed?", "PageTitle"))
        lay.addWidget(label("You can search with either kind of name whichever you pick. "
                            "This only changes what the lists show. You can switch any time in Settings.",
                            "Muted", wrap=True))
        lay.addSpacing(6)
        self.game_names = Choice("In-game names", "The names the game shows. The CRDB name appears "
                                 "underneath.", "Ferrari 296 Speciale")
        self.crdb_names = Choice("CRDB names", "The game's internal car keys, exactly as the bundles "
                                 "are named.", "Ferrari_296Speciale_2025")
        group = QButtonGroup(page)
        group.setExclusive(True)
        group.addButton(self.game_names)
        group.addButton(self.crdb_names)
        (self.crdb_names if self.settings.show_crdb else self.game_names).setChecked(True)
        lay.addWidget(self.game_names)
        lay.addWidget(self.crdb_names)
        lay.addStretch(1)
        return page

    def _folder_page(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        lay.addWidget(label("Where should the assets be saved?", "PageTitle"))
        intro = label("Bundles keep the game's own names (<code>.ASTC.<version>) and are sorted into "
                      "folders inside this one:", "Muted", wrap=True)
        intro.setTextFormat(Qt.PlainText)
        lay.addWidget(intro)
        tree = label("<CRDB key>/          a car's own and shared bundles\n"
                     "global_libraries/    paint, interior, livery ... libraries\n"
                     "scenes/              garage, workshop, showroom, tracks", "Mono")
        tree.setTextFormat(Qt.PlainText)
        tree.setStyleSheet(f"font-family: '{theme.MONO}'; color: {theme.MUTED}; padding: 4px 0 8px 0;")
        lay.addWidget(tree)
        self.folder = FolderPicker(self.settings.save_dir)
        lay.addWidget(self.folder)
        self.folder_error = QLabel("")
        self.folder_error.setStyleSheet(f"color: {theme.ERR};")
        lay.addWidget(self.folder_error)
        lay.addStretch(1)
        return page

    def _player_page(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        lay.addWidget(label("Your Player ID", "PageTitle"))
        lay.addWidget(label("Optional. Global Libraries, Car Assets and Scenes work without it.", "Muted", wrap=True))
        perks = label("With a Player ID the app can also ask the game's metadata service which branches it "
                      "announces. That unlocks:<br><br>"
                      f"<b style='color:{theme.ACCENT_TEXT}'>Newly Released Cars</b><br>"
                      f"<b style='color:{theme.ACCENT_TEXT}'>The announced live branch</b>", wrap=True)
        perks.setTextFormat(Qt.RichText)
        lay.addWidget(perks)
        lay.addSpacing(8)
        self.player = QLineEdit(self.settings.player_id)
        self.player.setPlaceholderText("Player ID (the ID the game shows for your account)")
        lay.addWidget(self.player)
        lay.addWidget(label("It is only sent to the game's own metadata service. You can add or change it later "
                            "in Settings.", "Muted", wrap=True))
        lay.addStretch(1)
        return page

    # navigation
    def _go(self, index: int):
        index = max(0, min(self.stack.count() - 1, index))
        self.page = index
        self.stack.slide_to(index)
        self.dots.set(index)
        self.back.setVisible(index > 0)
        self.next.setText("Finish" if index == self.stack.count() - 1 else "Next")

    def _next(self):
        i = self.page
        if i == 1 and not self.folder.path():
            self.folder_error.setText("Pick a folder for the assets.")
            return
        self.folder_error.setText("")
        if i < self.stack.count() - 1:
            self._go(i + 1)
            return
        self.settings.show_crdb = self.crdb_names.isChecked()
        self.settings.save_dir = self.folder.path()
        self.settings.player_id = "".join(self.player.text().split())
        self.settings.setup_done = True
        self.settings.save()
        self.accept()
