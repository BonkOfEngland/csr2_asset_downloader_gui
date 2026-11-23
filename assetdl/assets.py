from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional

QUALITY = "ASTC"

LIBRARIES = ("CarPaintLibrary", "CarInteriorLibrary", "CarCalliperLibrary", "CarLiveryLibrary", "CarLiverySetLibrary",
             "LiveryZonesSetLibrary", "CarWrapLibrary", "CarColorLibrary", "CarLicensePlateLibrary",
             "GlobalTextures", "GlobalLiveryTextures",
             "CarMetadata",
             "CarTunerStarsPaintLibrary", "CarTunerStarsInteriorLibrary", "CarTunerStarsCalliperLibrary",
             "CarTunerStarsLiveryLibrary", "CarTunerStarsLiverySetLibrary", "CarTunerStarsRimLibrary",
             "CarTunerStarsTireLibrary", "TNRGlobalTireTextures", "TNRGlobalLiveryTextures",
             "Localisation_EN")
LIBRARY_HINTS = ("liveryzones", "liverytextures")
SCENE_PREFIX = "assets_scene"
LEGENDS_MANIFEST = "_RestorationManifest"

CAR_KEY = re.compile(r"^[A-Za-z0-9]+_[A-Za-z0-9]+_\d{4}$")
MODEL = re.compile(r"^([A-Za-z0-9]+)_([A-Za-z0-9]+)_(\d{4})_")

LIBRARIES_DIR = "global_libraries"
SCENES_DIR = "scenes"
OLD_DIR = "_old_bundles"


class PlanError(RuntimeError):
    pass


def owner_key(code: str) -> str:
    return "_".join(code.split("_")[:3])


def library_assets(database) -> list:
    found, seen = [], set()
    for name in LIBRARIES:
        asset = database.assets.get(name)
        if asset is not None:
            found.append(asset)
            seen.add(asset.code.lower())
    for asset in database.assets:
        code = asset.code.lower()
        if code not in seen and any(h in code for h in LIBRARY_HINTS) and not CAR_KEY.match(owner_key(asset.code)):
            found.append(asset)
            seen.add(code)
    return found


def scene_assets(database) -> list:
    return sorted((a for a in database.assets if a.code.lower().startswith(SCENE_PREFIX)),
                  key=lambda a: a.code.lower())


def scene_label(code: str) -> str:
    rest = code[len(SCENE_PREFIX):].strip("_")
    words = rest.split("_")
    if words and words[0].lower() == "track" and len(words) > 1:
        return "Track: " + " ".join(w.capitalize() for w in words[1:])
    return " ".join(w.capitalize() for w in words) or code


def car_keys(database) -> List[str]:
    keys = set()
    codes = {a.code for a in database.assets}
    for asset in database.assets:
        code = asset.code
        if code.lower().endswith("_common"):
            key = code[: -len("_common")]
            if CAR_KEY.match(key):
                keys.add(key)
        elif code.endswith(LEGENDS_MANIFEST):
            key = code[: -len(LEGENDS_MANIFEST)]
            if CAR_KEY.match(key) and key in codes:
                keys.add(key)
    return sorted(keys, key=lambda k: (k.split("_")[0].lower(), len(k), k.lower()))


def belongs_to_model(code: str, key: str) -> bool:
    m = MODEL.match(code)
    k = key.split("_")
    if not m or len(k) != 3:
        return False
    make, model, year = m.groups()
    return make.lower() == k[0].lower() and year == k[2] and k[1].lower().startswith(model.lower())


def variant_base(key: str) -> Optional[str]:
    m = re.match(r"^(.+?)(RewardRecycled|Recycled|Reward)(_\d{4})$", key)
    return m.group(1) + m.group(3) if m else None


def car_plan(database, key: str, keys: Optional[Iterable[str]] = None) -> Dict[str, list]:
    prefix = key.lower() + "_"
    keys = {k.lower() for k in (keys if keys is not None else car_keys(database))}
    own = [a for a in database.assets.search(key) if a.code.lower().startswith(prefix)]
    if key in database.assets and own and any(a.code.endswith(LEGENDS_MANIFEST) for a in own):
        own.append(database.assets[key])
    if not own:
        raise PlanError(f"no assets named {key}_... in this asset database")

    def model_bundle(code: str) -> bool:
        return not code.lower().startswith(prefix) and belongs_to_model(code, key)

    shared, seen = [], {a.code for a in own}
    for asset in own:
        for dep in asset.walk_dependencies():
            other = owner_key(dep.code).lower()
            other_car = (other != key.lower() and not dep.code.lower().startswith(prefix)
                         and re.match(r"^[A-Za-z0-9]+_[A-Za-z0-9]+_\d{4}_", dep.code) is not None)
            if (dep.code not in seen and (model_bundle(dep.code) or other_car)
                    and not (other_car and dep.code.lower().endswith(("_common", "_icon")))):
                seen.add(dep.code)
                shared.append(dep)
    base = variant_base(key)
    if (base and base.lower() in keys
            and not any(a.code.lower().startswith(base.lower() + "_") for a in shared)):
        for asset in database.assets.search(base + "_"):
            code = asset.code.lower()
            if (asset.code not in seen and code.startswith(base.lower() + "_")
                    and not code.endswith(("_common", "_icon"))):
                seen.add(asset.code)
                shared.append(asset)
    if not shared:
        for asset in database.assets.search(key.split("_")[0] + "_"):
            other = owner_key(asset.code).lower()
            if asset.code not in seen and model_bundle(asset.code) and not (other in keys and other != key.lower()):
                seen.add(asset.code)
                shared.append(asset)
    skip = {a.code.lower() for a in library_assets(database)}
    for asset in own:
        for dep in asset.walk_dependencies():
            c = dep.code.lower()
            if (dep.code not in seen and c not in skip and not CAR_KEY.match(owner_key(dep.code))
                    and not c.startswith(SCENE_PREFIX)):
                seen.add(dep.code)
                shared.append(dep)
    return {"own": sorted(own, key=lambda a: a.code.lower()), "shared": sorted(shared, key=lambda a: a.code.lower())}


CURRENT, UPDATE, MISSING = "current", "update", "missing"


def file_state(folder: Path, asset) -> str:
    folder = Path(folder)
    path = folder / asset.filename(QUALITY)
    if path.is_file():
        expected = asset.size(QUALITY)
        if not expected or path.stat().st_size == expected:
            return CURRENT
    try:
        if any(p.is_file() for p in folder.glob(f"{glob_escape(asset.code)}.{QUALITY}.*")):
            return UPDATE
    except OSError:
        pass
    return MISSING


def glob_escape(text: str) -> str:
    return re.sub(r"([\[\]*?])", r"[\1]", text)


def retire_old_versions(folder: Path, asset, keep: bool = True, log: Callable[[str], None] = lambda _m: None) -> None:
    folder = Path(folder)
    current = asset.filename(QUALITY)
    pattern = re.compile(re.escape(asset.code) + r"\." + QUALITY + r"\.\d+$")
    try:
        others = [p for p in folder.iterdir() if p.is_file() and p.name != current and pattern.match(p.name)]
    except OSError:
        return
    for other in others:
        try:
            if keep:
                old = folder / OLD_DIR
                old.mkdir(exist_ok=True)
                shutil.move(str(other), str(old / other.name))
                log(f"older version moved to {OLD_DIR}: {other.name}")
            else:
                other.unlink()
                log(f"older version deleted: {other.name}")
        except OSError as exc:
            log(f"couldn't move the older {other.name} aside: {exc}")


def human_size(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} GB"
