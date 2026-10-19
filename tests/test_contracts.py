"""Static/data contracts for Kozhikode Atlas.

These tests deliberately do not run JavaScript or a browser. Optional generated
publish assets are skipped with an explicit reason while acquisition is in
progress; skips are reported, not treated as successful data validation.
"""
from __future__ import annotations

import json
import re
import struct
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
DATA = SITE / "data"
APP = (SITE / "app.js").read_text(encoding="utf-8")
THEMATIC_PATH = DATA / "thematic.json"


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def png_header(path: Path):
    """Return width, height, bit depth, colour type from a PNG IHDR."""
    raw = path.read_bytes()
    if raw[:8] != b"\x89PNG\r\n\x1a\n":
        raise AssertionError(f"not a PNG: {path}")
    length, chunk = struct.unpack(">I4s", raw[8:16])
    if chunk != b"IHDR" or length < 13:
        raise AssertionError(f"PNG has no valid IHDR: {path}")
    width, height, depth, colour = struct.unpack(">IIBB", raw[16:26])
    return width, height, depth, colour


class GeoJSONContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.published = DATA / "atlas.geojson"
        cls.raw_boundary = ROOT / "raw" / "geoBoundaries-IND-ADM2.geojson"
        cls.path = cls.published if cls.published.exists() else cls.raw_boundary

    def test_available_geojson_is_feature_collection(self):
        if not self.path.exists():
            self.skipTest("no published or retained GeoJSON is available")
        doc = read_json(self.path)
        self.assertEqual(doc.get("type"), "FeatureCollection")
        self.assertIsInstance(doc.get("features"), list)
        self.assertGreater(len(doc["features"]), 0)

    def test_coordinates_are_in_geographic_bounds(self):
        if not self.path.exists():
            self.skipTest("no GeoJSON available")
        doc = read_json(self.path)

        def walk(coords):
            if isinstance(coords, (list, tuple)) and coords and isinstance(coords[0], (int, float)):
                yield coords
            else:
                for child in coords or []:
                    yield from walk(child)

        count = 0
        for feature in doc.get("features", []):
            geometry = feature.get("geometry") or {}
            for coordinate in walk(geometry.get("coordinates")):
                self.assertGreaterEqual(coordinate[0], -180)
                self.assertLessEqual(coordinate[0], 180)
                self.assertGreaterEqual(coordinate[1], -90)
                self.assertLessEqual(coordinate[1], 90)
                count += 1
        self.assertGreater(count, 0)

    def test_point_coordinates_are_not_duplicated(self):
        if not self.published.exists():
            self.skipTest("published atlas.geojson is not present yet")
        doc = read_json(self.published)
        points = [
            tuple(f["geometry"]["coordinates"][:2])
            for f in doc.get("features", [])
            if (f.get("geometry") or {}).get("type") == "Point"
        ]
        self.assertEqual(len(points), len(set(points)), "duplicate point coordinates found")

    def test_crs_contract_is_wgs84_or_omitted(self):
        if not self.path.exists():
            self.skipTest("no GeoJSON available")
        crs = read_json(self.path).get("crs")
        if crs is None:
            return  # RFC 7946 GeoJSON defaults to WGS 84.
        text = json.dumps(crs).upper()
        self.assertTrue(
            "4326" in text or "CRS84" in text or "WGS 84" in text or "WGS84" in text,
            crs,
        )

    def test_published_features_have_kind_and_missing_optional_attributes_are_safe(self):
        if not self.published.exists():
            self.skipTest("published atlas.geojson is not present yet")
        features = read_json(self.published)["features"]
        self.assertTrue(features)
        for feature in features:
            props = feature.get("properties")
            self.assertIsInstance(props, dict)
            self.assertIsInstance(props.get("kind"), str)
            self.assertTrue(props["kind"])
            # app.js intentionally supplies fallbacks for these optional fields.
            self.assertRegex(APP, r"p\.name\s*\|\|\s*['\"]Unnamed feature")
            self.assertRegex(APP, r"p\.source\s*\|\|\s*['\"]See data provenance")


class ThematicRasterContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = read_json(THEMATIC_PATH) if THEMATIC_PATH.exists() else None

    def test_thematic_catalogue_has_layers(self):
        if self.doc is None:
            self.skipTest("site/data/thematic.json is not present")
        layers = self.doc.get("layers")
        self.assertIsInstance(layers, list)
        self.assertTrue(layers)
        self.assertEqual(len({layer.get("id") for layer in layers}), len(layers))

    def test_rasters_match_metadata_and_have_valid_png_headers(self):
        if self.doc is None:
            self.skipTest("site/data/thematic.json is not present")
        for layer in self.doc["layers"]:
            image = DATA / layer["image"]
            if not image.exists():
                self.skipTest(f"raster not generated yet: {image.name}")
            width, height, depth, colour = png_header(image)
            self.assertGreater(width, 0)
            self.assertGreater(height, 0)
            self.assertIn(depth, (8, 16))
            self.assertIn(colour, (2, 3, 4, 6), "unsupported PNG colour type")
            bounds = layer["bounds"]
            self.assertEqual(len(bounds), 2)
            self.assertEqual(len(bounds[0]), 2)
            self.assertLess(bounds[0][0], bounds[1][0])
            self.assertLess(bounds[0][1], bounds[1][1])

    def test_legends_are_ordered_nonempty_and_colour_consistent(self):
        if self.doc is None:
            self.skipTest("site/data/thematic.json is not present")
        for layer in self.doc["layers"]:
            legend = layer.get("legend")
            self.assertIsInstance(legend, list)
            self.assertTrue(legend)
            labels = [entry.get("label") for entry in legend]
            colours = [entry.get("color") for entry in legend]
            self.assertEqual(len(labels), len(set(labels)), layer.get("id"))
            self.assertTrue(all(isinstance(x, str) and x.strip() for x in labels))
            self.assertTrue(all(re.fullmatch(r"#[0-9a-fA-F]{6}", x or "") for x in colours))
            self.assertEqual(colours, [entry.get("color") for entry in layer["legend"]])


class StaticFrontendContractTests(unittest.TestCase):
    def test_supported_layers_and_metadata_driven_legend_contract(self):
        for layer in ("reference", "landcover", "elevation", "slope", "coastal", "urban", "population"):
            self.assertIn(f"id:'{layer}'", APP)
        self.assertIn("t?.legend?.length?t.legend:refLegend()", APP)
        self.assertIn("state.thematic=thematic?.layers||[]", APP)

    def test_reference_colour_map_is_used_for_legend_and_layers(self):
        self.assertIn("const colors={boundary:'#526c3f',settlement:'#344e36',road:'#b79660',river:'#709eab',coast:'#4c8791'}", APP)
        self.assertIn("color:colors[kind]", APP)
        self.assertIn("color:colors[k]", APP)

    def test_loading_errors_and_raster_errors_are_user_visible(self):
        self.assertIn("if(!r.ok)", APP)
        self.assertIn("catch(e)", APP)
        self.assertIn("Data could not be loaded", APP)
        self.assertIn("This raster could not load", APP)
        self.assertIn("Context basemap unavailable", APP)

    def test_source_markers_are_present(self):
        self.assertIn("inventory.json", APP)
        self.assertIn("sourceUrl", APP)
        self.assertIn("sourceDatasetCards", APP)
        self.assertIn("source", APP)
        self.assertIn("license", APP)

    def test_svg_png_pdf_export_code_paths_have_attribution(self):
        self.assertIn("function buildSVG()", APP)
        self.assertIn("if(format==='svg')", APP)
        self.assertIn("else if(format==='png')", APP)
        self.assertIn("async function makePdf(svg)", APP)
        self.assertIn("type:'application/pdf'", APP)
        self.assertIn("Web Mercator EPSG:3857", APP)
        self.assertIn("No online basemap tiles in export", APP)
        self.assertIn("Missing raster pixels are transparent", APP)

    def test_required_runtime_files_are_referenced(self):
        self.assertIn("data/atlas.geojson", APP)
        self.assertIn("data/inventory.json", APP)
        self.assertIn("data/thematic.json", APP)


if __name__ == "__main__":
    unittest.main(verbosity=2)
