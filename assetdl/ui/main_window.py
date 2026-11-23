"""The main window: New Cars, Global Libraries, Car Assets, Scenes and Settings."""

from __future__ import annotations

import threading
from pathlib import Path

from PySide6.QtCore import (QAbstractListModel, QEasingCurve, QModelIndex, QParallelAnimationGroup,
                            QPropertyAnimation, QSize, Qt, QThreadPool, QTimer, QUrl)
from PySide6.QtGui import QColor, QDesktopServices, QFont, QIcon, QKeySequence, QPainter, QShortcut
from PySide6.QtWidgets import (QAbstractItemView, QButtonGroup, QCheckBox, QComboBox, QFrame, QGridLayout,
                               QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListView, QMainWindow,
                               QMessageBox, QPlainTextEdit, QProgressBar, QPushButton, QStackedWidget, QStyle,
                               QStyledItemDelegate, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from assetdl import APP_NAME, AUTHOR, VERSION
from assetdl.assets import (CURRENT, LIBRARIES_DIR, MISSING, QUALITY, SCENES_DIR, UPDATE, PlanError, car_plan,
                            file_state, human_size, library_assets, scene_assets, scene_label)
from assetdl.config import WORKER_CHOICES, Settings
from assetdl.downloader import Job, run_jobs
from assetdl.session import NEW, UPCOMING, Car, Session, apply_new_cars, find_new_cars, open_session
from assetdl.ui import theme
from assetdl.ui.widgets import FolderPicker, Segmented, Switch, asset_pixmap, card, credit, label, nav_icon
from assetdl.ui.workers import Task
from assetdl import updater

PAGES = (("New Cars", "badge"), ("Global Libraries", "stack"), ("Car Assets", "car"), ("Scenes", "scene"),
         ("Settings", "gear"))
NEW_CARS, LIBRARIES, CARS, SCENES, SETTINGS = range(5)

TAG_STYLE = {UPCOMING: ("UPCOMING", theme.WARN, "#2a2210"), NEW: ("NEW", theme.ACCENT_TEXT, "#2a1212")}
STATUS_STYLE = {CURRENT: ("Current", theme.OK), UPDATE: ("Update", theme.WARN), MISSING: ("Missing", theme.MUTED)}


# --- car lists -----------------------------------------------------------------------------------------------------
class CarModel(QAbstractListModel):
    def __init__(self):
        super().__init__()
        self.cars: list[Car] = []
        self.show_crdb = False

    def set_cars(self, cars: list[Car]):
        self.beginResetModel()
        self.cars = cars
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.cars)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        car = self.cars[index.row()]
        if role == Qt.DisplayRole:
            return car.label(self.show_crdb)[0]
        if role == Qt.UserRole:
            return car
        return None


