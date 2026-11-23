from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
_CONFIG = tempfile.mkdtemp(prefix="csr2assets-test-")
os.environ["CSR2_ASSETS_CONFIG"] = _CONFIG

from csr2cdn import AssetDatabase

from assetdl import assets as A
from assetdl.config import Settings
from assetdl.session import NEW, UPCOMING, Catalog, NewCars, Session, apply_new_cars


def make_db() -> AssetDatabase:
    db = AssetDatabase.from_json([{"branch_name": "6_9_0_Release", "version": "100"}, []])
    add = lambda code, deps=(), size=10, version="3": db.add_asset(
        code, version=version, dependencies=list(deps), sizes={"High": size, "ASTC": size})
    add("Ferrari_296Speciale_2026_shared1", size=100)
    add("Ferrari_296Speciale_2026_Wheel_1_shared2")
    add("Ferrari_296SpecialeReward_2026_common", ["ferrari_296speciale_2026_shared1"])
    add("Ferrari_296SpecialeReward_2026_loda", ["Ferrari_296Speciale_2026_Wheel_1_shared2", "CarPaintLibrary"])
    add("Ferrari_296SpecialeReward_2026_icon")
    add("Ferrari_296Speciale_2026_common", ["Ferrari_296Speciale_2026_shared1"])
    add("Ferrari_296Speciale_2026_icon")
    add("Pagani_Zonda_2005_common")
    add("CarPaintLibrary", size=50)
    add("Localisation_EN")
    add("CarFancyLiveryZonesSet")
    add("assets_scene_garage", size=500)
    add("assets_scene_track_route66_night", size=800)
    return db


class PlanTests(unittest.TestCase):
    def setUp(self):
        self.db = make_db()

    def test_car_keys(self):
        self.assertEqual(A.car_keys(self.db), ["Ferrari_296Speciale_2026", "Ferrari_296SpecialeReward_2026",
                                               "Pagani_Zonda_2005"])

    def test_plan_takes_shared_and_dependencies_not_libraries(self):
        plan = A.car_plan(self.db, "Ferrari_296SpecialeReward_2026")
        own = [a.code for a in plan["own"]]
        shared = [a.code for a in plan["shared"]]
        self.assertIn("Ferrari_296SpecialeReward_2026_loda", own)
        self.assertIn("Ferrari_296SpecialeReward_2026_icon", own)
        self.assertIn("Ferrari_296Speciale_2026_shared1", shared)
        self.assertIn("Ferrari_296Speciale_2026_Wheel_1_shared2", shared)
        self.assertNotIn("CarPaintLibrary", shared)
        self.assertNotIn("Ferrari_296Speciale_2026_common", shared)
        self.assertNotIn("Ferrari_296Speciale_2026_icon", shared)

    def test_plan_unknown_car(self):
        with self.assertRaises(A.PlanError):
            A.car_plan(self.db, "Nope_Nothing_2020")

    def test_libraries_and_scenes(self):
        libs = [a.code for a in A.library_assets(self.db)]
        self.assertEqual(libs, ["CarPaintLibrary", "Localisation_EN", "CarFancyLiveryZonesSet"])
        scenes = [a.code for a in A.scene_assets(self.db)]
        self.assertEqual(scenes, ["assets_scene_garage", "assets_scene_track_route66_night"])
        self.assertEqual(A.scene_label("assets_scene_track_route66_night"), "Track: Route66 Night")
        self.assertEqual(A.scene_label("assets_scene_garage"), "Garage")


