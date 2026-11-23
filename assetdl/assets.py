"""What to download, worked out from the asset database alone (no names or versions are guessed).

The car planning is ported from csr2_master_renderer's car_download.py. Files go to:

    <save folder>/<CRDB key>/          a car's own bundles and the shared bundles they depend on
    <save folder>/global_libraries/    CarPaintLibrary, CarInteriorLibrary, ... Localisation_EN
    <save folder>/scenes/              assets_scene_* (garage, workshop, showroom, tracks ...)

Every file keeps the game's own name, <code>.ASTC.<version>. When an asset is updated, its older copy is moved
to _old_bundles/ beside it (or deleted), so two versions never sit side by side.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional

QUALITY = "ASTC"

LIBRARIES = ("CarPaintLibrary", "CarInteriorLibrary", "CarCalliperLibrary", "CarLiveryLibrary", "CarLiverySetLibrary",
             "LiveryZonesSetLibrary", "CarWrapLibrary", "CarColorLibrary", "CarLicensePlateLibrary",
             "GlobalTextures", "GlobalLiveryTextures",
             "CarMetadata",                 # the CarDatabase: each car's size class
             # Tuner Stars (..TNR<n>_<year>) cars: their paint, interior, callipers, liveries, rims and tyres
             "CarTunerStarsPaintLibrary", "CarTunerStarsInteriorLibrary", "CarTunerStarsCalliperLibrary",
             "CarTunerStarsLiveryLibrary", "CarTunerStarsLiverySetLibrary", "CarTunerStarsRimLibrary",
             "CarTunerStarsTireLibrary", "TNRGlobalTireTextures", "TNRGlobalLiveryTextures",
             "Localisation_EN")             # the game's English text: the cars' and brands' names
LIBRARY_HINTS = ("liveryzones", "liverytextures")      # any asset named like these is a library too (renamed / split)
SCENE_PREFIX = "assets_scene"
LEGENDS_MANIFEST = "_RestorationManifest"

CAR_KEY = re.compile(r"^[A-Za-z0-9]+_[A-Za-z0-9]+_\d{4}$")          # Make_Model_Year: a CRDB key
MODEL = re.compile(r"^([A-Za-z0-9]+)_([A-Za-z0-9]+)_(\d{4})_")      # the model a bundle belongs to

LIBRARIES_DIR = "global_libraries"
SCENES_DIR = "scenes"
OLD_DIR = "_old_bundles"


class PlanError(RuntimeError):
    pass


# --- libraries and scenes --------------------------------------------------------------------------------------
def owner_key(code: str) -> str:
    """The CRDB key a bundle would belong to as an OWN bundle: its first three name parts (Make_Model_Year)."""
    return "_".join(code.split("_")[:3])


def library_assets(database) -> list:
    """The libraries this database has: the known names, plus any asset named like a livery-zone or livery-texture
    library."""
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
    """Every assets_scene_* bundle: garage, workshop, showroom, the tracks ..."""
    return sorted((a for a in database.assets if a.code.lower().startswith(SCENE_PREFIX)),
                  key=lambda a: a.code.lower())


def scene_label(code: str) -> str:
    """assets_scene_track_route66_night -> 'Track: Route66 Night'."""
    rest = code[len(SCENE_PREFIX):].strip("_")
    words = rest.split("_")
    if words and words[0].lower() == "track" and len(words) > 1:
        return "Track: " + " ".join(w.capitalize() for w in words[1:])
    return " ".join(w.capitalize() for w in words) or code


# --- cars --------------------------------------------------------------------------------------------------------
def car_keys(database) -> List[str]:
    """Every car in the database: the CRDB key of each <key>_common bundle, and each Legends car (a bare <key>
    bundle with a <key>_RestorationManifest: no _common)."""
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
    """A shared bundle of the car's model: same make and year, and the car's model name starts with the bundle's
    (Ferrari_296Speciale_2026_shared1 belongs to Ferrari_296SpecialeReward_2026)."""
    m = MODEL.match(code)
    k = key.split("_")
    if not m or len(k) != 3:
        return False
    make, model, year = m.groups()
    return make.lower() == k[0].lower() and year == k[2] and k[1].lower().startswith(model.lower())


def variant_base(key: str) -> Optional[str]:
    """The base car of a variant key: Pagani_UtopiaRoadsterRewardRecycled_2024 -> Pagani_UtopiaRoadster_2024."""
    m = re.match(r"^(.+?)(RewardRecycled|Recycled|Reward)(_\d{4})$", key)
    return m.group(1) + m.group(3) if m else None


def car_plan(database, key: str, keys: Optional[Iterable[str]] = None) -> Dict[str, list]:
    """{'own': [...], 'shared': [...]}: the Asset objects a car needs. ``keys`` (car_keys(database)) saves a scan
    when planning many cars."""
    prefix = key.lower() + "_"
    keys = {k.lower() for k in (keys if keys is not None else car_keys(database))}
    own = [a for a in database.assets.search(key) if a.code.lower().startswith(prefix)]
    if key in database.assets and own and any(a.code.endswith(LEGENDS_MANIFEST) for a in own):
        own.append(database.assets[key])                # a Legends car's base: the bare <key> bundle
    if not own:
        raise PlanError(f"no assets named {key}_... in this asset database")

    def model_bundle(code: str) -> bool:
        return not code.lower().startswith(prefix) and belongs_to_model(code, key)

    # 1. what the car's bundles depend on - Unity's own record. Another car's bundles it depends on are needed too
    #    (wheels, shadows, shared bodies), all but that car's own visuals (_common) and icon.
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
    # 1b. a variant (..RewardRecycled_2024, ..Reward_2024) is drawn with its BASE car's model
    base = variant_base(key)
    if (base and base.lower() in keys
            and not any(a.code.lower().startswith(base.lower() + "_") for a in shared)):
        for asset in database.assets.search(base + "_"):
            code = asset.code.lower()
            if (asset.code not in seen and code.startswith(base.lower() + "_")
                    and not code.endswith(("_common", "_icon"))):
                seen.add(asset.code)
                shared.append(asset)
    # 2. no dependencies listed (some builds): the model's bundles by name, leaving out other cars' own bundles
    if not shared:
        for asset in database.assets.search(key.split("_")[0] + "_"):
            other = owner_key(asset.code).lower()
            if asset.code not in seen and model_bundle(asset.code) and not (other in keys and other != key.lower()):
                seen.add(asset.code)
                shared.append(asset)
    # 3. anything else the car's bundles depend on that is not another car, a library or a scene (e.g. the
    #    textures behind <key>_LiveryAndSwatchTexture)
    skip = {a.code.lower() for a in library_assets(database)}
    for asset in own:
        for dep in asset.walk_dependencies():
            c = dep.code.lower()
            if (dep.code not in seen and c not in skip and not CAR_KEY.match(owner_key(dep.code))
                    and not c.startswith(SCENE_PREFIX)):
                seen.add(dep.code)
                shared.append(dep)
    return {"own": sorted(own, key=lambda a: a.code.lower()), "shared": sorted(shared, key=lambda a: a.code.lower())}


# --- files on disk -----------------------------------------------------------------------------------------------
CURRENT, UPDATE, MISSING = "current", "update", "missing"


def file_state(folder: Path, asset) -> str:
    """CURRENT when <code>.ASTC.<version> is there at the database's size, UPDATE when only another version is,
    else MISSING."""
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
    """Older copies of ``asset`` in ``folder`` go to _old_bundles/ (keep) or are deleted."""
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
