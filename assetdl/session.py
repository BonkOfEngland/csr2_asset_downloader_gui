from __future__ import annotations

import json
import os
import re
import tempfile
import threading
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional

from assetdl.assets import car_keys
from assetdl.config import Settings, cache_dir

Progress = Callable[[str, float], None]

NAMES_FILE = "car_names.json"
LAST_FILE = "last_database.json"
LOCALISATION_CODE = "Localisation_EN"

UPCOMING, NEW = "upcoming", "new"


def _fold(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^0-9a-z]+", " ", text.lower()).strip()


def short_error(exc: BaseException) -> str:
    text = str(exc).strip().splitlines()[0] if str(exc).strip() else type(exc).__name__
    return text if len(text) <= 160 else text[:157] + "..."


def _write_atomic(path: Path, text: str) -> None:
    with tempfile.NamedTemporaryFile("w", dir=path.parent, suffix=".tmp", delete=False,
                                     encoding="utf-8") as out:
        out.write(text)
        tmp = out.name
    os.replace(tmp, path)


@dataclass
class Car:
    crdb: str
    short: Optional[str] = None
    medium: Optional[str] = None
    long: Optional[str] = None
    tag: str = ""
    _blob: str = field(default="", repr=False)

    @property
    def game_name(self) -> Optional[str]:
        return self.medium or self.long or self.short

    def names(self) -> List[str]:
        return [n for n in dict.fromkeys((self.medium, self.long, self.short)) if n]

    def label(self, show_crdb: bool) -> tuple[str, str]:
        game = self.game_name
        if show_crdb or not game:
            return self.crdb, (game or "")
        return game, self.crdb

    def blob(self) -> str:
        if not self._blob:
            parts = [self.crdb, *self.names()]
            self._blob = " | ".join(_fold(p) for p in parts) + " | " + self.crdb.lower()
        return self._blob


class Catalog:
    def __init__(self):
        self.cars: Dict[str, Car] = {}
        self._sorted: Dict[bool, List[Car]] = {}

    def add_keys(self, keys, tag: str = "") -> None:
        for key in keys:
            car = self.cars.setdefault(key, Car(key))
            if tag and not car.tag:
                car.tag = tag
        self._sorted = {}

    def add_translations(self, records: List[dict], only_missing: bool = False) -> None:
        for row in records:
            car = self.cars.get(row.get("model_key") or "")
            if car is None or (only_missing and car.game_name):
                continue
            car.short, car.medium, car.long = row.get("SHORT"), row.get("MEDIUM"), row.get("LONG")
            car._blob = ""
        self._sorted = {}

    def sorted(self, show_crdb: bool) -> List[Car]:
        if show_crdb not in self._sorted:
            self._sorted[show_crdb] = sorted(self.cars.values(), key=lambda c: _fold(c.label(show_crdb)[0]))
        return self._sorted[show_crdb]

    def search(self, query: str, show_crdb: bool, cars: Optional[List[Car]] = None) -> List[Car]:
        everything = cars if cars is not None else self.sorted(show_crdb)
        folded = _fold(query)
        if not folded:
            return list(everything)
        words = folded.split()
        raw = query.strip().lower()
        hits = []
        for car in everything:
            if raw in car.crdb.lower() or all(w in car.blob() for w in words):
                main = _fold(car.label(show_crdb)[0])
                exact = folded == _fold(car.crdb) or any(folded == _fold(n) for n in car.names())
                rank = 0 if exact else 1 if main.startswith(folded) else 2
                hits.append((rank, car))
        hits.sort(key=lambda h: h[0])
        return [car for _, car in hits]


@dataclass
class NewCars:
    checked: bool = False
    live_branch: str = ""
    upcoming_branch: str = ""
    upcoming_database: object = None
    upcoming: List[str] = field(default_factory=list)
    since_branch: str = ""
    recent: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


class Session:
    def __init__(self):
        self.cdn = None
        self.database = None
        self.keys: List[str] = []
        self.catalog = Catalog()
        self.new_cars = NewCars()
        self.offline = False
        self.has_player_id = False
        self.warnings: List[str] = []
        self.notes: List[str] = []
        self._staged_names: Optional[list] = None

    @property
    def ready(self) -> bool:
        return self.database is not None

    def database_for(self, key: str):
        if self.new_cars.upcoming_database is not None and key in self.new_cars.upcoming:
            return self.new_cars.upcoming_database
        return self.database


