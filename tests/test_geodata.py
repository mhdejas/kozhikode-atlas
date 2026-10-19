"""Tests against the real bundled datasets, not mocked geometry or rasters."""
import json
from pathlib import Path
import unittest
import numpy as np
from PIL import Image
from pyproj import Transformer
from shapely.geometry import shape

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'site' / 'data'


class RealDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.features = json.loads((DATA/'atlas.geojson').read_text())['features']
        cls.inventory = json.loads((DATA/'inventory.json').read_text())
        cls.thematic = json.loads((DATA/'thematic.json').read_text())

    def test_geometries_are_valid_nonempty_and_in_district_bounds(self):
        for f in self.features:
            g = shape(f['geometry'])
            self.assertFalse(g.is_empty)
            self.assertTrue(g.is_valid, f['properties'])
            w,s,e,n = g.bounds
            self.assertGreaterEqual(w, 75.53)
            self.assertLessEqual(e, 76.15)
            self.assertGreaterEqual(s, 11.12)
            self.assertLessEqual(n, 11.81)

    def test_no_exact_duplicate_geometries_within_each_kind(self):
        seen = set()
        for f in self.features:
            key = (f['properties']['kind'], shape(f['geometry']).wkb)
            self.assertNotIn(key, seen)
            seen.add(key)

    def test_inventory_counts_and_file_size_match_actual_data(self):
        self.assertEqual(len(self.features), self.inventory['feature_count'])
        self.assertEqual((DATA/'atlas.geojson').stat().st_size, self.inventory['size_bytes'])
        for kind, count in self.inventory['counts'].items():
            self.assertEqual(sum(f['properties']['kind']==kind for f in self.features),count)

    def test_required_attributes_and_sources_are_present(self):
        for f in self.features:
            self.assertIn(f['properties']['kind'], ['boundary','settlement','road','river','coast'])
            self.assertIn('name',f['properties'])
            self.assertTrue(f['properties']['source'])
            if f['properties']['kind']=='settlement':
                self.assertTrue(f['properties']['name'])
        for d in self.inventory['datasets']:
            for field in ['name','source','url','license','date','resolution','processing','limitations']:
                self.assertTrue(d.get(field), (d['name'],field))

    def test_utm_roundtrip_and_axis_order(self):
        forward = Transformer.from_crs(4326,32643,always_xy=True)
        reverse = Transformer.from_crs(32643,4326,always_xy=True)
        x,y=forward.transform(75.78,11.26)
        self.assertTrue(500000 < x < 700000)
        lon,lat=reverse.transform(x,y)
        self.assertAlmostEqual(lon,75.78,places=8)
        self.assertAlmostEqual(lat,11.26,places=8)

    def test_raster_dimensions_and_display_alignment(self):
        for layer in self.thematic['layers']:
            grid=layer.get('displayGrid',self.thematic['displayGrid'])
            self.assertEqual(grid['crs'],'EPSG:3857')
            image=Image.open(DATA/layer['image'])
            self.assertEqual(image.size,(grid['width'],grid['height']))
            self.assertIn(image.mode, ('RGBA', 'P') if layer['id']=='urban' else ('RGBA',))
            image.close()
            self.assertEqual(layer['displayCrs'],'EPSG:3857')
            project=Transformer.from_crs(4326,3857,always_xy=True)
            sw,ne=layer['bounds']
            x0,y0=project.transform(sw[1],sw[0]);x1,y1=project.transform(ne[1],ne[0])
            for observed,expected in zip((x0,y0,x1,y1),grid['bounds3857']):
                self.assertAlmostEqual(observed,expected,places=4)
            transform=grid.get('transform')
            if transform:
                self.assertEqual(len(transform),6)
                self.assertGreater(abs(transform[0]),0)
                self.assertGreater(abs(transform[4]),0)

    def test_visible_raster_colours_match_legends_and_nodata_is_transparent(self):
        for layer in self.thematic['layers']:
            pixels=np.asarray(Image.open(DATA/layer['image']).convert('RGBA'))
            alpha=pixels[:,:,3]
            self.assertEqual(set(np.unique(alpha)),{0,255})
            # Urban's after/before products are continuous RGB visualizations;
            # only its categorical gain product has a documented class palette.
            if layer['id'] != 'urban':
                allowed={tuple(int(entry['color'][i:i+2],16) for i in (1,3,5)) for entry in layer['legend']}
                observed={tuple(row) for row in np.unique(pixels[:,:,:3][alpha>0],axis=0)}
                self.assertLessEqual(observed,allowed)
                self.assertGreater(len(observed),1)
            expected=layer['stats'].get('validPixels',layer['stats'].get('commonRGBPixels'))
            self.assertIsNotNone(expected)
            self.assertEqual(int((alpha>0).sum()),expected)

    def test_ordered_legends_and_landcover_class_95(self):
        layers={x['id']:x for x in self.thematic['layers']}
        self.assertEqual([x['label'] for x in layers['elevation']['legend']],['0–50 m','50–200 m','200–500 m','500–1000 m','≥1000 m'])
        self.assertEqual([x['label'] for x in layers['slope']['legend']],['0–5°','5–15°','15–30°','≥30°'])
        self.assertEqual(layers['landcover']['classCodes']['95'],'Mangroves')
        self.assertEqual(layers['slope']['analysisCrs'],'EPSG:32643')
        self.assertEqual(layers['slope']['analysisResolution'],'90 m')


if __name__ == '__main__':
    unittest.main()
