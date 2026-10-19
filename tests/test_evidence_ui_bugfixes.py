"""Regression contracts for evidence and election interaction bug fixes."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
LANDSLIDE = (ROOT / "site" / "landslide-evidence.js").read_text(encoding="utf-8")
ELECTIONS = (ROOT / "site" / "elections.js").read_text(encoding="utf-8")

class EvidenceUiBugfixTests(unittest.TestCase):
    def test_landslide_init_is_retryable_and_idempotent(self):
        self.assertIn("atlas.__landslideEvidenceInit", LANDSLIDE)
        self.assertIn("if (!tools || !mapWrap) return;", LANDSLIDE)
        self.assertIn("const geo = rawGeo && Array.isArray(rawGeo.features)", LANDSLIDE)

    def test_public_evidence_loads_research_and_licensed_inventory_assets(self):
        self.assertIn("data/landslide-research.json", LANDSLIDE)
        self.assertIn("data/landslide-inventory-provenance.json", LANDSLIDE)
        self.assertIn("data/landslide-inventory-2018.geojson", LANDSLIDE)
        self.assertIn("Download the licensed historical evidence", LANDSLIDE)
        self.assertIn("CC BY 4.0", LANDSLIDE)

    def test_public_evidence_content_is_escaped_and_has_no_dynamic_remote_links(self):
        self.assertIn("const esc =", LANDSLIDE)
        self.assertNotIn("href=\\\"${esc(x.url)}\\\"", LANDSLIDE)

    def test_elections_deep_link_survives_async_data_init(self):
        self.assertIn("new URLSearchParams(global.location?.search||'')", ELECTIONS)
        self.assertIn("if(shouldOpen) open()", ELECTIONS)
        self.assertIn("if(!state.selected)", ELECTIONS)

    def test_elections_geometry_and_external_urls_are_safe(self):
        self.assertIn("Array.isArray(raw.features)", ELECTIONS)
        self.assertIn("safeUrl=v=>/^https?:\\/\\//i", ELECTIONS)
        self.assertIn("target?.focus", ELECTIONS)

if __name__ == "__main__":
    unittest.main()
