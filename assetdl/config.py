"""Settings, and where the app keeps its files.

Settings live in the user's config folder, so they survive replacing the .exe:
    Windows:  %APPDATA%\\CSR2 Asset Downloader\\settings.json
    Linux:    ~/.config/csr2-asset-downloader/settings.json
    macOS:    ~/Library/Application Support/CSR2 Asset Downloader/settings.json
The cache (asset databases, the car names, the last branch that worked) lives next to it, in cache/.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from dataclasses import asdict, dataclass, fields
from pathlib import Path

from assetdl import APP_NAME

WORKER_CHOICES = (2, 4, 8, 12, 16)


def app_dir() -> Path:
    """The folder the app runs from: next to the .exe when packaged, else the project folder."""
    if getattr(sys, "frozen", False):                  # PyInstaller
        return Path(sys.executable).resolve().parent
    if "__compiled__" in globals():                    # Nuitka: argv[0] is the .exe, even for onefile
        return Path(sys.argv[0]).resolve().parent
    return Path(__file__).resolve().parents[1]


def resource(name: str) -> Path:
    """A file bundled with the app (assets/...)."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    return base / "assets" / name


def config_dir() -> Path:
    override = os.environ.get("CSR2_ASSETS_CONFIG")
    if override:
        return Path(override)
    if sys.platform == "win32":
        root = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
        return root / APP_NAME
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    root = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return root / "csr2-asset-downloader"


def cache_dir() -> Path:
    path = config_dir() / "cache"
    path.mkdir(parents=True, exist_ok=True)
    return path


def default_save_dir() -> str:
    # next to the program, like the other tools; a Mac .app can't hold files, so there it's ~/Documents
    if sys.platform == "darwin" and ".app/Contents/" in app_dir().as_posix() + "/":
        return str(Path.home() / "Documents" / "CSR2 Assets")
    return str(app_dir() / "CSR2 Assets")


@dataclass
class Settings:
    setup_done: bool = False
    show_crdb: bool = False            # list cars by CRDB name instead of their in-game name
    save_dir: str = ""                 # <save_dir>/<CRDB key>/, global_libraries/, scenes/
    player_id: str = ""                # unlocks New Cars (the announced branches) and the live branch
    keep_old: bool = True              # an updated bundle's older copy goes to _old_bundles/ (else deleted)
    workers: int = 8                   # downloads at once
    sidebar_collapsed: bool = False
    check_updates: bool = True         # look for a newer release on GitHub at start
    skipped_version: str = ""          # "Skip this version" in the update dialog

    def __post_init__(self):
        if not self.save_dir:
            self.save_dir = default_save_dir()
        self.player_id = "".join(str(self.player_id or "").split())
        if self.workers not in WORKER_CHOICES:
            self.workers = 8

    @property
    def root(self) -> Path:
        return Path(self.save_dir)

    @classmethod
    def load(cls) -> "Settings":
        file = config_dir() / "settings.json"
        try:
            data = json.loads(file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return cls()
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known})

    def save(self) -> None:
        folder = config_dir()
        folder.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile("w", dir=folder, suffix=".tmp", delete=False,
                                         encoding="utf-8") as out:
            json.dump(asdict(self), out, indent=2)
            tmp = out.name
        os.replace(tmp, folder / "settings.json")
