@echo off
rem Nuitka build: "dist-nuitka\CSR2 Asset Downloader.exe". Run on Windows with Python 3.10-3.13.
rem Needs a C compiler: Visual Studio Build Tools ("Desktop development with C++"), or let Nuitka
rem download MinGW64 for you the first time (it asks; this script answers yes).
cd /d "%~dp0"
if not exist .venv (
    py -3 -m venv .venv || python -m venv .venv
)
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -r requirements.txt nuitka ordered-set zstandard
python build_nuitka.py %*
pause
