"""Install, update, and reject bad packages without touching a real data dir."""

from __future__ import annotations

import hashlib
import io
import json
import tempfile
import time
import unittest
import zipfile
from contextlib import redirect_stdout
from pathlib import Path

from music_tools_installer.__main__ import main
from music_tools_installer.catalog import load_catalog, parse_catalog
from music_tools_installer.installer import (
    app_dir,
    install_product,
    load_installed,
    pid_alive,
    read_pid,
    remove_product,
    run_product,
    stop_product,
)

ROOT = Path(__file__).resolve().parents[1]


def _zip(path: Path, files: dict[str, str]) -> str:
    with zipfile.ZipFile(path, "w") as archive:
        for name, text in files.items():
            archive.writestr(name, text)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _product(directory: Path, name: str, version: str, digest: str, entry: str | None = None):
    catalog = {
        "products": [
            {
                "id": "hoarder",
                "name": "Hoarder",
                "version": version,
                "url": str(directory / name),
                "sha256": digest,
                "entry": entry or "python -c \"print('hi')\"",
            }
        ]
    }
    return parse_catalog(catalog)[0]


class InstallerTests(unittest.TestCase):
    def test_example_catalog_lists_the_three_apps(self) -> None:
        products = {product.id: product for product in load_catalog(str(ROOT / "catalog.example.json"))}
        self.assertEqual(set(products), {"hoarder", "reroll", "resampler"})
        self.assertEqual(products["hoarder"].port, 8770)
        self.assertEqual(products["reroll"].port, 8000)
        self.assertEqual(products["resampler"].port, 8787)

    def test_install_update_and_keep_old_on_bad_hash(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            data = root / "data"
            first = _zip(root / "a.zip", {"marker.txt": "one"})
            product = _product(root, "a.zip", "1.0.0", first)
            self.assertEqual(install_product(product, data), "installed hoarder 1.0.0")
            self.assertEqual((app_dir(data, "hoarder") / "marker.txt").read_text(encoding="utf-8"), "one")

            again = _product(root, "a.zip", "1.0.0", first)
            self.assertIn("already installed", install_product(again, data))

            second = _zip(root / "b.zip", {"marker.txt": "two"})
            updated = _product(root, "b.zip", "1.1.0", second)
            install_product(updated, data)
            self.assertEqual((app_dir(data, "hoarder") / "marker.txt").read_text(encoding="utf-8"), "two")
            self.assertEqual(load_installed(data)["hoarder"]["version"], "1.1.0")

            bad = _product(root, "b.zip", "1.2.0", "a" * 64)
            with self.assertRaises(ValueError):
                install_product(bad, data)
            self.assertEqual((app_dir(data, "hoarder") / "marker.txt").read_text(encoding="utf-8"), "two")
            self.assertEqual(load_installed(data)["hoarder"]["version"], "1.1.0")

    def test_zip_slip_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            data = root / "data"
            package = root / "evil.zip"
            with zipfile.ZipFile(package, "w") as archive:
                info = zipfile.ZipInfo("../evil.txt")
                archive.writestr(info, "nope")
            digest = hashlib.sha256(package.read_bytes()).hexdigest()
            product = _product(root, "evil.zip", "1.0.0", digest)
            with self.assertRaises(ValueError):
                install_product(product, data)
            self.assertFalse((root / "evil.txt").exists())
            self.assertFalse((data / "evil.txt").exists())

    def test_run_stop_and_remove(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            data = root / "data"
            digest = _zip(root / "app.zip", {"marker.txt": "ok"})
            entry = 'python -c "import time; time.sleep(60)"'
            product = _product(root, "app.zip", "1.0.0", digest, entry=entry)
            install_product(product, data)
            pid: int | None = None
            try:
                self.assertIn("started", run_product(product, data))
                pid = read_pid(data, "hoarder")
                self.assertIsNotNone(pid)
                assert pid is not None
                self.assertTrue(pid_alive(pid))
                self.assertIn("stopped", stop_product("hoarder", data))
                for _ in range(25):
                    if not pid_alive(pid):
                        break
                    time.sleep(0.1)
                self.assertFalse(pid_alive(pid))
            finally:
                if pid is not None and pid_alive(pid):
                    stop_product("hoarder", data)
            self.assertIn("removed", remove_product("hoarder", data))
            self.assertFalse(app_dir(data, "hoarder").exists())
            self.assertNotIn("hoarder", load_installed(data))

    def test_cli_list(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            catalog = root / "catalog.json"
            catalog.write_text(json.dumps(json.loads((ROOT / "catalog.example.json").read_text(encoding="utf-8"))), encoding="utf-8")
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = main(["--catalog", str(catalog), "--data", str(root / "data"), "list"])
            self.assertEqual(code, 0)
            self.assertIn("hoarder", buf.getvalue())
            self.assertIn("not installed", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
