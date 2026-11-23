# CSR2 Asset Downloader

Download CSR2 car bundles, global libraries and scenes.

## Download

Get the latest version from [Releases](https://github.com/BonkOfEngland/csr2_asset_downloader/releases/latest):

| System | File |
|---|---|
| Windows | `CSR2-Asset-Downloader-windows.exe` |
| Linux | `CSR2-Asset-Downloader-linux-x86_64.tar.gz` (unpack, then run `CSR2 Asset Downloader`) |

Windows SmartScreen may warn the first time because the app isn't code-signed: **More info > Run anyway**.

## Pages

| Page | What it does |
|---|---|
| New Cars | Cars coming in the next update, and cars added in the current game version. Needs your Player ID. |
| Global Libraries | Paint, interior, calliper, livery, wrap and plate libraries, Tuner Stars libraries, global textures and more. |
| Car Assets | Search by in-game or CRDB name and download a car's bundles. Select several cars with Ctrl/Shift to download them together. |
| Scenes | Garage, workshop, showroom, crew hangout and every race track. |
| Settings | Name display, save folder, Player ID, older versions, parallel downloads and updates. |

Each list shows whether a file you already have is **Current**, needs an **Update**, or is **Missing**. A car's
missing bundles are ticked for you; libraries and scenes start unticked. **Select needed** ticks everything missing
or outdated.

## Where files go

    <save folder>/<CRDB key>/          a car's bundles
    <save folder>/global_libraries/    the libraries
    <save folder>/scenes/              the scenes

When a file is updated, the older copy is moved to `_old_bundles/` beside it. Turn off **Keep older versions** in
Settings to delete it instead.

## First run

Setup asks how cars should be listed (in-game or CRDB names), where to save files, and for your Player ID. The
Player ID is optional and only needed for New Cars; you can add it later.

## Updates

The app tells you when a new version is out and can update itself. You can turn the check off, or check by hand,
in Settings > Updates.

## Credits

Made by BonkOfEngland. Special thanks to Nitro4CSR.

Not affiliated with, endorsed by or connected to Zynga, NaturalMotion or any of their subsidiaries.
