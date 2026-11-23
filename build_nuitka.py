from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from assetdl import APP_NAME, AUTHOR, VERSION

OUT = ROOT / "dist-nuitka"


def main() -> int:
    folder = "--folder" in sys.argv[1:]
    args = [
        sys.executable, "-m", "nuitka", "app.py",
        "--standalone" if folder else "--onefile",
        "--enable-plugin=pyside6",
        "--include-qt-plugins=sensible,imageformats",
        "--include-package=csr2cdn",
        "--include-package-data=csr2cdn",
        "--include-module=lz4.block",
        "--include-data-dir=assets=assets",
        "--nofollow-import-to=tkinter,unittest,pydoc,numpy,pandas,PIL,UnityPy,cryptography,pytest",
        "--assume-yes-for-downloads",
        f"--output-dir={OUT}",
        f"--output-filename={APP_NAME}",
        f"--company-name={AUTHOR}",
        f"--product-name={APP_NAME}",
        f"--file-version={VERSION}",
        f"--product-version={VERSION}",
        "--remove-output",
    ]
    if not folder:
        args.append("--onefile-tempdir-spec={CACHE_DIR}/CSR2AssetDownloader/" + VERSION)
    if sys.platform == "win32":
        args.append("--windows-console-mode=disable")
        ico = ROOT / "assets" / "icon.ico"
        if ico.exists():
            args.append(f"--windows-icon-from-ico={ico}")
    else:
        png = ROOT / "assets" / "icon.png"
        if png.exists():
            args.append(f"--linux-app-icon={png}")
    print(" ".join(f'"{a}"' if " " in a else a for a in args))
    result = subprocess.run(args, cwd=ROOT).returncode
    if result == 0:
        print(f"\nDone: {OUT}")
    return result


if __name__ == "__main__":
    sys.exit(main())
