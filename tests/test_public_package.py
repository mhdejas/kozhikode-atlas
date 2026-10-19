"""Public-package integration and safety contracts for the atlas."""
import json
import unittest
from pathlib import Path

import numpy as np
from PIL import Image
from shapely.geometry import shape

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
DATA = SITE / "data"


def load_json(name):
    return json.loads((DATA / name).read_text(encoding="utf-8"))


class PublicPackageTests(unittest.TestCase):
    def test_shipped_surface_has_no_staging_claims_and_keeps_rights_context(self):
        banned = (
            "candidate unpublished",
            "unpublished repository candidate",
            "unpublished candidate",
            "nothing has been published",
            "publication is pending",
            "no publication has occurred",
            "not been committed",
            "no repository, commit, push or deployment",
            "temporary-preview feature",
        )
        suffixes = {".css", ".html", ".js", ".json", ".md", ".py"}
        excluded = {"tests", "vendor"}
        offenders = []
        for path in (ROOT / "README.md", ROOT / "docs", ROOT / "site", ROOT / "scripts"):
            paths = [path] if path.is_file() else path.rglob("*")
            for candidate in paths:
                if not candidate.is_file() or candidate.suffix.lower() not in suffixes:
                    continue
                relative = candidate.relative_to(ROOT)
                if excluded.intersection(relative.parts) or relative.as_posix() == "docs/LANDSLIDE_PUBLIC_SOURCES.json":
                    continue
                text = candidate.read_text(encoding="utf-8").lower()
                for phrase in banned:
                    if phrase in text:
                        offenders.append(f"{relative}: {phrase}")
        self.assertEqual(offenders, [])

        readme = (ROOT / "README.md").read_text(encoding="utf-8").lower()
        html = (SITE / "index.html").read_text(encoding="utf-8").lower()
        for text in (readme, html):
            self.assertRegex(text, r"rights warning|gsi rights")
            self.assertRegex(text, r"not official|non-official|unofficial")

    def test_required_published_files_exist(self):
        required = [
            "site/index.html", "site/app.js", "site/inspector.js",
            "site/landslide-evidence.js", "site/data/thematic.json",
            "site/data/inspector.json", "site/data/landslide-provenance.json",
            "site/data/landslide-research.json",
            "site/data/landslide-inventory-2018.geojson",
            "site/data/landslide-inventory-provenance.json",
            "site/data/landslide-susceptibility.png", "site/data/inspector-landslide.png",
        ]
        for rel in required:
            self.assertTrue((ROOT / rel).is_file(), f"missing required published file: {rel}")

    def test_no_private_or_unwanted_files_are_staged(self):
        forbidden = {"private", "temp", "tmp", "build", "work", "raw"}
        offenders = [
            p.relative_to(ROOT).as_posix() for p in ROOT.rglob("*")
            if ".git" not in p.relative_to(ROOT).parts and (
                any(part.lower() in forbidden for part in p.relative_to(ROOT).parts)
                or (p.name.startswith(".") and p.name not in {".nojekyll", ".github"})
            )
        ]
        self.assertEqual(offenders, [])

    def test_historical_inventory_is_wgs84_points_and_attributed(self):
        geo = load_json("landslide-inventory-2018.geojson")
        self.assertEqual(geo["type"], "FeatureCollection")
        self.assertEqual(geo["crs"]["properties"]["name"], "urn:ogc:def:crs:OGC:1.3:CRS84")
        self.assertEqual(len(geo["features"]), 235)
        boundary = next(f for f in load_json("atlas.geojson")["features"] if f.get("properties", {}).get("kind") == "boundary")
        district = shape(boundary["geometry"])
        expected = {"record_id", "type", "source_method", "district"}
        for feature in geo["features"]:
            self.assertEqual(feature["geometry"]["type"], "Point")
            self.assertEqual(set(feature["properties"]), expected)
            self.assertTrue(district.covers(shape(feature["geometry"])))
        prov = load_json("landslide-inventory-provenance.json")
        self.assertEqual(prov["feature_count"], 235)
        self.assertEqual(prov["license"], "CC-BY-4.0")
        self.assertIn("10.17026/dans-x6c-y7x2", prov["source_doi"])

    def test_gsi_rights_and_research_gates_are_present(self):
        prov = load_json("landslide-provenance.json")
        research = load_json("landslide-research.json")
        self.assertFalse(prov["permanentGsiRedistributionCleared"])
        self.assertFalse(research["outreachPermitted"])
        review = research["publicSourceReview"]
        self.assertFalse(review["newLayerAdded"])
        self.assertTrue(review["candidates"])
        text = " ".join(p for s in research["sections"] for p in s["paragraphs"])
        self.assertIn("No data request will be sent", text)
        thematic = load_json("thematic.json")
        layer = next(x for x in thematic["layers"] if x["id"] == "landslide")
        inspector = load_json("inspector.json")["datasets"]["landslide"]
        for entry in (layer, inspector):
            joined = " ".join(str(entry.get(k, "")) for k in ("source", "license", "limitations", "units"))
            self.assertIn("GSI", joined)
            self.assertRegex(joined.lower(), r"no explicit reuse|unresolved|not probability|not safe|not mapped")
        self.assertIn("landslide-provenance.json", layer["provenanceFile"])

    def test_gsi_references_are_live_and_share_the_same_grid(self):
        layers = load_json("thematic.json")["layers"]
        layer = next(x for x in layers if x["id"] == "landslide")
        inspector = load_json("inspector.json")["datasets"]["landslide"]
        self.assertTrue((DATA / layer["image"]).is_file())
        self.assertTrue((DATA / inspector["image"]).is_file())
        with Image.open(DATA / layer["image"]) as thematic_image, Image.open(DATA / inspector["image"]) as inspector_image:
            self.assertEqual(thematic_image.size, inspector_image.size)
            self.assertEqual(thematic_image.size, (681, 776))
        self.assertEqual(layer["displayCrs"], "EPSG:3857")
        self.assertEqual(layer["bounds"], next(x for x in layers if x["id"] == "elevation")["bounds"])

    def test_gsi_png_codes_palette_and_counts_match_provenance(self):
        prov = load_json("landslide-provenance.json")
        codes = np.asarray(Image.open(DATA / "inspector-landslide.png").convert("RGB"))[:, :, 0]
        rgba = np.asarray(Image.open(DATA / "landslide-susceptibility.png").convert("RGBA"))
        labels = {"1": "Low", "2": "Moderate", "3": "High", "4": "Not mapped in source"}
        for code, label in labels.items():
            mask = codes == int(code)
            self.assertEqual(int(mask.sum()), prov["pixelCounts"][label])
            rgb = [int(prov["colors"][code][i:i + 2], 16) for i in (1, 3, 5)]
            self.assertTrue(np.all(rgba[mask, :3] == rgb))
            self.assertTrue(np.all(rgba[mask, 3] == 255))
        self.assertEqual(int((codes == 0).sum()), 528456 - 248483)

    def test_gsi_unknown_and_unmapped_are_not_encoded_as_low(self):
        meta = load_json("inspector.json")["datasets"]["landslide"]
        self.assertEqual(meta["nodata"], 0)
        self.assertEqual(meta["classCodes"]["4"], "Not mapped in source")
        layer = next(x for x in load_json("thematic.json")["layers"] if x["id"] == "landslide")
        self.assertRegex(layer["limitations"].lower(), r"not safe|does not mean safe")
        self.assertIn("not mapped", layer["limitations"].lower())

    def test_frontend_integrates_rights_notice_theme_warning_and_export_guard(self):
        text = "\n".join((SITE / n).read_text(encoding="utf-8") for n in ("index.html", "app.js", "inspector.js"))
        lower = text.lower()
        self.assertRegex(lower, r"gsi[-_]rights[-_]notice|rights[-_]notice")
        self.assertRegex(lower, r"(?:export.{0,240}(?:permanentgsiredistributioncleared|redistribution|rights|permission)|(?:permanentgsiredistributioncleared|redistribution|rights|permission).{0,240}export)")
        self.assertIn("not a live warning", lower)
        self.assertIn("unmapped", lower)

    def test_catalogue_local_image_references_exist(self):
        for name in ("inspector.json", "thematic.json"):
            catalogue = load_json(name)
            entries = catalogue.get("datasets", {}).values() if name == "inspector.json" else catalogue.get("layers", [])
            for item in entries:
                if item.get("image"):
                    self.assertTrue((DATA / item["image"]).is_file(), item["image"])

    def test_readme_embeds_local_screenshots_and_documents_attribution(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        screenshots = (ROOT / "docs/screenshots/README.md").read_text(encoding="utf-8")
        for name in ("reference-map.png", "terrain-3d.png", "election-muneer.png"):
            self.assertRegex(readme, rf"!\[[^\]]*\]\(docs/screenshots/{name}\)")
            with Image.open(ROOT / "docs/screenshots" / name) as image:
                image.load()
                self.assertEqual(image.size, (1265, 649))
                self.assertIsNotNone(image.getbbox())
        self.assertIn("Syed Shiyaz Mirza", screenshots)
        self.assertRegex(screenshots, r"https?://commons\.wikimedia\.org/wiki/File:MK_Muneer\.jpg")
        self.assertIn("CC BY-SA 4.0", screenshots)
        lower = screenshots.lower()
        self.assertIn("screenshot", lower)
        self.assertRegex(lower, r"project.{0,80}mit|mit.{0,80}project")
        self.assertRegex(lower, r"photo.{0,100}map|map.{0,100}photo")
        self.assertIn("rights", lower)
        self.assertRegex(lower, r"(?:not|does not|doesn't).{0,100}(?:override|replace|supersede).{0,100}rights")


if __name__ == "__main__":
    unittest.main(verbosity=2)
