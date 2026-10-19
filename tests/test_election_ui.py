"""Regression checks for the election archive UI contract."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
JS = (ROOT / "site" / "elections.js").read_text(encoding="utf-8")
CSS = (ROOT / "site" / "elections.css").read_text(encoding="utf-8")


class ElectionUiContractTests(unittest.TestCase):
    def test_all_years_mode_has_start_to_end_selector_and_filters_timeline(self):
        self.assertIn("All years · 1957–2026", JS)
        self.assertIn("state.year?`Election year ${state.year}", JS)
        self.assertIn("filter(y=>!state.year||y===Number(state.year))", JS)
        self.assertIn("sort((a,b)=>a-b)", JS)

    def test_timeline_rows_open_full_record(self):
        self.assertIn("data-timeline-kind", JS)
        self.assertIn("state.mode='historical'", JS)
        self.assertIn("state.mode='current'", JS)
        self.assertIn("state.selected=b.dataset.timelineId", JS)

    def test_search_includes_secondary_candidate_names_and_provenance_is_unconditional(self):
        self.assertIn("candidates.flatMap(c=>[c.name,c.party])", JS)
        self.assertIn(")+archiveProvenance()", JS)
        self.assertIn("200 documented result records across 17 election years", JS)

    def test_portrait_caption_has_source_license_date_and_nota_exception(self):
        self.assertIn("Photo source", JS)
        self.assertIn("p.licenseUrl", JS)
        self.assertIn("p.date||p.accessed||p.capturedAt", JS)
        self.assertIn("['nota','noneoftheabove'].includes(nameKey(c.name))", JS)
        self.assertIn("p.reusable===true?localPhoto(p):''", JS)
        self.assertIn("state.year=state.mode==='all'?'':", JS)
        self.assertIn(".timeline-row:focus-visible", CSS)


if __name__ == "__main__":
    unittest.main()