def _probe_in_parallel(cdn, workers: int = 10):
    try:
        from csr2cdn.patterns import successors
        ask = cdn.try_database_version
        known: dict = {}
        lock = threading.Lock()

        def remembered(branch, strict=True):
            with lock:
                if branch in known:
                    return known[branch]
            answer = ask(branch, strict)
            with lock:
                known[branch] = answer
            return answer

        candidates = successors(cdn.base_branch, include_preemptive=bool(getattr(cdn, "allow_preemptive", True)))
        cdn.try_database_version = remembered
        with ThreadPoolExecutor(min(workers, len(candidates)) or 1, thread_name_prefix="cdn-probe") as pool:
            list(pool.map(lambda b: _quietly(remembered, b), candidates))
    except Exception:
        pass


def _quietly(fn, *args):
    try:
        return fn(*args)
    except Exception:
        return None


def _make_cdn(zid: Optional[str], **pins):
    from csr2cdn import CDN
    return CDN(zid=zid or None, probe=True, allow_preemptive=False, cache_dir=str(cache_dir() / "cdn"),
               timeout=25.0, **pins)


def connect(settings: Settings, session: Session, report: Progress) -> None:
    zid = settings.player_id or None
    last_path = cache_dir() / LAST_FILE
    try:
        last = json.loads(last_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        last = {}

    attempts = []
    if zid:
        attempts.append(("your Player ID", zid, {}))
    attempts.append(("the CDN probe", None, {}))
    if last.get("branch"):
        attempts.append((f"the last branch that worked ({last['branch']})", zid,
                         {"branch": last["branch"], **({"product_version": last["product_version"]}
                                                       if last.get("product_version") else {})}))
    for i, (how, attempt_zid, pins) in enumerate(attempts):
        report("Finding the current game version" if i == 0 else f"Trying {how}", 0.05 + 0.05 * i)
        try:
            cdn = _make_cdn(attempt_zid, **pins)
            if "branch" not in pins:
                _probe_in_parallel(cdn)
            branch = cdn.branch
            report(f"Loading the asset database ({branch})", 0.25)
            database = cdn.database
        except Exception as exc:
            session.warnings.append(f"Couldn't connect using {how}: {short_error(exc)}")
            continue
        session.cdn, session.database = cdn, database
        session.has_player_id = bool(attempt_zid)
        session.notes.append(f"Branch {branch}, asset database {database.version} ({len(database.assets)} assets)"
                             + (" - via your Player ID" if attempt_zid and not pins else ""))
        try:
            pv = cdn._product_version or (database.product_version and str(database.product_version))
            _write_atomic(last_path, json.dumps({"branch": branch, "database": str(database.version),
                                                 "product_version": pv or ""}))
        except Exception:
            pass
        if i > 0 and zid and attempt_zid is None:
            session.warnings.append("Your Player ID didn't work this time, so New Cars is unavailable. "
                                    "Check it in Settings.")
        return

    db_file = cache_dir() / "cdn" / "databases" / f"asset_database.{last.get('database')}.json"
    if last.get("database") and db_file.is_file():
        from csr2cdn import AssetDatabase
        try:
            database = AssetDatabase.load(db_file)
            cdn = _make_cdn(zid, branch=last.get("branch") or None,
                            **({"product_version": last["product_version"]} if last.get("product_version") else {}))
            cdn.use_database(database)
            session.cdn, session.database, session.offline = cdn, database, True
            session.warnings.append(f"Offline: showing the saved asset database {database.version}. "
                                    "Downloads will fail until the CDN can be reached.")
        except Exception as exc:
            session.warnings.append(f"The saved asset database is unreadable: {short_error(exc)}")


def _load_names(cdn, database, cached: Optional[dict]) -> tuple[Optional[list], str]:
    from csr2cdn.localisation_bundle import decode_localisation_unityfs
    asset = database.assets.get(LOCALISATION_CODE)
    if asset is None:
        raise RuntimeError(f"{LOCALISATION_CODE} is not in the asset database")
    version = str(asset.version)
    if cached and cached.get("version") == version:
        return cached["records"], version
    translations = decode_localisation_unityfs(cdn.download_asset(asset))
    records = [{"model_key": r.model_key, "SHORT": r.short, "MEDIUM": r.medium, "LONG": r.long}
               for r in translations.records]
    return records, version


def load_names(session: Session, report: Progress) -> None:
    report("Getting car names", 0.55)
    names_path = cache_dir() / NAMES_FILE
    try:
        cached = json.loads(names_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        cached = None
    records = None
    if not session.offline:
        try:
            records, version = _load_names(session.cdn, session.database, cached)
            if not cached or cached.get("version") != version:
                _write_atomic(names_path, json.dumps({"version": version, "records": records}))
                session.notes.append(f"Car names: {len(records)} from {LOCALISATION_CODE} v{version}")
        except Exception as exc:
            session.warnings.append(f"Couldn't update the in-game car names: {short_error(exc)}")
    if records is None and cached:
        records = cached.get("records") or []
        session.notes.append(f"Car names: {len(records)} (saved copy)")
    if records:
        session.catalog.add_translations(records)


def previous_release(cdn, database) -> Optional[tuple[str, str]]:
    from csr2cdn import parse_branch
    from csr2cdn.patterns import build_branch
    current = parse_branch(str(database.branch_name or cdn.branch))
    if current is None or current.minor == 0:
        return None
    start = build_branch((current.major, current.minor - 1, 0))
    found = cdn.probe_branches(branch=start, allow_preemptive=False)
    best = None
    for branch, version in found.items():
        parsed = parse_branch(branch)
        if (parsed is not None and (parsed.major, parsed.minor) == (current.major, current.minor - 1)
                and int(version) < int(database.version) and (best is None or int(version) > int(best[1]))):
            best = (branch, str(version))
    return best


def find_new_cars(session: Session, report: Progress, frac=(0.7, 0.95)) -> NewCars:
    cdn, database = session.cdn, session.database
    nc = NewCars(checked=True)
    live = set(session.keys)
    span = frac[1] - frac[0]

    report("Checking for upcoming cars", frac[0])
    try:
        names = cdn.branch_names()
        nc.live_branch = names.explicit
        nc.upcoming_branch = names.preemptive
        if names.preemptive:
            version = cdn.try_database_version(names.preemptive)
            if version is None:
                nc.notes.append(f"{names.preemptive} is announced but not on the CDN yet")
            elif int(version) <= int(database.version):
                nc.notes.append(f"{names.preemptive} (database {version}) is no newer than the live one")
            else:
                report(f"Loading the staged database ({names.preemptive})", frac[0] + span * 0.3)
                staged = cdn.get_database(version=version)
                nc.upcoming_database = staged
                nc.upcoming = sorted(set(car_keys(staged)) - live)
                nc.notes.append(f"Staged: {names.preemptive}, database {version}: {len(nc.upcoming)} new car(s)")
                try:
                    a, b = staged.assets.get(LOCALISATION_CODE), database.assets.get(LOCALISATION_CODE)
                    if nc.upcoming and a is not None and (b is None or str(a.version) != str(b.version)):
                        report("Getting the upcoming cars' names", frac[0] + span * 0.5)
                        records, _v = _load_names(cdn, staged, None)
                        nc.notes.append("Upcoming names from the staged Localisation_EN")
                        session._staged_names = records
                except Exception as exc:
                    nc.warnings.append(f"Couldn't read the upcoming cars' names: {short_error(exc)}")
        else:
            nc.notes.append("Nothing is staged for the next update right now")
    except Exception as exc:
        nc.warnings.append(f"Couldn't read the announced branches: {short_error(exc)}")

    report("Comparing with the previous game version", frac[0] + span * 0.7)
    try:
        prev = previous_release(cdn, database)
        if prev is None:
            nc.notes.append("No previous game version to compare with")
        else:
            nc.since_branch = prev[0]
            older = cdn.get_database(version=prev[1])
            nc.recent = sorted(live - set(car_keys(older)))
            nc.notes.append(f"New since {prev[0]} (database {prev[1]}): {len(nc.recent)} car(s)")
    except Exception as exc:
        nc.warnings.append(f"Couldn't compare with the previous game version: {short_error(exc)}")
    return nc


def apply_new_cars(session: Session, nc: NewCars) -> None:
    session.new_cars = nc
    for car in session.catalog.cars.values():
        if car.tag:
            car.tag = ""
    session.catalog.add_keys(nc.upcoming, UPCOMING)
    session.catalog.add_keys(nc.recent, NEW)
    staged = session._staged_names
    if staged:
        session.catalog.add_translations(staged, only_missing=True)


def open_session(settings: Settings, progress: Optional[Progress] = None) -> Session:
    report = progress or (lambda text, frac: None)
    session = Session()
    connect(settings, session, report)
    if session.database is None:
        report("Couldn't reach the game CDN", 1.0)
        return session
    report("Listing the cars", 0.45)
    session.keys = car_keys(session.database)
    session.catalog.add_keys(session.keys)
    load_names(session, report)
    if session.has_player_id and not session.offline:
        apply_new_cars(session, find_new_cars(session, report))
    report("Ready", 1.0)
    return session
