# CSR2 Asset Downloader

Download CSR2's asset bundles straight from the game's own CDN: cars, the global libraries and the scenes,
through Nitro4CSR's [csr2-cdn](https://pypi.org/project/csr2-cdn/) package.

Nothing about the game version is hard coded. On start the app finds the current branch by probing the CDN (and,
with a Player ID, asks which branch the game announces), loads that asset database and works everything out from
it. Asset databases are cached, so the app still opens offline.

## Pages

| Page | What it does |
|---|---|
| New Cars | **Needs your Player ID.** *Upcoming*: cars in the branch the game has staged for its next update (`PreemptiveDownloadDataBranchName` in `FeatureKillswitches`) that aren't in the live one yet. *New this version*: cars in the live database that weren't in the newest database of the previous game version (e.g. 6.9 vs `6_8_0_Release_OTA_2`). Download them like any other car. |
| Global Libraries | CarPaintLibrary, CarInteriorLibrary, the calliper, livery, wrap, colour and plate libraries, GlobalTextures, the Tuner Stars libraries, CarMetadata and Localisation_EN, plus anything named like a livery-zone or livery-texture library. None are ticked by default; *Select needed* ticks the missing and outdated ones. |
| Car Assets | Search by in-game or CRDB name. A car's plan is its own bundles (`<key>_...`) plus every shared bundle they depend on (the model's `_shared` bundles, wheels and shadows borrowed from other cars, a variant's base model, livery textures). Untick any row you don't want. Select several cars with Ctrl/Shift to download them together. |
| Scenes | Every `assets_scene_*` bundle: garage, workshop, showroom, crew hangout and each race track. None are pre-selected (some are ~100 MB). |
| Settings | Display (in-game or CRDB names), save folder, Player ID, keep older versions, parallel downloads, reconnect. |

Each table shows whether the file on disk is **Current** (right version and size), needs an **Update** (an older
version is there) or is **Missing**. Downloads skip anything current, stream through a `.part` file, can be
cancelled, and are logged (Show log).

## Where files go

Bundles keep the game's own names, `<code>.ASTC.<version>`:

    <save folder>/<CRDB key>/          a car's own and shared bundles
    <save folder>/global_libraries/    the libraries
    <save folder>/scenes/              the scenes

When a bundle is updated, its older copy is moved to `_old_bundles/` beside it (or deleted, if you turn off
*Keep older versions*), so two versions never sit side by side.

## First run

The splash screen connects to the CDN, then setup asks:

1. **How cars should be listed**: in-game names (CRDB name underneath) or CRDB names.
2. **Where to save** the files.
3. **Your Player ID** (optional). It is only sent to the game's own metadata service, and unlocks New Cars and
   the announced live branch. You can add it later from the New Cars page or Settings.

**Settings and cache** are kept in `%APPDATA%\CSR2 Asset Downloader\` on Windows and
`~/.config/csr2-asset-downloader/` on Linux.

## Run / build

    pip install -r requirements.txt
    python app.py

Nuitka builds one file (`dist-nuitka/CSR2 Asset Downloader(.exe)`):

| | Windows | Linux |
|---|---|---|
| Script | `build_nuitka_windows.bat` | `./build_nuitka_linux.sh` |
| Needs | Python 3.10–3.13; a C compiler (Nuitka offers to fetch MinGW64) | gcc, patchelf (`sudo pacman -S --needed gcc patchelf ccache`) |

`python build_nuitka.py --folder` builds a folder instead (starts faster).

**GitHub Actions** (`.github/workflows/build.yml`): every push runs the tests and builds with Nuitka on Windows
and Linux; the files are attached to the run. When a push to `main` carries a `VERSION` (in
`assetdl/__init__.py`) that hasn't been released yet, both builds are published as release `v<version>`.

Tests: `python -m unittest discover -s tests` (set `QT_QPA_PLATFORM=offscreen` without a display).

## Updates

The built app checks this repo's latest GitHub release a few seconds after it starts (Settings > Updates turns that
off, and has a *Check now* button). When the release is newer than the app, it shows the release notes and offers:

- **Update now**: downloads this system's file from the release, checks it against the size and SHA-256 digest
  GitHub reports, swaps it in place of the running program and restarts. On Windows the old `.exe` is renamed to
  `.exe.old` first (a running program can't be overwritten) and deleted on the next start. Older versions'
  unpacked files in the cache folder are removed then too.
- **Release page**, **Later**, or **Skip this version** (it won't ask again until a newer one comes out).

If the app's folder isn't writable, or you run it from source, it links to the release page instead.

**To ship an update:** raise `VERSION` in `assetdl/__init__.py`, commit and push to `main`. The workflow builds both
systems and publishes release `v<VERSION>`; every copy of the app picks it up on its next start. The updater
finds its file by name, so keep the release file names (`CSR2-Asset-Downloader-windows.exe`,
`CSR2-Asset-Downloader-linux-x86_64.tar.gz`) and `REPO` in `assetdl/__init__.py` as they are.

## Credits

Made by BonkOfEngland. Special thanks to Nitro4CSR for csr2-cdn.

Not affiliated with, endorsed by or connected to Zynga, NaturalMotion or any of their subsidiaries.
