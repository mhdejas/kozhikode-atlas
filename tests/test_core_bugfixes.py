"""Regression checks for the static atlas core runtime fixes."""
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
APP = (SITE / "app.js").read_text(encoding="utf-8")
UI = (SITE / "atlas-ui.js").read_text(encoding="utf-8")


class CoreRuntimeBugfixTests(unittest.TestCase):
    def test_javascript_sources_parse(self):
        for name in ("app.js", "interface.js", "atlas-ui.js"):
            result = subprocess.run(["node", "--check", str(SITE / name)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_anchor_navigation_restores_target_hash_after_show_page(self):
        self.assertIn("history.replaceState(null,'',target === '#explore-page' ? '#explore' : target)", UI)
        self.assertIn("history.replaceState(null,'','#explore')", UI)

    def test_unavailable_theme_deep_link_is_explicitly_routed(self):
        self.assertIn("else showPage('limitations',initialRoute)", APP)
        self.assertIn("!['elections','terrain-explorer','geography-story','elevation-lab'].includes(initialRoute)", APP)

    def test_bookmarks_cannot_restore_invalid_theme_or_blend(self):
        self.assertIn("themeDefs.some(t=>t.id===b.theme)&&available(b.theme)?b.theme:'reference'", APP)
        self.assertIn("Math.max(0,Math.min(100,b.urbanBlend))", APP)

    def test_svg_export_ignores_features_without_vector_layers(self):
        self.assertIn("const k=f.properties.kind,layer=state.vectorLayers[k]", APP)
        self.assertIn("!layer||!map.hasLayer(layer)", APP)

    def test_png_density_chunk_has_valid_size(self):
        code = APP[APP.index('async function pngDPI'):]
        harness = """
const assert=require('node:assert/strict');
(async()=>{
 const input=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/l9sAAAAASUVORK5CYII=','base64');
 const output=Buffer.from(await (await pngDPI(new Blob([input]),300)).arrayBuffer());
 assert.equal(output.length,input.length+21);
 assert.equal(output.toString('ascii',37,41),'pHYs');
 assert.equal(output.readUInt32BE(41),11811);
 assert.equal(output[49],1);
})().catch(e=>{console.error(e);process.exit(1)});
"""
        result = subprocess.run(['node', '-e', code + harness], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_export_failures_are_reported(self):
        self.assertIn("Export failed:", APP)
        self.assertIn("Raster unavailable for export.", APP)


if __name__ == "__main__":
    unittest.main(verbosity=2)
