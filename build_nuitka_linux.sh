#!/usr/bin/env bash
# Nuitka build: "dist-nuitka/CSR2 Asset Downloader". Needs gcc and patchelf
# (CachyOS / Arch: sudo pacman -S --needed gcc patchelf ccache).
set -euo pipefail
cd "$(dirname "$0")"
[ -d .venv ] || python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt nuitka ordered-set zstandard
python build_nuitka.py "$@"