class CarDelegate(QStyledItemDelegate):
    def __init__(self, model: CarModel, parent=None):
        super().__init__(parent)
        self.model = model
        self.main_font = QFont(theme.FONT, 10, QFont.DemiBold)
        self.sub_font = QFont(theme.MONO, 8)
        self.tag_font = QFont(theme.FONT, 7, QFont.Bold)

    def sizeHint(self, option, index):
        return QSize(200, 50)

    def paint(self, p: QPainter, option, index):
        car: Car = index.data(Qt.UserRole)
        main, sub = car.label(self.model.show_crdb)
        r = option.rect.adjusted(2, 2, -2, -2)
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        selected = option.state & QStyle.State_Selected
        hover = option.state & QStyle.State_MouseOver
        if selected or hover:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(theme.SURFACE_3 if selected else theme.SURFACE_2))
            p.drawRoundedRect(r, 8, 8)
        if selected:
            p.setBrush(QColor(theme.ACCENT_HOVER))
            p.drawRoundedRect(r.left(), r.top() + 8, 3, r.height() - 16, 1.5, 1.5)
        right = r.right() - 10
        if car.tag in TAG_STYLE:
            text, fg, bg = TAG_STYLE[car.tag]
            p.setFont(self.tag_font)
            w = p.fontMetrics().horizontalAdvance(text) + 14
            pill = r.adjusted(r.width() - w - 10, 15, -10, -15)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(bg))
            p.drawRoundedRect(pill, 9, 9)
            p.setPen(QColor(fg))
            p.drawText(pill, Qt.AlignCenter, text)
            right = pill.left() - 8
        text_rect = r.adjusted(14, 6, 0, -6)
        text_rect.setRight(right)
        p.setFont(self.main_font)
        p.setPen(QColor(theme.TEXT))
        fm = p.fontMetrics()
        p.drawText(text_rect.adjusted(0, 0, 0, -text_rect.height() // 2), Qt.AlignLeft | Qt.AlignBottom,
                   fm.elidedText(main, Qt.ElideRight, text_rect.width()))
        if sub:
            p.setFont(self.sub_font)
            p.setPen(QColor(theme.MUTED))
            fm = p.fontMetrics()
            p.drawText(text_rect.adjusted(0, text_rect.height() // 2 + 2, 0, 0), Qt.AlignLeft | Qt.AlignTop,
                       fm.elidedText(sub, Qt.ElideRight, text_rect.width()))
        p.restore()


def car_list(model: CarModel) -> QListView:
    view = QListView()
    view.setModel(model)
    view.setItemDelegate(CarDelegate(model, view))
    view.setSelectionMode(QAbstractItemView.ExtendedSelection)
    view.setUniformItemSizes(True)
    view.setMouseTracking(True)
    view.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
    return view


# --- asset tables --------------------------------------------------------------------------------------------------
class AssetTable(QTreeWidget):
    """Checkable rows of bundles: name, version, size and whether the file on disk is current."""

    COLS = ("Name", "Version", "Size", "Status")

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setColumnCount(len(self.COLS))
        self.setHeaderLabels(self.COLS)
        self.setRootIsDecorated(False)
        self.setAlternatingRowColors(True)
        self.setUniformRowHeights(True)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        head = self.header()
        head.setStretchLastSection(False)
        head.setSectionResizeMode(0, QHeaderView.Stretch)
        for c in (1, 2, 3):
            head.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        self.rows: list[tuple] = []           # (asset, folder, item)
        self.itemChanged.connect(lambda *_: self.on_change())
        self.on_change = lambda: None
        self.itemDoubleClicked.connect(self._toggle)

    def _toggle(self, item, _col):
        item.setCheckState(0, Qt.Unchecked if item.checkState(0) == Qt.Checked else Qt.Checked)

    def set_rows(self, rows, check: str = "needed"):
        """rows: (asset, folder, display name, tooltip)."""
        self.blockSignals(True)
        self.clear()
        self.rows = []
        for asset, folder, name, tip in rows:
            item = QTreeWidgetItem([name, str(asset.version), human_size(asset.size(QUALITY)), ""])
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setToolTip(0, tip or asset.filename(QUALITY))
            item.setTextAlignment(1, Qt.AlignRight | Qt.AlignVCenter)
            item.setTextAlignment(2, Qt.AlignRight | Qt.AlignVCenter)
            item.setCheckState(0, Qt.Unchecked)
            self.addTopLevelItem(item)
            self.rows.append((asset, Path(folder), item))
        self.blockSignals(False)
        self.refresh_status()
        self.check(check)

    def refresh_status(self):
        self.blockSignals(True)
        for asset, folder, item in self.rows:
            state = file_state(folder, asset)
            text, colour = STATUS_STYLE[state]
            item.setText(3, text)
            item.setForeground(3, QColor(colour))
            item.setData(3, Qt.UserRole, state)
        self.blockSignals(False)
        self.on_change()

    def check(self, which: str):
        self.blockSignals(True)
        for asset, folder, item in self.rows:
            on = which == "all" or (which == "needed" and item.data(3, Qt.UserRole) != CURRENT)
            item.setCheckState(0, Qt.Checked if on else Qt.Unchecked)
        self.blockSignals(False)
        self.on_change()

    def checked_jobs(self) -> list[Job]:
        return [Job(asset, folder) for asset, folder, item in self.rows if item.checkState(0) == Qt.Checked]

    def summary(self) -> str:
        checked = [(a, i) for a, _f, i in self.rows if i.checkState(0) == Qt.Checked]
        need = [a for a, i in checked if i.data(3, Qt.UserRole) != CURRENT]
        current = sum(1 for _a, _f, i in self.rows if i.data(3, Qt.UserRole) == CURRENT)
        size = sum(a.size(QUALITY) for a in need)
        return (f"{len(self.rows)} bundles · {current} current · {len(checked)} selected"
                + (f" · {len(need)} to download ({human_size(size)})" if need else ""))


def check_bar(table: AssetTable) -> QHBoxLayout:
    bar = QHBoxLayout()
    bar.setSpacing(6)
    for text, which in (("Select needed", "needed"), ("All", "all"), ("None", "none")):
        b = QPushButton(text)
        b.setToolTip({"needed": "Select everything that is missing or outdated", "all": "Select every row",
                      "none": "Clear the selection"}[which])
        b.setObjectName("Chip")
        b.setCursor(Qt.PointingHandCursor)
        b.clicked.connect(lambda _=False, w=which: table.check(w))
        bar.addWidget(b)
    return bar


# --- window --------------------------------------------------------------------------------------------------------
class MainWindow(QMainWindow):
    def __init__(self, settings: Settings, session: Session | None = None):
        super().__init__()
        self.settings = settings
        self.session = session or Session()
        self.pool = QThreadPool.globalInstance()
        self.busy = False
        self.stop = threading.Event()
        self._tasks: set = set()
        self._plan_cache: dict = {}

        self.setWindowTitle(APP_NAME)
        self.resize(1180, 760)
        self.setMinimumSize(940, 600)

        root = QWidget()
        root.setObjectName("Root")
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        body = QHBoxLayout()
        body.setSpacing(0)
        outer.addLayout(body, 1)

        body.addWidget(self._sidebar())
        self.pages = QStackedWidget()
        self.pages.addWidget(self._new_cars_page())
        self.pages.addWidget(self._libraries_page())
        self.pages.addWidget(self._cars_page())
        self.pages.addWidget(self._scenes_page())
        self.pages.addWidget(self._settings_page())
        body.addWidget(self.pages, 1)
        outer.addWidget(self._status_bar())

        self.search_timer = QTimer(self, singleShot=True, interval=120)
        self.search_timer.timeout.connect(self._run_search)
        self.new_search_timer = QTimer(self, singleShot=True, interval=120)
        self.new_search_timer.timeout.connect(self._fill_new_cars)
        QShortcut(QKeySequence("Ctrl+F"), self, activated=self._focus_search)
        for i in range(len(PAGES)):
            QShortcut(QKeySequence(f"Ctrl+{i + 1}"), self, activated=lambda i=i: self._nav(i))
        self._nav(NEW_CARS if self.settings.player_id else CARS)
        self._session_ready(self.session, initial=True)
        self.update_info = None
        if self.settings.check_updates:
            QTimer.singleShot(2500, lambda: self.check_updates(manual=False))

    # --- layout pieces --------------------------------------------------------------------------------------------
    SIDEBAR_OPEN, SIDEBAR_SHUT = 206, 64

    def _sidebar(self) -> QWidget:
        side = QFrame()
        side.setObjectName("Sidebar")
        self.side = side
        lay = QVBoxLayout(side)
        lay.setContentsMargins(12, 18, 12, 12)
        lay.setSpacing(4)
        self.brand = QLabel()
        self.brand.setAlignment(Qt.AlignCenter)
        logo = asset_pixmap("brand.png", 70)
        if logo is not None:
            self.brand.setPixmap(logo)
        else:
            self.brand.setText("CSR2 ASSETS")
            self.brand.setObjectName("Brand")
        self.brand_small = QLabel()
        self.brand_small.setAlignment(Qt.AlignCenter)
        small = asset_pixmap("icon.png", 38)
        if small is not None:
            self.brand_small.setPixmap(small)
        lay.addWidget(self.brand)
        lay.addWidget(self.brand_small)
        lay.addSpacing(18)
        self.nav_group = QButtonGroup(self)
        self.nav_buttons = []
        for i, (name, icon) in enumerate(PAGES):
            if i == SETTINGS:
                lay.addStretch(1)       # Settings sits at the bottom
            b = QPushButton(name)
            b.setObjectName("Nav")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.setIcon(nav_icon(icon))
            b.setIconSize(QSize(18, 18))
            b.setToolTip(f"{name} (Ctrl+{i + 1})")
            b.clicked.connect(lambda _=False, i=i: self._nav(i))
            self.nav_group.addButton(b, i)
            self.nav_buttons.append(b)
            lay.addWidget(b)
        self.collapse_btn = QPushButton("Collapse")
        self.collapse_btn.setObjectName("Nav")
        self.collapse_btn.setCursor(Qt.PointingHandCursor)
        self.collapse_btn.setIconSize(QSize(18, 18))
        self.collapse_btn.clicked.connect(lambda: self.set_sidebar(not self.settings.sidebar_collapsed, True))
        lay.addWidget(self.collapse_btn)
        QShortcut(QKeySequence("Ctrl+B"), self, activated=self.collapse_btn.click)
        self.set_sidebar(self.settings.sidebar_collapsed, animate=False)
        return side

    def set_sidebar(self, collapsed: bool, animate: bool = False):
        """Collapse to icons only, or open with names and the logo. Remembered between runs."""
        if collapsed != self.settings.sidebar_collapsed:
            self.settings.sidebar_collapsed = collapsed
            self.settings.save()
        width = self.SIDEBAR_SHUT if collapsed else self.SIDEBAR_OPEN

        def labels():
            for b, (name, _icon) in zip(self.nav_buttons, PAGES):
                b.setText("" if collapsed else name)
            self.collapse_btn.setText("" if collapsed else "Collapse")
            self.collapse_btn.setIcon(nav_icon("expand" if collapsed else "collapse", checkable=False))
            self.collapse_btn.setToolTip(("Expand" if collapsed else "Collapse") + " sidebar (Ctrl+B)")
            self.brand.setVisible(not collapsed)
            self.brand_small.setVisible(collapsed)
            style = "text-align: center; padding: 9px 0;" if collapsed else ""
            for b in (*self.nav_buttons, self.collapse_btn):
                b.setStyleSheet(style)

        if not animate:
            self.side.setFixedWidth(width)
            labels()
            return
        if collapsed:
            labels()
        group = QParallelAnimationGroup(self)
        for prop in (b"minimumWidth", b"maximumWidth"):
            a = QPropertyAnimation(self.side, prop, group)
            a.setDuration(180)
            a.setStartValue(self.side.width())
            a.setEndValue(width)
            a.setEasingCurve(QEasingCurve.OutCubic)
            group.addAnimation(a)
        if not collapsed:
            group.finished.connect(labels)
        group.start()
        self._side_anim = group

    def _page(self, title: str, subtitle: str = "") -> tuple[QWidget, QVBoxLayout]:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(26, 22, 26, 18)
        lay.setSpacing(12)
        lay.addWidget(label(title, "PageTitle"))
        if subtitle:
            sub = label(subtitle, "Muted", wrap=True)
            sub.setTextFormat(Qt.PlainText)
            lay.addWidget(sub)
        return page, lay

    def _banner(self) -> QLabel:
        b = label("", "Banner", wrap=True)
        b.setContentsMargins(12, 8, 12, 8)
        b.hide()
        return b

    def _primary(self, text: str, slot, width: int = 170) -> QPushButton:
        b = QPushButton(text)
        b.setObjectName("Primary")
        b.setMinimumWidth(width)
        b.clicked.connect(slot)
        return b

    # New Cars
    def _new_cars_page(self) -> QWidget:
        page, lay = self._page("New Cars", "Cars staged for the next update, and the cars that are new in this "
                                           "game version.")
        self.new_banner = self._banner()
        lay.addWidget(self.new_banner)
        self.new_stack = QStackedWidget()
        lay.addWidget(self.new_stack, 1)

        # locked: no Player ID yet
        lock_wrap = QWidget()
        lw = QVBoxLayout(lock_wrap)
        lw.setContentsMargins(0, 20, 0, 0)
        lock = QFrame()
        lock.setObjectName("Lock")
        lock.setFixedWidth(560)
        ll = QVBoxLayout(lock)
        ll.setContentsMargins(28, 26, 28, 26)
        ll.setSpacing(12)
        icon = QLabel()
        icon.setPixmap(nav_icon("badge").pixmap(QSize(40, 40), QIcon.Normal, QIcon.On))
        ll.addWidget(icon)
        ll.addWidget(label("New Cars needs your Player ID", "CarTitle"))
        desc = label("Which branch the game has staged for its next update is only announced to a player, "
                     "through the game's metadata service. Add your Player ID (the ID the game shows for "
                     "your account) to see upcoming and newly added cars.", "Muted", wrap=True)
        desc.setMinimumHeight(desc.heightForWidth(560 - 56) + 4)    # (added with an alignment: no height-for-width)
        ll.addWidget(desc)
        row = QHBoxLayout()
        self.unlock_edit = QLineEdit()
        self.unlock_edit.setPlaceholderText("Player ID")
        self.unlock_edit.returnPressed.connect(self._unlock)
        row.addWidget(self.unlock_edit, 1)
        row.addWidget(self._primary("Unlock", self._unlock, 110))
        ll.addLayout(row)
        lw.addWidget(lock, 0, Qt.AlignHCenter | Qt.AlignTop)
        lw.addStretch(1)
        self.new_stack.addWidget(lock_wrap)

        # unlocked
        content = QWidget()
        cl = QVBoxLayout(content)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(10)
        stats = QHBoxLayout()
        stats.setSpacing(12)
        self.stat_upcoming = self._stat("Upcoming", theme.WARN)
        self.stat_recent = self._stat("New this version", theme.ACCENT_TEXT)
        stats.addWidget(self.stat_upcoming[0], 1)
        stats.addWidget(self.stat_recent[0], 1)
        check = QPushButton("Check again")
        check.clicked.connect(self.check_new_cars)
        self.new_check_btn = check
        stats.addWidget(check, 0, Qt.AlignVCenter)
        cl.addLayout(stats)
        filt = QHBoxLayout()
        self.new_search = QLineEdit()
        self.new_search.setObjectName("Search")
        self.new_search.setPlaceholderText("Filter…")
        self.new_search.setClearButtonEnabled(True)
        self.new_search.textChanged.connect(lambda _: self.new_search_timer.start())
        filt.addWidget(self.new_search, 1)
        self.new_filter = Segmented([("all", "All"), (UPCOMING, "Upcoming"), (NEW, "New this version")])
        self.new_filter.picked.connect(lambda _k: self._fill_new_cars())
        filt.addWidget(self.new_filter)
        cl.addLayout(filt)
        self.new_model = CarModel()
        self.new_list = car_list(self.new_model)
        self.new_list.doubleClicked.connect(lambda _: self._download_new_selected())
        self.new_list.selectionModel().selectionChanged.connect(lambda *_: self._new_selection())
        cl.addWidget(self.new_list, 1)
        self.new_info = label("", "Muted", wrap=True)
        cl.addWidget(self.new_info)
        bar = QHBoxLayout()
        bar.setSpacing(12)
        self.new_libs = QCheckBox("Also update the global libraries")
        self.new_libs.setChecked(False)
        bar.addWidget(self.new_libs)
        bar.addStretch(1)
        show = QPushButton("Show in Car Assets")
        show.clicked.connect(self._show_new_in_cars)
        bar.addWidget(show)
        self.new_all_btn = QPushButton("Download all")
        self.new_all_btn.clicked.connect(lambda: self._download_cars(self.new_model.cars, self.new_libs.isChecked()))
        bar.addWidget(self.new_all_btn)
        self.new_dl_btn = self._primary("Download selected", self._download_new_selected)
        bar.addWidget(self.new_dl_btn)
        cl.addLayout(bar)
        self.new_stack.addWidget(content)
        return page

    def _stat(self, title: str, colour: str):
        box = QFrame()
        box.setObjectName("Stat")
        v = QVBoxLayout(box)
        v.setContentsMargins(16, 10, 16, 10)
        v.setSpacing(0)
        t = label(title.upper(), "Section")
        value = label("–", "StatValue")
        value.setStyleSheet(f"color: {colour};")
        sub = label("", "Muted")
        sub.setStyleSheet("font-size: 8pt;")
        v.addWidget(t)
        v.addWidget(value)
        v.addWidget(sub)
        return box, value, sub

    # Global Libraries
    def _libraries_page(self) -> QWidget:
        page, lay = self._page("Global Libraries", "Paint, interior, calliper, livery, wrap, plate and Tuner Stars "
                                                   "libraries, global textures, CarMetadata and Localisation_EN. "
                                                   "Saved to global_libraries/ in your save folder.")
        self.lib_banner = self._banner()
        lay.addWidget(self.lib_banner)
        self.lib_table = AssetTable()
        self.lib_table.on_change = lambda: self.lib_info.setText(self.lib_table.summary())
        top = check_bar(self.lib_table)
        top.addStretch(1)
        lay.addLayout(top)
        lay.addWidget(self.lib_table, 1)
        bar = QHBoxLayout()
        self.lib_info = label("", "Muted")
        bar.addWidget(self.lib_info, 1)
        open_btn = QPushButton("Open folder")
        open_btn.clicked.connect(lambda: self.open_folder(self.settings.root / LIBRARIES_DIR))
        bar.addWidget(open_btn)
        self.lib_btn = self._primary("Download selected", lambda: self._download(
            self.lib_table.checked_jobs(), "Global libraries"))
        bar.addWidget(self.lib_btn)
        lay.addLayout(bar)
        return page

    # Car Assets
    def _cars_page(self) -> QWidget:
        page, lay = self._page("Car Assets")
        self.cars_banner = self._banner()
        lay.addWidget(self.cars_banner)
        cols = QHBoxLayout()
        cols.setSpacing(16)
        lay.addLayout(cols, 1)

        left = QVBoxLayout()
        left.setSpacing(8)
        self.search = QLineEdit()
        self.search.setObjectName("Search")
        self.search.setPlaceholderText("Search by in-game or CRDB name…   (Ctrl+F)")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(lambda _: self.search_timer.start())
        left.addWidget(self.search)
        self.count_label = label("", "Muted")
        left.addWidget(self.count_label)
        self.model = CarModel()
        self.list = car_list(self.model)
        self.list.selectionModel().selectionChanged.connect(lambda *_: self._car_selection())
        self.list.doubleClicked.connect(lambda _: self._download_cars_selected())
        left.addWidget(self.list, 1)
        cols.addLayout(left, 4)

        right = card()
        r = QVBoxLayout(right)
        r.setContentsMargins(16, 16, 16, 16)
        r.setSpacing(8)
        self.car_title = label("No car selected", "CarTitle", wrap=True)
        self.car_crdb = label("", "Mono")
        self.car_crdb.setTextInteractionFlags(Qt.TextSelectableByMouse)
        r.addWidget(self.car_title)
        r.addWidget(self.car_crdb)
        self.car_table = AssetTable()
        self.car_table.on_change = lambda: self.car_info.setText(self.car_table.summary()
                                                                  if self.car_table.rows else "")
        top = check_bar(self.car_table)
        top.addStretch(1)
        r.addLayout(top)
        r.addWidget(self.car_table, 1)
        self.car_info = label("", "Muted", wrap=True)
        r.addWidget(self.car_info)
        cols.addWidget(right, 6)

        bar = QHBoxLayout()
        bar.setSpacing(12)
        self.car_libs = QCheckBox("Also update the global libraries")
        self.car_libs.setChecked(False)
        bar.addWidget(self.car_libs)
        bar.addStretch(1)
        open_btn = QPushButton("Open folder")
        open_btn.clicked.connect(self._open_car_folder)
        bar.addWidget(open_btn)
        self.car_btn = self._primary("Download", self._download_cars_selected)
        bar.addWidget(self.car_btn)
        lay.addLayout(bar)
        return page

    # Scenes
    def _scenes_page(self) -> QWidget:
        page, lay = self._page("Scenes", "The game's scene bundles: garage, workshop, showroom, crew hangout and "
                                         "every race track. Saved to scenes/ in your save folder.")
        self.scene_banner = self._banner()
        lay.addWidget(self.scene_banner)
        self.scene_table = AssetTable()
        self.scene_table.on_change = lambda: self.scene_info.setText(self.scene_table.summary())
        top = check_bar(self.scene_table)
        top.addStretch(1)
        lay.addLayout(top)
        lay.addWidget(self.scene_table, 1)
        bar = QHBoxLayout()
        self.scene_info = label("", "Muted")
        bar.addWidget(self.scene_info, 1)
        open_btn = QPushButton("Open folder")
        open_btn.clicked.connect(lambda: self.open_folder(self.settings.root / SCENES_DIR))
        bar.addWidget(open_btn)
        self.scene_btn = self._primary("Download selected", lambda: self._download(
            self.scene_table.checked_jobs(), "Scenes"))
        bar.addWidget(self.scene_btn)
        lay.addLayout(bar)
        return page

    # Settings
    def _settings_page(self) -> QWidget:
        page, lay = self._page("Settings")
        box = card()
        grid = QGridLayout(box)
        grid.setContentsMargins(20, 18, 20, 18)
        grid.setHorizontalSpacing(24)
        grid.setVerticalSpacing(16)
        grid.setColumnStretch(1, 1)

        def row(r, title, hint, widget, align=Qt.AlignLeft):
            t = QVBoxLayout()
            t.setSpacing(2)
            t.addWidget(label(title))
            if hint:
                t.addWidget(label(hint, "Muted", wrap=True))
            grid.addLayout(t, r, 0)
            if align == Qt.AlignLeft:
                grid.addWidget(widget, r, 1)
            else:
                grid.addWidget(widget, r, 1, alignment=align | Qt.AlignVCenter)

        self.names_toggle = Segmented([("game", "In-game names"), ("crdb", "CRDB names")])
        self.names_toggle.set("crdb" if self.settings.show_crdb else "game")
        self.names_toggle.picked.connect(lambda k: self._set_show_crdb(k == "crdb"))
        row(0, "List cars by", "Search works with both either way.", self.names_toggle, Qt.AlignRight)

        self.folder = FolderPicker(self.settings.save_dir)
        self.folder.changed.connect(self._set_folder)
        row(1, "Save to", "Each car gets its own folder; libraries and scenes get one each.", self.folder)

        pid = QWidget()
        ph = QHBoxLayout(pid)
        ph.setContentsMargins(0, 0, 0, 0)
        self.player = QLineEdit(self.settings.player_id)
        self.player.setPlaceholderText("Player ID")
        self.player.returnPressed.connect(self._set_player)
        ph.addWidget(self.player, 1)
        apply_btn = QPushButton("Apply")
        apply_btn.clicked.connect(self._set_player)
        ph.addWidget(apply_btn)
        row(2, "Player ID", "Unlocks New Cars and the announced live branch.", pid)

        self.keep_switch = Switch(self.settings.keep_old)
        self.keep_switch.toggled.connect(self._set_keep_old)
        row(3, "Keep older versions", "When a bundle is updated, move its older copy to _old_bundles/ "
                                      "instead of deleting it.", self.keep_switch, Qt.AlignRight)

        self.workers = QComboBox()
        for n in WORKER_CHOICES:
            self.workers.addItem(f"{n} at once", n)
        self.workers.setCurrentIndex(WORKER_CHOICES.index(self.settings.workers))
        self.workers.currentIndexChanged.connect(self._set_workers)
        row(4, "Parallel downloads", "", self.workers, Qt.AlignRight)

        upd = QWidget()
        uh = QHBoxLayout(upd)
        uh.setContentsMargins(0, 0, 0, 0)
        uh.setSpacing(10)
        self.update_label = label(f"v{VERSION}", "Muted")
        uh.addWidget(self.update_label, 1)
        uh.addWidget(label("Check on start", "Muted"))
        self.update_switch = Switch(self.settings.check_updates)
        self.update_switch.toggled.connect(self._set_check_updates)
        uh.addWidget(self.update_switch)
        self.update_check_btn = QPushButton("Check now")
        self.update_check_btn.clicked.connect(lambda: self.check_updates(manual=True))
        uh.addWidget(self.update_check_btn)
        row(5, "Updates", "New versions come from the GitHub releases.", upd)
        lay.addWidget(box)

        refresh = QHBoxLayout()
        self.reload_btn = QPushButton("Reconnect / refresh")
        self.reload_btn.clicked.connect(self.reload_session)
        refresh.addWidget(self.reload_btn)
        self.session_info = label("", "Muted", wrap=True)
        refresh.addWidget(self.session_info, 1)
        lay.addLayout(refresh)
        lay.addStretch(1)
        credits = QHBoxLayout()
        credits.setSpacing(22)
        credits.addWidget(credit("bonk_logo.png", f"{APP_NAME} v{VERSION} · made by <b>{AUTHOR}</b>", 24))
        credits.addWidget(credit("nitro4csr.png", "Special thanks to <b>Nitro4CSR</b> (csr2-cdn)", 24))
        credits.addStretch(1)
        lay.addLayout(credits)
        return page

    def _status_bar(self) -> QWidget:
        wrap = QWidget()
        v = QVBoxLayout(wrap)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        self.log_box = QPlainTextEdit()
        self.log_box.setObjectName("Log")
        self.log_box.setReadOnly(True)
        self.log_box.setFixedHeight(160)
        self.log_box.setMaximumBlockCount(5000)
        self.log_box.hide()
        v.addWidget(self.log_box)
        bar = QFrame()
        bar.setObjectName("StatusBar")
        h = QHBoxLayout(bar)
        h.setContentsMargins(16, 7, 12, 7)
        h.setSpacing(12)
        self.status = label("Ready", "Muted")
        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.setTextVisible(False)
        self.progress.setFixedWidth(240)
        self.progress.hide()
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setObjectName("Flat")
        self.cancel_btn.clicked.connect(self._cancel)
        self.cancel_btn.hide()
        self.log_toggle = QPushButton("Show log")
        self.log_toggle.setObjectName("Flat")
        self.log_toggle.clicked.connect(self._toggle_log)
        h.addWidget(self.status, 1)
        self.update_btn = QPushButton("Update available")
        self.update_btn.setObjectName("Chip")
        self.update_btn.setCursor(Qt.PointingHandCursor)
        self.update_btn.clicked.connect(self.show_update)
        self.update_btn.hide()
        h.addWidget(self.update_btn)
        h.addWidget(self.progress)
        h.addWidget(self.cancel_btn)
        h.addWidget(self.log_toggle)
        v.addWidget(bar)
        return wrap

    # --- helpers --------------------------------------------------------------------------------------------------
    def _start(self, task: Task):
        self._tasks.add(task.signals)
        task.signals.done.connect(lambda *_: self._tasks.discard(task.signals))
        task.signals.failed.connect(lambda *_: self._tasks.discard(task.signals))
        self.pool.start(task)

    def _nav(self, index: int):
        self.pages.setCurrentIndex(index)
        self.nav_buttons[index].setChecked(True)

    def _focus_search(self):
        if self.pages.currentIndex() == NEW_CARS and self.new_stack.currentIndex() == 1:
            self.new_search.setFocus()
            self.new_search.selectAll()
            return
        self._nav(CARS)
        self.search.setFocus()
        self.search.selectAll()

    def log(self, text: str):
        self.log_box.appendPlainText(text)

    def _toggle_log(self):
        show = not self.log_box.isVisible()
        self.log_box.setVisible(show)
        self.log_toggle.setText("Hide log" if show else "Show log")

    def set_status(self, text: str, fraction: float | None = None):
        self.status.setText(text)
        if fraction is None:
            self.progress.hide()
        else:
            self.progress.show()
            self.progress.setValue(int(max(0.0, min(1.0, fraction)) * 1000))

    def set_busy(self, busy: bool, cancellable: bool = False):
        self.busy = busy
        self.cancel_btn.setVisible(busy and cancellable)
        self.cancel_btn.setEnabled(True)
        for b in (self.lib_btn, self.car_btn, self.scene_btn, self.new_dl_btn, self.new_all_btn,
                  self.reload_btn, self.new_check_btn):
            b.setEnabled(not busy and self.session.ready)
        self.reload_btn.setEnabled(not busy)

    def open_folder(self, path: Path):
        path = Path(path)
        target = path if path.is_dir() else self.settings.root if self.settings.root.is_dir() \
            else Path(self.settings.save_dir)
        target.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))

    def _show_banner(self, text: str):
        for b in (self.new_banner, self.lib_banner, self.cars_banner, self.scene_banner):
            b.setText(text)
            b.setVisible(bool(text))

    # --- session --------------------------------------------------------------------------------------------------
    def reload_session(self):
        if self.busy:
            return
        self.set_busy(True)
        self.set_status("Connecting to the game CDN", 0.02)
        self.log("Connecting to the game CDN …")
        task = Task(lambda report: open_session(self.settings, lambda t, f: report((t, f))))
        task.signals.progress.connect(lambda tf: self.set_status(*tf))
        task.signals.done.connect(lambda s: self._session_ready(s))
        task.signals.failed.connect(lambda err: self._session_failed(err))
        self._start(task)

    def _session_failed(self, err: str):
        self.set_busy(False)
        self.set_status(f"Couldn't connect: {err}")
        self.log(f"Couldn't connect: {err}")

    def _session_ready(self, session: Session, initial: bool = False):
        self.session = session
        self._plan_cache = {}
        if not (initial and not session.ready and not session.warnings):
            for note in session.notes:
                self.log(note)
            for warning in session.warnings:
                self.log("WARNING: " + warning)
            for note in session.new_cars.notes:
                self.log("New cars: " + note)
            for warning in session.new_cars.warnings:
                self.log("WARNING (new cars): " + warning)
        self.set_busy(False)
        if not session.ready:
            if initial and not session.warnings:          # nothing loaded yet (first run): load now
                QTimer.singleShot(0, self.reload_session)
                return
            self._show_banner("Couldn't reach the game CDN. " + " ".join(session.warnings[:2])
                              + "  Use Settings > Reconnect to try again.")
            self.set_status("Not connected")
            self._update_new_page()
            return
        rejected = bool(self.settings.player_id) and not session.has_player_id
        self._show_banner(" ".join(session.warnings[:2]) if session.offline or rejected else "")
        db = session.database
        info = f"Branch {db.branch_name or session.cdn.branch} · asset database {db.version} · {len(session.keys)} cars"
        self.session_info.setText(info + (" · offline" if session.offline else ""))
        self.set_status(("Offline · " if session.offline else "") + info)
        self._fill_tables()
        self._run_search()
        self._update_new_page()

    def _fill_tables(self):
        db = self.session.database
        root = self.settings.root
        self.lib_table.set_rows([(a, root / LIBRARIES_DIR, a.code, a.filename(QUALITY)) for a in library_assets(db)],
                                check="none")
        self.scene_table.set_rows([(a, root / SCENES_DIR, scene_label(a.code), a.filename(QUALITY))
                                   for a in scene_assets(db)], check="none")
        self._car_selection()

    def _refresh_statuses(self):
        for table in (self.lib_table, self.scene_table, self.car_table):
            table.refresh_status()

    # --- New Cars -------------------------------------------------------------------------------------------------
    def _update_new_page(self):
        if not self.settings.player_id:
            self.new_stack.setCurrentIndex(0)
            return
        self.new_stack.setCurrentIndex(1)
        nc = self.session.new_cars
        _box, value, sub = self.stat_upcoming
        if not nc.checked:
            value.setText("–")
            sub.setText("not checked" if self.session.ready else "not connected")
        else:
            value.setText(str(len(nc.upcoming)))
            sub.setText(nc.upcoming_branch or "nothing staged right now")
        _box, value, sub = self.stat_recent
        value.setText(str(len(nc.recent)) if nc.checked else "–")
        sub.setText(f"since {nc.since_branch}" if nc.since_branch else "")
        msgs = list(nc.warnings)
        if self.settings.player_id and self.session.ready and not self.session.has_player_id:
            msgs.insert(0, "Your Player ID wasn't accepted this time (check it in Settings), so this list "
                           "couldn't be built.")
        self.new_info.setText("  ".join(msgs))
        self._fill_new_cars()

    def _fill_new_cars(self):
        nc = self.session.new_cars
        cat = self.session.catalog
        which = next((k for k, b in self.new_filter.buttons.items() if b.isChecked()), "all")
        keys = (nc.upcoming if which in ("all", UPCOMING) else []) + (nc.recent if which in ("all", NEW) else [])
        cars = [cat.cars[k] for k in keys if k in cat.cars]
        cars.sort(key=lambda c: (c.tag != UPCOMING, c.label(self.settings.show_crdb)[0].lower()))
        cars = cat.search(self.new_search.text(), self.settings.show_crdb, cars)
        self.new_model.show_crdb = self.settings.show_crdb
        self.new_model.set_cars(cars)
        self._new_selection()

    def _new_selection(self):
        n = len(self.new_list.selectionModel().selectedRows())
        self.new_dl_btn.setText(f"Download {n} selected" if n > 1 else "Download selected")
        self.new_dl_btn.setEnabled(n > 0 and not self.busy and self.session.ready)
        self.new_all_btn.setEnabled(bool(self.new_model.cars) and not self.busy and self.session.ready)

    def _selected_cars(self, view: QListView) -> list[Car]:
        return [i.data(Qt.UserRole) for i in sorted(view.selectionModel().selectedRows(), key=lambda i: i.row())]

    def _download_new_selected(self):
        self._download_cars(self._selected_cars(self.new_list), self.new_libs.isChecked())

    def _show_new_in_cars(self):
        cars = self._selected_cars(self.new_list) or self.new_model.cars[:1]
        if not cars:
            return
        self.search.setText(cars[0].crdb)
        self._run_search()
        self._nav(CARS)
        if self.model.cars:
            self.list.setCurrentIndex(self.model.index(0))

    def _unlock(self):
        text = "".join(self.unlock_edit.text().split())
        if not text:
            self.unlock_edit.setFocus()
            return
        self.player.setText(text)
        self._set_player()

    def check_new_cars(self):
        if self.busy or not self.session.ready:
            return
        if not self.session.has_player_id:
            self.reload_session()                # the CDN client needs the Player ID attached: reconnect
            return
        self.set_busy(True)
        self.log("Checking for new cars …")
        task = Task(lambda report: find_new_cars(self.session, lambda t, f: report((t, f)), (0.0, 1.0)))
        task.signals.progress.connect(lambda tf: self.set_status(*tf))
        task.signals.done.connect(self._new_cars_done)
        task.signals.failed.connect(lambda err: (self.set_busy(False), self.set_status(f"Failed: {err}"),
                                                 self.log(f"Checking for new cars failed: {err}")))
        self._start(task)

    def _new_cars_done(self, nc):
        apply_new_cars(self.session, nc)
        for note in nc.notes:
            self.log("New cars: " + note)
        for warning in nc.warnings:
            self.log("WARNING (new cars): " + warning)
        self.set_busy(False)
        self.set_status(f"{len(nc.upcoming)} upcoming · {len(nc.recent)} new this version")
        self._run_search()
        self._update_new_page()

    # --- Car Assets -----------------------------------------------------------------------------------------------
    def _run_search(self):
        cat = self.session.catalog
        self.model.show_crdb = self.settings.show_crdb
        cars = cat.search(self.search.text(), self.settings.show_crdb)
        selected = {c.crdb for c in self._selected_cars(self.list)}
        self.model.set_cars(cars)
        total = len(cat.cars)
        self.count_label.setText(f"{len(cars)} of {total} cars" if self.search.text().strip() else f"{total} cars")
        if selected:
            sel = self.list.selectionModel()
            for row, car in enumerate(cars):
                if car.crdb in selected:
                    sel.select(self.model.index(row), sel.SelectionFlag.Select)
        self._car_selection()

    def _plan(self, car: Car):
        if car.crdb not in self._plan_cache:
            db = self.session.database_for(car.crdb)
            keys = self.session.keys if db is self.session.database else None
            self._plan_cache[car.crdb] = car_plan(db, car.crdb, keys)
        return self._plan_cache[car.crdb]

    def _car_selection(self):
        cars = self._selected_cars(self.list)
        self.car_btn.setEnabled(bool(cars) and not self.busy and self.session.ready)
        if not cars:
            self.car_title.setText("No car selected" if self.session.ready else "Not connected")
            self.car_crdb.setText("")
            self.car_table.set_rows([])
            self.car_info.setText("Pick a car to see its bundles. Select several with Ctrl/Shift to download "
                                  "them together." if self.session.ready else "")
            self.car_btn.setText("Download")
            return
        if len(cars) > 1:
            self.car_title.setText(f"{len(cars)} cars selected")
            self.car_crdb.setText(", ".join(c.crdb for c in cars[:4]) + (" …" if len(cars) > 4 else ""))
            self.car_table.set_rows([])
            self.car_info.setText("Every car's own and shared bundles will be downloaded into its own folder; "
                                  "files that are already current are skipped.")
            self.car_btn.setText(f"Download {len(cars)} cars")
            return
        car = cars[0]
        main, sub = car.label(self.settings.show_crdb)
        tag = {UPCOMING: "  ·  upcoming", NEW: "  ·  new this version"}.get(car.tag, "")
        self.car_title.setText(main)
        self.car_crdb.setText((sub or "") + tag)
        self.car_btn.setText("Download")
        try:
            plan = self._plan(car)
        except PlanError as exc:
            self.car_table.set_rows([])
            self.car_info.setText(str(exc))
            return
        folder = self.settings.root / car.crdb
        rows = [(a, folder, a.code, "own bundle") for a in plan["own"]]
        rows += [(a, folder, a.code, "shared / dependency") for a in plan["shared"]]
        self.car_table.set_rows(rows, check="needed")

    def _download_cars_selected(self):
        cars = self._selected_cars(self.list)
        if len(cars) == 1 and self.car_table.rows:
            jobs = self.car_table.checked_jobs()
            if self.car_libs.isChecked():
                jobs += self._library_jobs(self.session.database_for(cars[0].crdb))
            self._download(jobs, cars[0].crdb)
            return
        self._download_cars(cars, self.car_libs.isChecked())

    def _library_jobs(self, database=None) -> list[Job]:
        """The libraries of ``database`` (an upcoming car's: the staged ones, which may be newer)."""
        folder = self.settings.root / LIBRARIES_DIR
        return [Job(a, folder) for a in library_assets(database or self.session.database)]

    def _download_cars(self, cars: list[Car], with_libraries: bool):
        if not cars or self.busy or not self.session.ready:
            return
        jobs, problems = [], []
        for car in cars:
            try:
                plan = self._plan(car)
            except PlanError as exc:
                problems.append(f"{car.crdb}: {exc}")
                continue
            folder = self.settings.root / car.crdb
            jobs += [Job(a, folder) for a in plan["own"] + plan["shared"]]
        for p in problems:
            self.log("Skipped " + p)
        if with_libraries:
            staged = next((self.session.database_for(c.crdb) for c in cars if c.tag == UPCOMING), None)
            jobs += self._library_jobs(staged)
        title = cars[0].crdb if len(cars) == 1 else f"{len(cars)} cars"
        self._download(jobs, title)

    def _open_car_folder(self):
        cars = self._selected_cars(self.list)
        self.open_folder(self.settings.root / cars[0].crdb if len(cars) == 1 else self.settings.root)

    # --- downloading ----------------------------------------------------------------------------------------------
    def _download(self, jobs: list[Job], title: str):
        if self.busy or not self.session.ready:
            return
        if not jobs:
            self.set_status("Nothing selected")
            return
        if not self.settings.save_dir:
            QMessageBox.warning(self, APP_NAME, "Pick a save folder in Settings first.")
            return
        self.stop.clear()
        self.set_busy(True, cancellable=True)
        self.log(f"— {title} —")
        cdn, workers, keep = self.session.cdn, self.settings.workers, self.settings.keep_old

        def work(report):
            return run_jobs(cdn, jobs, workers=workers, keep_old=keep,
                            report=lambda t, f: report(("p", t, f)), log=lambda m: report(("l", m)),
                            stop=self.stop)

        def progress(msg):
            if msg[0] == "p":
                self.set_status(msg[1], msg[2])
            else:
                self.log(msg[1])

        task = Task(work)
        task.signals.progress.connect(progress)
        task.signals.done.connect(lambda summary: self._download_done(title, summary))
        task.signals.failed.connect(lambda err: self._download_done(title, None, err))
        self.set_status(f"Starting {title}", 0.0)
        self._start(task)

    def _download_done(self, title: str, summary, err: str = ""):
        self.set_busy(False)
        if summary is None:
            self.set_status(f"{title}: failed - {err}")
            self.log(f"{title}: failed - {err}")
        else:
            text = f"{title}: {summary.text()}"
            self.set_status(text)
            self.log(text)
            if summary.failed and not self.log_box.isVisible():
                self._toggle_log()
        self._refresh_statuses()
        self._new_selection()
        self._car_selection_buttons()

    def _car_selection_buttons(self):
        self.car_btn.setEnabled(bool(self._selected_cars(self.list)) and self.session.ready)

    def _cancel(self):
        self.stop.set()
        self.cancel_btn.setEnabled(False)
        self.set_status("Cancelling …")

    # --- settings -------------------------------------------------------------------------------------------------
    def _set_show_crdb(self, on: bool):
        self.settings.show_crdb = on
        self.settings.save()
        self._run_search()
        self._fill_new_cars()

    def _set_folder(self, path: str):
        self.settings.save_dir = path.strip()
        self.settings.save()
        if self.session.ready:
            self._fill_tables()

    def _set_player(self):
        text = "".join(self.player.text().split())
        self.player.setText(text)
        if text == self.settings.player_id and (self.session.has_player_id or not text):
            self._update_new_page()
            return
        self.settings.player_id = text
        self.settings.save()
        self.unlock_edit.clear()
        self._update_new_page()
        if text:
            self._nav(NEW_CARS)
        self.reload_session()

    def _set_keep_old(self, on: bool):
        self.settings.keep_old = on
        self.settings.save()

    def _set_workers(self, _i: int):
        self.settings.workers = self.workers.currentData()
        self.settings.save()

    # --- updates --------------------------------------------------------------------------------------------------
    def _set_check_updates(self, on: bool):
        self.settings.check_updates = on
        self.settings.save()

    def check_updates(self, manual: bool = False):
        self.update_check_btn.setEnabled(False)
        if manual:
            self.update_label.setText("Checking …")
        task = Task(lambda _report: updater.check())
        task.signals.done.connect(lambda info: self._update_checked(info, manual))
        task.signals.failed.connect(lambda err: self._update_failed(err, manual))
        self._start(task)

    def _update_failed(self, err: str, manual: bool):
        self.update_check_btn.setEnabled(True)
        self.update_label.setText(f"v{VERSION}" + (f" · couldn't check: {err}" if manual else ""))
        self.log(f"Update check: {err}")

    def _update_checked(self, info, manual: bool):
        self.update_check_btn.setEnabled(True)
        self.update_info = info
        if info is None:
            self.update_label.setText(f"v{VERSION} · up to date" if manual else f"v{VERSION}")
            return
        self.update_label.setText(f"v{VERSION} · {info.version} is available")
        self.update_btn.setText(f"Update to {info.version}")
        self.update_btn.show()
        self.log(f"Update available: {info.version} ({info.page_url})")
        if manual or (info.version != self.settings.skipped_version and not self.busy):
            self.show_update()

    def show_update(self):
        if self.update_info is None:
            return
        from assetdl.ui.update import UpdateDialog
        if self.busy:
            QMessageBox.information(self, APP_NAME, "Wait for the current download to finish, then update.")
            return
        UpdateDialog(self.update_info, self.settings, self).exec()

    def closeEvent(self, event):
        self.stop.set()
        super().closeEvent(event)
