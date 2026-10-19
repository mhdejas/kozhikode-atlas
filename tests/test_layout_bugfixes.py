import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class LayoutBugfixTests(unittest.TestCase):
    def test_timeline_link_owns_grid_columns(self):
        css = (ROOT / 'site/atlas-ui.css').read_text()
        self.assertIn('.election-timeline-year li{display:block}', css)
        self.assertIn('.timeline-row{min-width:0}', css)

    def test_dialogs_fit_small_viewports_and_scroll(self):
        css = (ROOT / 'site/atlas-ui.css').read_text()
        self.assertIn('max-width:calc(100vw - 24px);max-height:calc(100dvh - 24px);overflow:auto', css)
