from __future__ import annotations

import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional

from assetdl.assets import CURRENT, QUALITY, file_state, human_size, retire_old_versions


class Cancelled(Exception):
    pass


@dataclass
class Job:
    asset: object
    folder: Path


@dataclass
class Summary:
    downloaded: List[str] = field(default_factory=list)
    current: List[str] = field(default_factory=list)
    failed: Dict[str, str] = field(default_factory=dict)
    cancelled: bool = False
    bytes: int = 0

    def text(self) -> str:
        parts = [f"{len(self.downloaded)} downloaded ({human_size(self.bytes)})",
                 f"{len(self.current)} already current"]
        if self.failed:
            parts.append(f"{len(self.failed)} failed")
        return ", ".join(parts) + (" - cancelled" if self.cancelled else "")


def dedupe(jobs: List[Job]) -> List[Job]:
    seen, out = set(), []
    for job in jobs:
        key = (str(Path(job.folder).resolve()), job.asset.code.lower(), str(job.asset.version))
        if key not in seen:
            seen.add(key)
            out.append(job)
    return out


def _fetch(cdn, job: Job, add_bytes: Callable[[int], None], stop: threading.Event) -> str:
    if stop.is_set():
        raise Cancelled()
    asset, folder = job.asset, Path(job.folder)
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / asset.filename(QUALITY)
    temporary = target.with_name(target.name + ".part")
    url = cdn.asset_url(asset.code, asset.version, None, QUALITY)
    response = cdn._get(url, stream=True)
    got = 0
    try:
        with open(temporary, "wb") as handle:
            for chunk in response.iter_content(chunk_size=1 << 16):
                if stop.is_set():
                    raise Cancelled()
                if chunk:
                    handle.write(chunk)
                    got += len(chunk)
                    add_bytes(len(chunk))
    except BaseException:
        response.close()
        add_bytes(-got)
        try:
            temporary.unlink()
        except OSError:
            pass
        raise
    response.close()
    expected = asset.size(QUALITY)
    if expected and got != expected:
        temporary.unlink(missing_ok=True)
        add_bytes(-got)
        raise IOError(f"got {got} bytes, the database says {expected}")
    os.replace(temporary, target)
    return target.name


def run_jobs(cdn, jobs: List[Job], *, workers: int = 8, keep_old: bool = True,
             report: Optional[Callable[[str, float], None]] = None,
             log: Optional[Callable[[str], None]] = None,
             stop: Optional[threading.Event] = None) -> Summary:
    report = report or (lambda t, f: None)
    log = log or (lambda m: None)
    stop = stop or threading.Event()
    summary = Summary()
    jobs = dedupe(jobs)
    todo = []
    for job in jobs:
        if file_state(job.folder, job.asset) == CURRENT:
            summary.current.append(job.asset.filename(QUALITY))
        else:
            todo.append(job)
    total = sum(max(0, j.asset.size(QUALITY)) for j in todo) or 1
    if not todo:
        report("Everything is already current", 1.0)
    else:
        log(f"Downloading {len(todo)} file(s), {human_size(total)}"
            + (f" ({len(summary.current)} already current)" if summary.current else ""))
    lock = threading.Lock()
    state = {"bytes": 0, "done": 0}

    def add_bytes(n: int):
        with lock:
            state["bytes"] += n
            b, d = state["bytes"], state["done"]
        report(f"Downloading {d}/{len(todo)}  ·  {human_size(b)} of {human_size(total)}", min(1.0, b / total))

    if todo:
        with ThreadPoolExecutor(max(1, workers), thread_name_prefix="download") as pool:
            futures = {pool.submit(_fetch, cdn, job, add_bytes, stop): job for job in todo}
            for future in as_completed(futures):
                job = futures[future]
                with lock:
                    state["done"] += 1
                try:
                    name = future.result()
                except Cancelled:
                    continue
                except Exception as exc:
                    summary.failed[job.asset.code] = str(exc) or type(exc).__name__
                    log(f"FAILED {job.asset.code}: {summary.failed[job.asset.code]}")
                    continue
                summary.downloaded.append(name)
                summary.bytes += job.asset.size(QUALITY)
                log(f"  {Path(job.folder).name}/{name}  ({human_size(job.asset.size(QUALITY))})")
                retire_old_versions(job.folder, job.asset, keep=keep_old, log=lambda m: log("  " + m))
                add_bytes(0)
    summary.cancelled = stop.is_set()
    return summary
