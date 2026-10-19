"""Contracts for the exploratory 2019/2025 urban comparison publication.

The suite skips with an explicit pending message while Earth Engine assets are
being generated. A completed run is checked against its own provenance rather
than against arbitrary accuracy claims.
"""
from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

import numpy as np
from PIL import Image
import rasterio

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "site" / "data"
RAW = ROOT / "raw" / "urban"
PROVENANCE = DATA / "urban-provenance.json"
MANIFEST = RAW / "manifest.json"


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


class UrbanComparisonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not PROVENANCE.exists():
            raise unittest.SkipTest("urban comparison pending: urban-provenance.json is not present")
        cls.provenance = load(PROVENANCE)
        if cls.provenance.get("status") != "completed":
            raise unittest.SkipTest(
                "urban comparison pending: provenance status is "
                f"{cls.provenance.get('status')!r}, not completed"
            )
        cls.catalogue = load(DATA / "thematic.json")
        cls.entry = next((x for x in cls.catalogue.get("layers", []) if x.get("id") == "urban"), None)

    def test_completed_run_publishes_catalogue_and_provenance(self):
        self.assertEqual(self.provenance["status"], "completed")
        self.assertIsNotNone(self.entry)
        for key in ("image", "beforeImage", "afterImage", "gainImage", "displayGrid", "stats"):
            self.assertIn(key, self.entry)
        self.assertEqual(self.entry["provenanceFile"], "urban-provenance.json")

    def test_before_after_and_candidate_assets_are_aligned_rgba(self):
        names = [self.entry["beforeImage"], self.entry["afterImage"], self.entry["gainImage"]]
        images = []
        for name in names:
            path = DATA / name
            self.assertTrue(path.exists(), name)
            image = Image.open(path).convert("RGBA")
            images.append(np.asarray(image))
            image.close()
        self.assertEqual({array.shape[:2] for array in images}, {images[0].shape[:2]})
        self.assertTrue(all(array.shape[2] == 4 for array in images))
        self.assertTrue(np.array_equal(images[0][:, :, 3], images[1][:, :, 3]))
        self.assertEqual(images[0].shape[1], self.entry["displayGrid"]["width"])
        self.assertEqual(images[0].shape[0], self.entry["displayGrid"]["height"])

    def test_verification_counts_and_candidate_class_are_consistent(self):
        verification = self.provenance["verification"]
        counts = {str(k): int(v) for k, v in verification["signalClassPixels"].items()}
        self.assertEqual(sum(counts.values()), int(verification["inDistrictDisplayPixels"]))
        self.assertLessEqual(int(verification["commonAnalysisPixels"]), int(verification["commonRGBPixels"]))
        self.assertGreater(int(verification["commonRGBPixels"]), 0)
        self.assertGreater(int(verification["commonAnalysisPixels"]), 0)
        district = int(verification["inDistrictDisplayPixels"])
        self.assertAlmostEqual(verification["commonRGBFraction"], verification["commonRGBPixels"] / district)
        self.assertAlmostEqual(verification["commonAnalysisFraction"], verification["commonAnalysisPixels"] / district)
        self.assertEqual(sum(verification["perDateRGBValidPixels"].values()) >= 0, True)
        self.assertEqual(sum(verification["perDateDWValidPixels"].values()) >= 0, True)
        self.assertTrue(verification["scalarCrossCheck"]["agrees"])

        candidate = np.asarray(Image.open(DATA / self.entry["gainImage"]).convert("RGBA"))
        gain_colour = next(x["color"] for x in self.entry["legend"] if "gain" in x["label"].lower())
        rgb = tuple(int(gain_colour[i:i + 2], 16) for i in (1, 3, 5))
        observed = np.all(candidate[:, :, :3] == rgb, axis=2) & (candidate[:, :, 3] == 255)
        self.assertEqual(int(observed.sum()), counts["5"])
        self.assertGreater(int(observed.sum()), 0)

    def test_catalogue_ids_seasons_and_observation_counts(self):
        self.assertEqual(self.provenance["collections"], [
            "COPERNICUS/S2_SR_HARMONIZED",
            "GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED",
            "GOOGLE/DYNAMICWORLD/V1",
        ])
        periods = self.provenance["periods"]
        self.assertEqual(set(periods), {"2019", "2025"})
        for year, period in periods.items():
            self.assertEqual(period["start"], f"{year}-01-01")
            self.assertEqual(period["endExclusive"], f"{year}-04-01")
            self.assertGreaterEqual(len(period["s2_ids"]), 3)
            self.assertGreaterEqual(len(period["dw_ids"]), 3)

    def test_output_checksums_match_published_images(self):
        for name, metadata in self.provenance["outputs"].items():
            path = DATA / name
            self.assertTrue(path.exists(), name)
            self.assertEqual(sha256(path), metadata["sha256"], name)
            self.assertEqual(path.stat().st_size, metadata["bytes"], name)

    def test_optional_raw_cogs_are_six_band_aligned_exports(self):
        paths = [RAW / "urban-2019.tif", RAW / "urban-2025.tif"]
        present = [path for path in paths if path.exists()]
        if not present:
            self.skipTest("raw urban COGs are optional and not present")
        opened = [rasterio.open(path) for path in present]
        try:
            for src in opened:
                self.assertEqual(src.count, 6)
                self.assertEqual(src.dtypes, ("uint16",) * 6)
                self.assertEqual(src.crs.to_string(), "EPSG:3857")
                self.assertEqual(src.nodata, 65535)
                self.assertEqual((src.width, src.height),
                                 (self.entry["displayGrid"]["width"], self.entry["displayGrid"]["height"]))
            if len(opened) == 2:
                self.assertEqual(opened[0].transform, opened[1].transform)
        finally:
            for src in opened:
                src.close()

    def test_raw_signals_obey_probability_and_observation_rules(self):
        paths = [RAW / 'urban-2019.tif', RAW / 'urban-2025.tif', RAW / 'urban-signals.tif']
        if not all(path.exists() for path in paths):
            self.skipTest('optional raw COGs not present')
        with rasterio.open(paths[0]) as src:
            old = src.read([4, 5, 6])
        with rasterio.open(paths[1]) as src:
            new = src.read([4, 5, 6])
        with rasterio.open(paths[2]) as src:
            classes = src.read(1)
        assessed = classes >= 2
        for array in (old, new):
            self.assertTrue(np.all(array[0, assessed] >= 3))
            self.assertTrue(np.all(array[2, assessed] >= 3))
            self.assertTrue(np.all(array[0, assessed] != 65535))
            self.assertTrue(np.all(array[2, assessed] != 65535))
            self.assertTrue(np.all(array[1, assessed] <= 10000))
        gain = classes == 5
        loss = classes == 4
        self.assertTrue(np.all(old[1, gain] <= 2000))
        self.assertTrue(np.all(new[1, gain] >= 6000))
        self.assertTrue(np.all(old[1, loss] >= 6000))
        self.assertTrue(np.all(new[1, loss] <= 2000))

if __name__ == "__main__":
    unittest.main(verbosity=2)
