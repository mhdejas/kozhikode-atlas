import json
import struct
import unittest
from pathlib import Path

import numpy as np
import rasterio
from pyproj import Transformer

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "site/data"
RAW = ROOT / "raw/thematic"


def read_rgb(path):
    b = path.read_bytes()
    assert b[:8] == b"\x89PNG\r\n\x1a\n"
    w, h, depth, colour = struct.unpack(">IIBB", b[16:26])
    assert (depth, colour) == (8, 2)
    # Decode the exporter’s filter-zero scanlines (zlib stream is first IDAT).
    pos = 8; packed = b""
    while pos < len(b):
        n = struct.unpack(">I", b[pos:pos+4])[0]; typ = b[pos+4:pos+8]
        if typ == b"IDAT": packed += b[pos+8:pos+8+n]
        pos += 12 + n
    raw = __import__("zlib").decompress(packed)
    rows = []
    stride = w * 3
    for y in range(h):
        assert raw[y * (stride + 1)] == 0
        rows.append(np.frombuffer(raw[y * (stride + 1) + 1:y * (stride + 1) + 1 + stride], dtype=np.uint8).reshape(w, 3))
    return np.stack(rows)


class InspectorContractTests(unittest.TestCase):
    def test_grid_metadata_and_lossless_rgb_contract(self):
        m = json.loads((DATA / "inspector.json").read_text())
        self.assertEqual(m["grid"]["crs"], "EPSG:3857")
        self.assertEqual((m["grid"]["width"], m["grid"]["height"]), (681, 776))
        for k in ("elevation", "slope", "landcover"):
            self.assertIn(k, m["datasets"])
            self.assertEqual(read_rgb(DATA / m["datasets"][k]["image"]).shape, (776, 681, 3))

    def test_raster_roundtrip_precision_and_nodata(self):
        raw_paths = [RAW / f"{k}_display_3857.tif" for k in ("elevation", "slope", "landcover")]
        if not all(p.exists() for p in raw_paths):
            self.skipTest("original raw thematic TIFFs are not part of the public package")
        for k, factor, nodata in (("elevation", 1, 65535), ("slope", 100, 65535), ("landcover", 1, 0)):
            with rasterio.open(RAW / f"{k}_display_3857.tif") as src:
                a = src.read(1, masked=True)
            rgb = read_rgb(DATA / f"inspector-{k}.png")
            vals = rgb[..., 0].astype(np.uint16) if k == "landcover" else rgb[..., 0].astype(np.uint16) * 256 + rgb[..., 1]
            valid = ~a.mask
            self.assertTrue(np.all(vals[~valid] == nodata))
            if k == "landcover":
                self.assertTrue(np.all(vals[valid] == a.data[valid]))
            elif k == "elevation":
                self.assertLessEqual(np.max(np.abs(vals[valid].astype(float) - np.rint(a.data[valid]))), 0.5)
            else:
                self.assertLessEqual(np.max(np.abs(vals[valid].astype(float) / factor - a.data[valid])), 0.0051)
            self.assertTrue(np.all(rgb[..., 2] == 255))

    def test_named_features_are_utm43n_and_boundary_excluded(self):
        d = json.loads((DATA / "inspector-features.json").read_text())
        self.assertEqual(d["crs"], "EPSG:32643")
        self.assertGreater(len(d["features"]), 0)
        self.assertTrue(all(f["name"] and f["kind"] != "boundary" for f in d["features"]))
        t = Transformer.from_crs("EPSG:4326", "EPSG:32643", always_xy=True)
        # Kozhikode bounding range is a simple sanity check on projected coordinates.
        for f in d["features"][:20]:
            c = f["geometry"]["coordinates"]
            while isinstance(c[0], list): c = c[0]
            x, y = t.transform(75.8, 11.3)
            self.assertTrue(0 < c[0] < 1_000_000 and 0 < c[1] < 2_000_000)
            self.assertTrue(all(abs(float(v) * 10 - round(float(v) * 10)) < 1e-7 for v in c[:2]))


if __name__ == "__main__":
    unittest.main()
