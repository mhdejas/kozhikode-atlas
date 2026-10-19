"""Real published-data tests for the atlas extensions."""
import json
from pathlib import Path
import unittest
from shapely.geometry import shape
ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'site/data'

class ObservationCountTests(unittest.TestCase):
    def test_actual_clear_count_statistics(self):
        data = json.loads((DATA/'observation-counts.json').read_text())
        self.assertEqual(set(data['years']), {'2019','2025'})
        for year, stats in data['years'].items():
            self.assertLessEqual(stats['minimum'], stats['p10'])
            self.assertLessEqual(stats['p10'], stats['median'])
            self.assertLessEqual(stats['median'], stats['p90'])
            self.assertLessEqual(stats['p90'], stats['maximum'])
            self.assertEqual(sum(stats['histogram'].values()), stats['pixels'])
            self.assertEqual(stats['pixels'], 6206639)
            self.assertIn('not cloud-free scenes', data['semantics'])

class ConstituencyTests(unittest.TestCase):
    def test_all_thirteen_boundaries_are_valid(self):
        path = DATA/'constituencies.geojson'
        self.assertTrue(path.exists(), 'constituencies must be acquired before delivery')
        data = json.loads(path.read_text())
        self.assertEqual(data['type'], 'FeatureCollection')
        self.assertEqual(len(data['features']), 13)
        numbers = set()
        for f in data['features']:
            g = shape(f['geometry'])
            self.assertTrue(g.is_valid and not g.is_empty)
            self.assertIn(g.geom_type, ('Polygon','MultiPolygon'))
            minx,miny,maxx,maxy = g.bounds
            self.assertTrue(75 < minx < maxx < 77)
            self.assertTrue(10 < miny < maxy < 13)
            numbers.add(int(f['properties']['ac_no']))
        self.assertEqual(numbers, set(range(20,33)))

if __name__ == '__main__':
    unittest.main()
