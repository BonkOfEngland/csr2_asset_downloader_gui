from __future__ import annotations

import sys

from assetdl.config import resource

BG = "#101010"
SIDEBAR = "#151515"
SURFACE = "#1b1b1b"
SURFACE_2 = "#242424"
SURFACE_3 = "#2d2d2d"
BORDER = "#2f2f2f"
TEXT = "#e8e8e8"
MUTED = "#8f8f8f"
ACCENT = "#740000"
ACCENT_HOVER = "#8c0b0b"
ACCENT_PRESSED = "#5c0000"
ACCENT_TEXT = "#ff6b6b"
OK = "#7fcf8a"
ERR = "#ff7b72"
WARN = "#e8b85c"

if sys.platform == "win32":
    FONT = "Segoe UI"
elif sys.platform == "darwin":
    FONT = "Helvetica Neue"
else:
    FONT = "Noto Sans"
MONO = {"win32": "Consolas", "darwin": "Menlo"}.get(sys.platform, "DejaVu Sans Mono")

CHECK = resource("check.svg").as_posix()

QSS = f"""
* {{ outline: none; }}
QWidget {{ background: transparent; color: {TEXT}; font-family: "{FONT}"; font-size: 10pt; }}
QMainWindow, #Root {{ background: {BG}; }}
QToolTip {{ background: {SURFACE_3}; color: {TEXT}; border: 1px solid {BORDER}; padding: 4px 6px; }}

#Sidebar {{ background: {SIDEBAR}; border-right: 1px solid {BORDER}; }}
#Brand {{ font-size: 15pt; font-weight: 800; letter-spacing: 1px; }}
#BrandSub {{ color: {ACCENT_TEXT}; font-size: 8pt; font-weight: 700; letter-spacing: 3px; }}
QPushButton#Nav {{
    text-align: left; padding: 9px 14px; border: none; border-radius: 8px;
    color: {MUTED}; font-weight: 600; background: transparent;
}}
QPushButton#Nav:hover {{ background: {SURFACE_2}; color: {TEXT}; }}
QPushButton#Nav:checked {{ background: {SURFACE_3}; color: {TEXT}; border-left: 3px solid {ACCENT}; }}
#SideFoot {{ color: {MUTED}; font-size: 8pt; }}

#Card {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 12px; }}
#PageTitle {{ font-size: 17pt; font-weight: 700; }}
#Muted, QLabel[muted="true"] {{ color: {MUTED}; }}
#Section {{ color: {MUTED}; font-size: 8pt; font-weight: 700; letter-spacing: 1.5px; }}
#CarTitle {{ font-size: 13pt; font-weight: 700; }}
#Mono {{ font-family: "{MONO}"; color: {MUTED}; }}

QLineEdit, QPlainTextEdit, QComboBox {{
    background: {SURFACE_2}; border: 1px solid {BORDER}; border-radius: 8px;
    padding: 7px 10px; selection-background-color: {ACCENT};
}}
QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus {{ border: 1px solid {ACCENT_HOVER}; }}
QLineEdit#Search {{ padding: 10px 14px; font-size: 11pt; border-radius: 10px; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{
    background: {SURFACE_2}; border: 1px solid {BORDER}; selection-background-color: {ACCENT};
}}

QPushButton {{
    background: {SURFACE_3}; border: 1px solid {BORDER}; border-radius: 8px;
    padding: 8px 14px; font-weight: 600;
}}
QPushButton:hover {{ background: #363636; }}
QPushButton:pressed {{ background: {SURFACE_2}; }}
QPushButton:disabled {{ color: #5a5a5a; background: {SURFACE_2}; }}
QPushButton#Primary {{ background: {ACCENT}; border: 1px solid {ACCENT_HOVER}; color: white; }}
QPushButton#Primary:hover {{ background: {ACCENT_HOVER}; }}
QPushButton#Primary:pressed {{ background: {ACCENT_PRESSED}; }}
QPushButton#Primary:disabled {{ background: #3a1a1a; border-color: #3a1a1a; color: #8a6a6a; }}
QPushButton#Flat {{ background: transparent; border: none; color: {MUTED}; padding: 6px 8px; }}
QPushButton#Flat:hover {{ color: {TEXT}; }}
QPushButton#Chip {{ background: {SURFACE_2}; border: 1px solid #3a3a3a; border-radius: 14px; color: {TEXT};
    padding: 5px 14px; font-size: 9pt; font-weight: 600; }}
QPushButton#Chip:hover {{ background: {SURFACE_3}; border-color: {ACCENT_HOVER}; }}
QPushButton#Chip:pressed {{ background: {ACCENT_PRESSED}; border-color: {ACCENT_HOVER}; }}

QPushButton#Choice {{
    text-align: left; padding: 16px; border-radius: 12px; background: {SURFACE_2};
    border: 2px solid {BORDER}; font-weight: 500;
}}
QPushButton#Choice:hover {{ border-color: #4a4a4a; }}
QPushButton#Choice:checked {{ border-color: {ACCENT_HOVER}; background: #1f1414; }}

QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{ width: 16px; height: 16px; border-radius: 4px; border: 1px solid #4a4a4a;
    background: {SURFACE_2}; }}
QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT_HOVER};
    image: url("{CHECK}"); }}

QListView {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 12px; padding: 4px; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 4px 2px; }}
QScrollBar::handle:vertical {{ background: #3a3a3a; border-radius: 3px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: #4a4a4a; }}
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{
    height: 0; background: none; }}
QScrollBar:horizontal {{ height: 0; }}

QProgressBar {{ background: {SURFACE_3}; border: none; border-radius: 3px; max-height: 6px; }}
QProgressBar::chunk {{ background: {ACCENT_HOVER}; border-radius: 3px; }}
#StatusBar {{ background: {SIDEBAR}; border-top: 1px solid {BORDER}; }}
#Log {{ font-family: "{MONO}"; font-size: 9pt; background: {SURFACE}; border: none;
    border-top: 1px solid {BORDER}; border-radius: 0; }}
QTreeWidget {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 12px; padding: 4px;
    alternate-background-color: #1e1e1e; }}
QTreeWidget::item {{ padding: 5px 2px; border: none; }}
QTreeWidget::item:selected {{ background: {SURFACE_3}; color: {TEXT}; }}
QTreeWidget::item:hover {{ background: {SURFACE_2}; }}
QTreeWidget::indicator {{ width: 15px; height: 15px; border-radius: 4px; border: 1px solid #4a4a4a;
    background: {SURFACE_2}; }}
QTreeWidget::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT_HOVER}; image: url("{CHECK}"); }}
QHeaderView::section {{ background: transparent; color: {MUTED}; border: none; border-bottom: 1px solid {BORDER};
    padding: 6px 8px; font-size: 8pt; font-weight: 700; }}
#Stat {{ background: {SURFACE_2}; border: 1px solid {BORDER}; border-radius: 10px; }}
#StatValue {{ font-size: 15pt; font-weight: 800; }}
#Lock {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 14px; }}
#Banner {{ background: #2a2210; border: 1px solid #4d3d14; border-radius: 10px; color: {WARN}; }}
"""
