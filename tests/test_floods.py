"""Flood evidence layers from EARTHSIM-Omega, tested against the real bundled files."""
import hashlib
import json
import re
from pathlib import Path
import unittest

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / 'site'
DATA = SITE / 'data'
FLOODS = DATA / 'floods'
EVIDENCE = {
    'flood-2018': 'observed',
    'flood-2019': 'observed',
    'flood-low-land': 'modelled',
    'flood-susceptibility': 'modelled',
    'flood-hindcast-2019': 'simulated',
}
LABELS = {'observed', 'modelled', 'simulated', 'forecast'}


def load(path):
    return json.loads(path.read_text(encoding='utf-8'))


class FloodEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.layers = {layer['id']: layer for layer in load(DATA / 'thematic.json')['layers']}
        cls.datasets = load(DATA / 'inspector.json')['datasets']
        cls.prov = load(FLOODS / 'provenance.json')
        cls.rain = load(FLOODS / 'rain-replay.json')
        cls.outlook = load(FLOODS / 'outlook-2026-10-23.json')

    def test_every_flood_layer_is_a_map_theme_and_a_point_reading(self):
        for layer_id, evidence in EVIDENCE.items():
            with self.subTest(layer=layer_id):
                self.assertIn(layer_id, self.layers)
                self.assertIn(layer_id, self.datasets)
                self.assertEqual(self.layers[layer_id]['evidence'], evidence)
                self.assertEqual(self.datasets[layer_id]['evidence'], evidence)
                self.assertIs(self.layers[layer_id]['official'], False)
                self.assertTrue((DATA / self.datasets[layer_id]['image']).is_file())

    def test_layer_images_match_their_checksums_and_pixel_counts(self):
        for layer_id in EVIDENCE:
            with self.subTest(layer=layer_id):
                record = self.prov['files'][layer_id]
                path = DATA / record['file']
                self.assertEqual(self.layers[layer_id]['image'], record['file'])
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), record['sha256'])
                rgba = np.asarray(Image.open(path).convert('RGBA'))
                grid = self.layers[layer_id]['displayGrid']
                self.assertEqual(rgba.shape[:2], (grid['height'], grid['width']))
                visible = rgba[..., 3] > 0
                self.assertEqual(int(visible.sum()), record['validPixels'])
                for colour, count in record['pixelsByColour'].items():
                    rgb = [int(colour[i:i + 2], 16) for i in (1, 3, 5)]
                    self.assertEqual(int(((rgba[..., :3] == rgb).all(-1) & visible).sum()), count, colour)

    def test_legend_colours_are_the_colours_actually_drawn(self):
        for layer_id in EVIDENCE:
            with self.subTest(layer=layer_id):
                drawn = set(self.prov['files'][layer_id]['pixelsByColour'])
                legend = {item['color'].lower() for item in self.layers[layer_id]['legend']}
                self.assertTrue(drawn <= legend, drawn - legend)

    def test_published_accuracy_is_the_honest_held_out_score(self):
        csi = self.prov['heldOutCsi_2019_08_10']
        self.assertEqual(csi['calibrated_model'], 0.019)
        self.assertEqual(csi['ksdma_25yr_footprint'], 0.023)
        self.assertGreater(csi['ksdma_25yr_footprint'], csi['calibrated_model'])
        trigger = self.prov['rainTrigger_1day_2024_2026']
        self.assertEqual((trigger['caught'], trigger['heavy_days']), (9, 15))
        self.assertEqual(trigger['false_alarm_ratio'], 0.67)
        self.assertAlmostEqual(trigger['false_alarms'] / (trigger['false_alarms'] + trigger['caught']), 0.67, places=2)

    def test_rain_replay_table_agrees_with_the_daily_series(self):
        heavy = [d for d in self.rain['daily'] if d['era5'] >= self.rain['heavy_threshold_mm']]
        self.assertEqual(len(heavy), 15)
        self.assertEqual([d['date'] for d in heavy], [h['date'] for h in self.rain['heavy_days']])
        for day, row in zip(heavy, self.rain['heavy_days']):
            expected = None if day['fc1'] is None else day['fc1'] >= self.rain['trigger_mm']
            self.assertEqual(row['flagged'], expected, row['date'])
        vilangad = next(h for h in self.rain['heavy_days'] if h['date'] == '2024-07-30')
        self.assertFalse(vilangad['flagged'])

    def test_outlook_is_marked_experimental_and_not_official(self):
        self.assertIs(self.outlook['official'], False)
        self.assertIs(self.prov['official'], False)
        self.assertIn(self.outlook['level_next_72h'], {'GREEN', 'YELLOW', 'ORANGE', 'RED'})
        text = (SITE / 'flood-evidence.js').read_text(encoding='utf-8')
        for phrase in ('Research, not a warning', 'not live', 'IMD', 'CWC', 'KSDMA',
                       'https://mausam.imd.gov.in/', 'https://ffs.india-water.gov.in/', 'https://sdma.kerala.gov.in/'):
            self.assertIn(phrase, text)

    def test_figures_are_real_labelled_files(self):
        self.assertEqual(len(self.prov['figures']), 6)
        for figure in self.prov['figures']:
            with self.subTest(figure=figure['file']):
                self.assertIn(figure['evidence'], LABELS)
                self.assertTrue(figure['file'].endswith(f"-{figure['evidence']}.jpg"))
                path = DATA / figure['file']
                with Image.open(path) as im:
                    self.assertGreaterEqual(min(im.size), 600)
                self.assertRegex(figure['sourceSha256'], r'^[0-9a-f]{64}$')

    def test_atlas_page_loads_the_flood_section(self):
        html = (SITE / 'index.html').read_text(encoding='utf-8')
        for needle in ('id="flood-evidence"', 'href="#flood-evidence"', 'src="flood-evidence.js"',
                       'href="flood-evidence.css"', 'data-quick-theme="flood-2018"'):
            self.assertIn(needle, html)

    def test_no_private_paths_in_flood_files(self):
        pattern = re.compile(r'/(workspace|home|tmp|run)/|sandbox', re.I)
        files = [SITE / 'flood-evidence.js', SITE / 'flood-evidence.css', *FLOODS.glob('*.json')]
        for path in files:
            with self.subTest(file=path.name):
                self.assertIsNone(pattern.search(path.read_text(encoding='utf-8')))


if __name__ == '__main__':
    unittest.main()
