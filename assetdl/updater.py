from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import sys
import tarfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from assetdl import APP_NAME, REPO, VERSION

API = "https://api.github.com/repos/{repo}/releases/latest"
WINDOWS_ASSET = "CSR2-Asset-Downloader-windows.exe"
LINUX_ASSET = "CSR2-Asset-Downloader-linux-x86_64.tar.gz"
LINUX_MEMBER = APP_NAME
OLD_SUFFIX = ".old"
UNPACK_DIR_NAME = "CSR2AssetDownloader"
USER_AGENT = f"CSR2-Asset-Downloader/{VERSION}"


class UpdateError(RuntimeError):
    pass


class Cancelled(UpdateError):
    pass


@dataclass
class UpdateInfo:
    version: str
    tag: str
    notes: str
    page_url: str
    asset_name: str = ""
    asset_url: str = ""
    size: int = 0
    sha256: str = ""


def parse_version(text: str) -> tuple:
    m = re.match(r"^\s*v?(\d+(?:\.\d+)*)", str(text or ""))
    if not m:
        return ()
    parts = [int(p) for p in m.group(1).split(".")]
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts)


def is_newer(candidate: str, current: str = VERSION) -> bool:
    a, b = parse_version(candidate), parse_version(current)
    return bool(a) and a > b


def asset_name_for(platform: str = sys.platform) -> str:
    if platform == "win32":
        return WINDOWS_ASSET
    if platform.startswith("linux"):
        return LINUX_ASSET
    return ""


def release_from_json(data: dict, platform: str = sys.platform) -> UpdateInfo:
    tag = str(data.get("tag_name") or "")
    info = UpdateInfo(version=".".join(map(str, parse_version(tag))) or tag, tag=tag,
                      notes=str(data.get("body") or "").strip(),
                      page_url=str(data.get("html_url") or f"https://github.com/{REPO}/releases/latest"))
    wanted = asset_name_for(platform)
    for asset in data.get("assets") or []:
        if asset.get("name") == wanted:
            info.asset_name = wanted
            info.asset_url = str(asset.get("browser_download_url") or "")
            info.size = int(asset.get("size") or 0)
            digest = str(asset.get("digest") or "")
            if digest.lower().startswith("sha256:"):
                info.sha256 = digest.split(":", 1)[1].strip().lower()
            break
    return info


def _session():
    import requests
    s = requests.Session()
    s.headers["User-Agent"] = USER_AGENT
    return s


def check(timeout: float = 10.0, session=None) -> Optional[UpdateInfo]:
    s = session or _session()
    try:
        r = s.get(API.format(repo=REPO), timeout=timeout,
                  headers={"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"})
    except Exception as exc:
        raise UpdateError(f"couldn't reach GitHub ({type(exc).__name__})") from exc
    if r.status_code == 404:
        raise UpdateError("no releases have been published yet")
    if r.status_code in (403, 429):
        raise UpdateError("GitHub's rate limit was hit; try again in a while")
    if r.status_code != 200:
        raise UpdateError(f"GitHub answered {r.status_code}")
    info = release_from_json(r.json())
    if not is_newer(info.version):
        return None
    return info


def compiled() -> bool:
    return "__compiled__" in globals()


def executable() -> Optional[Path]:
    if not compiled():
        return None
    path = Path(sys.argv[0]).resolve()
    return path if path.is_file() else None


def can_self_update() -> tuple[bool, str]:
    exe = executable()
    if exe is None:
        return False, "Running from source: update with git pull, or download the release."
    if not asset_name_for():
        return False, "There is no release file for this system."
    if not os.access(exe.parent, os.W_OK):
        return False, f"Can't write to {exe.parent}. Move the app to a folder you own, or download the release."
    return True, ""


def download(info: UpdateInfo, report: Optional[Callable[[int, int], None]] = None,
             stop: Optional[threading.Event] = None, folder: Optional[Path] = None, session=None) -> Path:
    if not info.asset_url:
        raise UpdateError(f"release {info.tag} has no {asset_name_for() or 'file for this system'}")
    report = report or (lambda done, total: None)
    stop = stop or threading.Event()
    exe = executable()
    folder = Path(folder or (exe.parent if exe else Path.cwd()))
    part = folder / f".{info.asset_name}.part"
    s = session or _session()
    digest = hashlib.sha256()
    got = 0
    try:
        with s.get(info.asset_url, stream=True, timeout=30) as r:
            if r.status_code != 200:
                raise UpdateError(f"the download answered {r.status_code}")
            total = info.size or int(r.headers.get("Content-Length") or 0)
            with open(part, "wb") as out:
                for chunk in r.iter_content(chunk_size=1 << 16):
                    if stop.is_set():
                        raise Cancelled("cancelled")
                    if chunk:
                        out.write(chunk)
                        digest.update(chunk)
                        got += len(chunk)
                        report(got, total)
        if info.size and got != info.size:
            raise UpdateError(f"the download is incomplete ({got} of {info.size} bytes)")
        if info.sha256 and digest.hexdigest() != info.sha256:
            raise UpdateError("the download doesn't match the checksum GitHub reports")
        return _unpack(part, info, folder)
    except BaseException:
        part.unlink(missing_ok=True)
        raise


def _unpack(part: Path, info: UpdateInfo, folder: Path) -> Path:
    new = folder / f".{APP_NAME}.new"
    new.unlink(missing_ok=True)
    if info.asset_name.endswith(".tar.gz"):
        with tarfile.open(part, "r:gz") as tar:
            member = next((m for m in tar.getmembers()
                           if m.isfile() and Path(m.name).name == LINUX_MEMBER), None)
            if member is None:
                raise UpdateError(f"{info.asset_name} doesn't contain {LINUX_MEMBER}")
            with tar.extractfile(member) as src, open(new, "wb") as dst:
                shutil.copyfileobj(src, dst)
        part.unlink(missing_ok=True)
    else:
        os.replace(part, new)
    if sys.platform != "win32":
        new.chmod(0o755)
    return new


def install(new: Path, exe: Optional[Path] = None) -> Path:
    exe = exe or executable()
    if exe is None:
        raise UpdateError("not running as a built app")
    if sys.platform == "win32":
        old = exe.with_name(exe.name + OLD_SUFFIX)
        if old.exists():
            try:
                old.unlink()
            except OSError:
                old = exe.with_name(f"{exe.name}{OLD_SUFFIX}{os.getpid()}")
        os.replace(exe, old)
        try:
            os.replace(new, exe)
        except OSError:
            os.replace(old, exe)
            raise
    else:
        os.replace(new, exe)
    return exe


def restart(exe: Path) -> None:
    env = {k: v for k, v in os.environ.items() if not k.startswith("NUITKA_")}
    kwargs = {"env": env, "close_fds": True, "cwd": str(exe.parent)}
    if sys.platform == "win32":
        kwargs["creationflags"] = 0x00000008 | 0x00000200
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen([str(exe)], **kwargs)


def cleanup() -> None:
    exe = executable()
    if exe is None:
        return
    for leftover in exe.parent.glob(f"{exe.name}{OLD_SUFFIX}*"):
        try:
            leftover.unlink()
        except OSError:
            pass
    for stray in (exe.parent / f".{APP_NAME}.new", exe.parent / f".{asset_name_for()}.part"):
        try:
            stray.unlink()
        except OSError:
            pass
    here = Path(__file__).resolve().parents[1]
    if here.parent.name != UNPACK_DIR_NAME or here.name != VERSION:
        return
    for other in here.parent.iterdir():
        if other.is_dir() and other.name != VERSION and parse_version(other.name):
            shutil.rmtree(other, ignore_errors=True)
