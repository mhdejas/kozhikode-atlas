#!/usr/bin/env python3
"""Summarise exported per-pixel clear observations; no new server processing."""
import json
from pathlib import Path
import numpy as np
import rasterio
from rasterio.features import geometry_mask
from rasterio.warp import transform_geom

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "site/data"
features = json.loads((DATA / "atlas.geojson").read_text())["features"]
geometry = next(
    f["geometry"] for f in features if f["properties"]["kind"] == "boundary"
)
output = {
    "periodLabel": "January–March",
    "years": {},
    "semantics": "Counts are cloud/shadow-masked Sentinel-2 tile observations per display-grid pixel, not cloud-free scenes or unique days. Tile overlaps can contribute multiple observations on a date.",
    "source": "Saved six-band Earth Engine exports; band 4 rgb_count",
    "mask": "Cloud Score+ cs_cdf >= 0.60; SCL excludes 0, 1, 3, 8, 9, 10, 11; scene cloud <= 80%",
    "displayGrid": "EPSG:3857, approximately 20 m; nearest-neighbour count display; summaries are unweighted display-pixel statistics, not equal-area estimates.",
}
for year in (2019, 2025):
    with rasterio.open(ROOT / f"raw/urban/urban-{year}.tif") as src:
        assert src.count == 6
        inside = geometry_mask(
            [transform_geom("EPSG:4326", src.crs, geometry)],
            out_shape=(src.height, src.width),
            transform=src.transform,
            invert=True,
        )
        count = src.read(4)
        vals = count[inside & (count != 65535)]
        assert len(vals) > 0
        hist = np.bincount(vals.astype(int))
        output["years"][str(year)] = {
            "start": f"{year}-01-01",
            "endExclusive": f"{year}-04-01",
            "minimum": int(vals.min()),
            "p10": float(np.percentile(vals, 10)),
            "median": float(np.median(vals)),
            "p90": float(np.percentile(vals, 90)),
            "maximum": int(vals.max()),
            "pixels": int(len(vals)),
            "atLeastThreePercent": round(float(np.mean(vals >= 3)) * 100, 3),
            "histogram": {str(i): int(n) for i, n in enumerate(hist) if n},
        }
(DATA / "observation-counts.json").write_text(json.dumps(output, indent=2) + "\n")
print(
    json.dumps(
        {
            y: {k: v for k, v in d.items() if k != "histogram"}
            for y, d in output["years"].items()
        },
        indent=2,
    )
)
