#!/usr/bin/env python3
"""Prepare a compact, metric terrain grid for the Kozhikode Three.js scene."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import rasterio
from pyproj import Transformer
from rasterio.enums import Resampling
from rasterio.transform import from_bounds
from rasterio.warp import reproject
from shapely.geometry import Point, shape
from shapely.ops import transform as shp_transform

CRS = "EPSG:32643"
SOURCE = "Copernicus DEM GLO-30 Public (2021 release; DSM, EGM2008 heights)"
SOURCE_URL = "https://registry.opendata.aws/copernicus-dem/"
PLACES = {"Kozhikode", "Vadakara", "Koyilandy", "Mukkam", "Thamarassery"}


def projected_boundary(atlas_path: Path):
    atlas = json.loads(atlas_path.read_text())
    boundary = next(
        f
        for f in atlas["features"]
        if f.get("properties", {}).get("kind") == "boundary"
    )
    geom = shape(boundary["geometry"])
    if geom.is_empty or not geom.is_valid:
        raise ValueError("boundary is empty or invalid")
    to_utm = Transformer.from_crs("EPSG:4326", CRS, always_xy=True).transform
    return shp_transform(to_utm, geom), atlas


def rings_xy(geom):
    polygons = list(geom.geoms) if geom.geom_type == "MultiPolygon" else [geom]
    out = []
    for poly in polygons:
        out.append([[float(x), float(y)] for x, y in poly.exterior.coords])
        # Preserve holes as additional rings; consumers can use ring orientation.
        out.extend(
            [[[float(x), float(y)] for x, y in hole.coords] for hole in poly.interiors]
        )
    return out


def point_height(arr, transform, x, y, radius=3):
    col, row = (~transform) * (x, y)
    col, row = int(round(col - 0.5)), int(round(row - 0.5))
    r0, r1 = max(0, row - radius), min(arr.shape[0], row + radius + 1)
    c0, c1 = max(0, col - radius), min(arr.shape[1], col + radius + 1)
    window = arr[r0:r1, c0:c1]
    valid = window[np.isfinite(window)]
    if valid.size == 0:
        return None
    # nearest valid local sample, rather than spatially averaging a settlement's height
    ys, xs = np.where(np.isfinite(window))
    i = np.argmin((ys + r0 - row) ** 2 + (xs + c0 - col) ** 2)
    return float(valid[i])


def prepare(dem_path: Path, atlas_path: Path, output_path: Path, width=80, height=64):
    boundary, atlas = projected_boundary(atlas_path)
    minx, miny, maxx, maxy = boundary.bounds
    dst_transform = from_bounds(minx, miny, maxx, maxy, width, height)
    dst = np.full((height, width), np.nan, dtype="float32")
    with rasterio.open(dem_path) as src:
        if src.crs is None or src.crs.to_epsg() != 4326:
            raise ValueError(f"expected EPSG:4326 DEM, got {src.crs}")
        if src.nodata is None:
            raise ValueError("DEM has no declared nodata value")
        reproject(
            source=rasterio.band(src, 1),
            destination=dst,
            src_transform=src.transform,
            src_crs=src.crs,
            src_nodata=src.nodata,
            dst_transform=dst_transform,
            dst_crs=CRS,
            dst_nodata=np.nan,
            resampling=Resampling.average,
        )
        source_tags = src.tags()

    # Mask cell centers to the district, and make negative coastal/noisy values null.
    inside = np.zeros((height, width), dtype=bool)
    for row in range(height):
        for col in range(width):
            x, y = dst_transform * (col + 0.5, row + 0.5)
            inside[row, col] = boundary.covers(Point(x, y))
    dst[~inside] = np.nan
    dst[dst < 0] = np.nan
    finite = np.isfinite(dst)
    if not finite.any():
        raise ValueError("no valid masked elevation cells")

    places = []
    to_utm = Transformer.from_crs("EPSG:4326", CRS, always_xy=True).transform
    for feature in atlas["features"]:
        props = feature.get("properties", {})
        if props.get("kind") != "settlement" or props.get("name") not in PLACES:
            continue
        lon, lat = feature["geometry"]["coordinates"]
        easting, northing = to_utm(lon, lat)
        h = point_height(dst, dst_transform, easting, northing)
        places.append(
            {
                "name": props["name"],
                "easting": float(easting),
                "northing": float(northing),
                "height": h,
            }
        )
    places.sort(key=lambda p: p["name"])
    if len(places) != len(PLACES):
        missing = sorted(PLACES - {p["name"] for p in places})
        raise ValueError(f"missing required settlement points: {missing}")

    payload = {
        "width": width,
        "height": height,
        "extent": [float(minx), float(miny), float(maxx), float(maxy)],
        "heights": [None if not np.isfinite(v) else float(v) for v in dst.ravel()],
        "boundary": rings_xy(boundary),
        "places": places,
        "crs": CRS,
        "verticalDatum": "EGM2008",
        "source": SOURCE,
        "sourceUrl": SOURCE_URL,
        "release": "2021",
        "gridSpacingM": [float(dst_transform.a), float(abs(dst_transform.e))],
        "minHeightM": float(np.nanmin(dst)),
        "maxHeightM": float(np.nanmax(dst)),
        "limitations": "Copernicus GLO-30 is a DSM, so vegetation and buildings may affect heights; values are cell-average aggregates on an 80x64 district grid; district-outside, source NoData, and negative elevations are null; vertical datum is EGM2008.",
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, separators=(",", ":"), allow_nan=False) + "\n"
    )
    # Assertions are deliberately after writing so failures are visible in CI and reruns remain idempotent.
    assert len(payload["heights"]) == width * height
    assert sum(v is not None for v in payload["heights"]) == int(finite.sum())
    assert payload["heights"][0] == (None if not finite[0, 0] else float(dst[0, 0]))
    print(
        json.dumps(
            {
                "output": str(output_path),
                "validCells": int(finite.sum()),
                "totalCells": width * height,
                "minHeightM": payload["minHeightM"],
                "maxHeightM": payload["maxHeightM"],
                "gridSpacingM": payload["gridSpacingM"],
                "sourceTags": source_tags,
            },
            indent=2,
        )
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dem", type=Path, default=Path("raw/thematic/dem_mosaic_4326.tif")
    )
    parser.add_argument("--atlas", type=Path, default=Path("site/data/atlas.geojson"))
    parser.add_argument(
        "--output", type=Path, default=Path("site/data/terrain-3d.json")
    )
    parser.add_argument("--width", type=int, default=80)
    parser.add_argument("--height", type=int, default=64)
    args = parser.parse_args()
    if args.width > 80 or args.height > 64:
        parser.error("grid dimensions may not exceed 80x64")
    prepare(args.dem, args.atlas, args.output, args.width, args.height)


if __name__ == "__main__":
    main()