class FileTests(unittest.TestCase):
    def test_states_and_retire(self):
        db = make_db()
        asset = db.assets["CarPaintLibrary"]
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            self.assertEqual(A.file_state(folder, asset), A.MISSING)
            (folder / "CarPaintLibrary.ASTC.2").write_bytes(b"old")
            self.assertEqual(A.file_state(folder, asset), A.UPDATE)
            (folder / asset.filename()).write_bytes(b"x" * 49)
            self.assertEqual(A.file_state(folder, asset), A.UPDATE)
            (folder / asset.filename()).write_bytes(b"x" * 50)
            self.assertEqual(A.file_state(folder, asset), A.CURRENT)
            A.retire_old_versions(folder, asset, keep=True)
            self.assertFalse((folder / "CarPaintLibrary.ASTC.2").exists())
            self.assertTrue((folder / A.OLD_DIR / "CarPaintLibrary.ASTC.2").exists())
            (folder / "CarPaintLibrary.ASTC.1").write_bytes(b"older")
            A.retire_old_versions(folder, asset, keep=False)
            self.assertFalse((folder / "CarPaintLibrary.ASTC.1").exists())
            self.assertTrue((folder / asset.filename()).exists())

    def test_human_size(self):
        self.assertEqual(A.human_size(512), "512 B")
        self.assertEqual(A.human_size(1536), "1.5 KB")


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.cat = Catalog()
        self.cat.add_keys(["Ferrari_296Speciale_2026", "Pagani_Zonda_2005"])
        self.cat.add_translations([{"model_key": "Ferrari_296Speciale_2026", "MEDIUM": "296 Spéciale"}])

    def test_search_by_either_name(self):
        self.assertEqual([c.crdb for c in self.cat.search("296 speciale", False)], ["Ferrari_296Speciale_2026"])
        self.assertEqual([c.crdb for c in self.cat.search("zonda", True)], ["Pagani_Zonda_2005"])
        self.assertEqual(len(self.cat.search("", False)), 2)

    def test_labels(self):
        car = self.cat.cars["Ferrari_296Speciale_2026"]
        self.assertEqual(car.label(False), ("296 Spéciale", "Ferrari_296Speciale_2026"))
        self.assertEqual(car.label(True), ("Ferrari_296Speciale_2026", "296 Spéciale"))

    def test_new_car_tags(self):
        session = Session()
        session.catalog = self.cat
        apply_new_cars(session, NewCars(checked=True, upcoming=["Koenigsegg_Sadair_2027"],
                                        recent=["Pagani_Zonda_2005"]))
        self.assertEqual(self.cat.cars["Koenigsegg_Sadair_2027"].tag, UPCOMING)
        self.assertEqual(self.cat.cars["Pagani_Zonda_2005"].tag, NEW)
        self.assertEqual(self.cat.cars["Ferrari_296Speciale_2026"].tag, "")


class SettingsTests(unittest.TestCase):
    def test_round_trip(self):
        s = Settings(player_id=" 12 34 ", show_crdb=True, workers=3)
        self.assertEqual(s.player_id, "1234")
        self.assertEqual(s.workers, 8)
        s.save()
        loaded = Settings.load()
        self.assertTrue(loaded.show_crdb)
        self.assertEqual(loaded.player_id, "1234")
        self.assertEqual(loaded.root, Path(loaded.save_dir))


class WindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        from assetdl.ui import theme
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setStyleSheet(theme.QSS)

    def test_main_window_and_dialogs(self):
        from assetdl.ui.main_window import MainWindow
        from assetdl.ui.setup import SetupDialog
        from assetdl.ui.splash import Splash
        settings = Settings(setup_done=True)
        session = Session()
        session.warnings.append("offline in tests")
        window = MainWindow(settings, session)
        for i in range(5):
            window._nav(i)
        self.assertEqual(window.new_stack.currentIndex(), 0)
        window.close()
        SetupDialog(Settings()).close()
        Splash().close()

    def test_tables_with_a_database(self):
        from assetdl.ui.main_window import MainWindow
        db = make_db()
        session = Session()
        session.database = db
        session.keys = A.car_keys(db)
        session.catalog.add_keys(session.keys)
        with tempfile.TemporaryDirectory() as tmp:
            window = MainWindow(Settings(setup_done=True, save_dir=tmp), session)
            self.assertEqual(len(window.lib_table.rows), 3)
            self.assertEqual(len(window.scene_table.rows), 2)
            self.assertEqual(len(window.lib_table.checked_jobs()), 0)
            window.lib_table.check("needed")
            self.assertEqual(len(window.lib_table.checked_jobs()), 3)
            self.assertEqual(len(window.scene_table.checked_jobs()), 0)
            window.search.setText("296SpecialeReward")
            window._run_search()
            window.list.setCurrentIndex(window.model.index(0))
            self.assertGreater(len(window.car_table.rows), 2)
            window.close()


if __name__ == "__main__":
    unittest.main()
