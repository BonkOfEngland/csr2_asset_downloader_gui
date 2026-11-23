"""The updater, with GitHub faked: version checks, picking this system's file, the download checks and the swap."""

from __future__ import annotations

import hashlib
import io
import os
import sys
import tarfile
import tempfile
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("CSR2_ASSETS_CONFIG", tempfile.mkdtemp(prefix="csr2assets-test-"))

from assetdl import VERSION, updater as U  # noqa: E402


class FakeResponse:
    def __init__(self, status=200, data=None, body=b""):
        self.status_code, self._data, self.body = status, data, body
        self.headers = {"Content-Length": str(len(body))}

    def json(self):
        return self._data

    def iter_content(self, chunk_size=1):
        for i in range(0, len(self.body), 7):
            yield self.body[i:i + 7]

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FakeSession:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.urls = []

    def get(self, url, **kw):
        self.urls.append(url)
        return self.responses.pop(0)


def release(tag, assets=()):
    return {"tag_name": tag, "body": "## What's new\n- things", "html_url": f"https://github.com/x/y/releases/{tag}",
            "assets": list(assets)}


def bump(version: str, by: int = 1) -> str:
    parts = list(U.parse_version(version))
    parts[1] += by
    return ".".join(map(str, parts))


class VersionTests(unittest.TestCase):
    def test_parse_and_compare(self):
        self.assertEqual(U.parse_version("v1.2"), (1, 2, 0))
        self.assertEqual(U.parse_version("1.10.3-beta"), (1, 10, 3))
        self.assertEqual(U.parse_version("nightly"), ())
        self.assertTrue(U.is_newer("1.10.0", "1.9.9"))
        self.assertFalse(U.is_newer("v1.0.0", "1.0.0"))
        self.assertFalse(U.is_newer("garbage", "1.0.0"))

    def test_asset_for_each_system(self):
        assets = [{"name": U.WINDOWS_ASSET, "browser_download_url": "https://w", "size": 5,
                   "digest": "sha256:ABC"},
                  {"name": U.LINUX_ASSET, "browser_download_url": "https://l", "size": 6}]
        win = U.release_from_json(release("v2.0.0", assets), "win32")
        self.assertEqual((win.version, win.asset_url, win.size, win.sha256), ("2.0.0", "https://w", 5, "abc"))
        lin = U.release_from_json(release("v2.0.0", assets), "linux")
        self.assertEqual((lin.asset_url, lin.sha256), ("https://l", ""))
        self.assertEqual(U.release_from_json(release("v2.0.0", assets), "darwin").asset_url, "")


class CheckTests(unittest.TestCase):
    def test_newer_same_and_errors(self):
        newer = bump(VERSION)
        self.assertEqual(U.check(session=FakeSession(FakeResponse(data=release("v" + newer)))).version, newer)
        self.assertIsNone(U.check(session=FakeSession(FakeResponse(data=release("v" + VERSION)))))
        with self.assertRaisesRegex(U.UpdateError, "no releases"):
            U.check(session=FakeSession(FakeResponse(404)))
        with self.assertRaisesRegex(U.UpdateError, "rate limit"):
            U.check(session=FakeSession(FakeResponse(403)))


class DownloadTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def info(self, name, body, sha=True):
        return U.UpdateInfo("9.0.0", "v9.0.0", "", "https://page", name, "https://file", len(body),
                            hashlib.sha256(body).hexdigest() if sha else "")

    def test_windows_exe(self):
        body = b"MZ new program"
        new = U.download(self.info(U.WINDOWS_ASSET, body), folder=self.tmp,
                         session=FakeSession(FakeResponse(body=body)))
        self.assertEqual(new.read_bytes(), body)

    def test_linux_tar_takes_only_the_program(self):
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tar:
            for name, data in (("../evil", b"no"), (U.LINUX_MEMBER, b"\x7fELF new")):
                ti = tarfile.TarInfo(name)
                ti.size = len(data)
                tar.addfile(ti, io.BytesIO(data))
        body = buf.getvalue()
        new = U.download(self.info(U.LINUX_ASSET, body), folder=self.tmp,
                         session=FakeSession(FakeResponse(body=body)))
        self.assertEqual(new.read_bytes(), b"\x7fELF new")
        self.assertFalse((self.tmp.parent / "evil").exists())
        if sys.platform != "win32":
            self.assertTrue(os.access(new, os.X_OK))

    def test_checksum_and_size_are_checked(self):
        body = b"MZ new program"
        bad = self.info(U.WINDOWS_ASSET, body)
        bad.sha256 = "0" * 64
        with self.assertRaisesRegex(U.UpdateError, "checksum"):
            U.download(bad, folder=self.tmp, session=FakeSession(FakeResponse(body=body)))
        short = self.info(U.WINDOWS_ASSET, body)
        short.size += 1
        with self.assertRaisesRegex(U.UpdateError, "incomplete"):
            U.download(short, folder=self.tmp, session=FakeSession(FakeResponse(body=body)))
        self.assertEqual([p.name for p in self.tmp.iterdir()], [])      # nothing left behind

    def test_cancel(self):
        stop = threading.Event()
        stop.set()
        with self.assertRaises(U.Cancelled):
            U.download(self.info(U.WINDOWS_ASSET, b"x" * 20), folder=self.tmp, stop=stop,
                       session=FakeSession(FakeResponse(body=b"x" * 20)))

    def test_install_swaps_the_program(self):
        exe = self.tmp / "CSR2 Asset Downloader"
        exe.write_bytes(b"old")
        new = self.tmp / "new"
        new.write_bytes(b"new")
        self.assertEqual(U.install(new, exe), exe)
        self.assertEqual(exe.read_bytes(), b"new")
        self.assertFalse(new.exists())

    def test_not_compiled_means_no_self_update(self):
        ok, why = U.can_self_update()
        self.assertFalse(ok)
        self.assertIn("source", why)


if __name__ == "__main__":
    unittest.main()
