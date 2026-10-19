#!/usr/bin/env python3
"""Matched 2019/2025 Earth Engine composites; exploratory built-up signals.
Run: python scripts/urban_gee.py --project YOUR_REGISTERED_PROJECT
Requires authenticated earthengine-api. Credentials/URLs never enter published files.
No validated urban-area estimate is produced by this exploratory workflow.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import io
import json
import math
from pathlib import Path
import time

import ee
import numpy as np
from PIL import Image
from pyproj import Transformer
import rasterio
from rasterio.features import geometry_mask, sieve
from rasterio.transform import from_bounds
import requests

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "raw" / "urban"
DATA = ROOT / "site" / "data"
S2 = "COPERNICUS/S2_SR_HARMONIZED"
CS = "GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED"
DW = "GOOGLE/DYNAMICWORLD/V1"
YEARS = [2019, 2025]
BANDS = ["B4", "B3", "B2"]
SCALE = 20
MIN_OBS = 3


def fingerprint(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(year, aoi):
    start, end = f"{year}-01-01", f"{year}-04-01"
    cs = ee.ImageCollection(CS).filterBounds(aoi).filterDate(start, end)
    base = (
        ee.ImageCollection(S2)
        .filterBounds(aoi)
        .filterDate(start, end)
        .filter(ee.Filter.lte("CLOUDY_PIXEL_PERCENTAGE", 80))
    )

    def clear(img):
        scl = img.select("SCL")
        # Cloud Score+ plus explicit SCL exclusions; never use QA60's missing era.
        usable = img.select("cs_cdf").gte(0.60)
        for code in [0, 1, 3, 8, 9, 10, 11]:
            usable = usable.And(scl.neq(code))
        return (
            img.select(BANDS)
            .updateMask(usable)
            .copyProperties(img, ["system:time_start"])
        )

    masked = base.linkCollection(cs, ["cs_cdf"]).map(clear)
    count = masked.select("B4").count().rename("rgb_count")
    rgb = masked.median().round().toUint16()
    dw = ee.ImageCollection(DW).filterBounds(aoi).filterDate(start, end)
    built = dw.select("built").mean().multiply(10000).round().rename("built_scaled")
    dwcount = dw.select("built").count().rename("dw_count")
    image = rgb.addBands(count).addBands(built).addBands(dwcount).toUint16().clip(aoi)
    return image, base, dw, cs


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--workers", type=int, default=3)
    args = parser.parse_args()
    ee.Initialize(project=args.project)
    ee.data.setDeadline(240000)
    RAW.mkdir(parents=True, exist_ok=True)
    atlas = json.loads((DATA / "atlas.geojson").read_text())
    geometry = next(
        f["geometry"]
        for f in atlas["features"]
        if f["properties"]["kind"] == "boundary"
    )
    aoi = ee.Geometry(geometry, proj="EPSG:4326", geodesic=False)
    thematic = json.loads((DATA / "thematic.json").read_text())
    bbox = thematic["displayGrid"]["bounds3857"]
    w, s, e, n = bbox
    width = math.ceil((e - w) / SCALE)
    height = math.ceil((n - s) / SCALE)
    # Preserve exactly the same outer extent as the existing map; record effective pixel size.
    transform = from_bounds(w, s, e, n, width, height)
    manifest = {
        "status": "running",
        "runUtc": datetime.now(timezone.utc).isoformat(),
        "eeClientVersion": ee.__version__,
        "collections": [S2, CS, DW],
        "boundarySource": "Existing atlas geoBoundaries gbOpen Kozhikode (2021)",
        "boundarySha256": fingerprint(DATA / "atlas.geojson"),
        "periods": {},
        "cloudMask": {
            "cs_cdf_min": 0.60,
            "excludedSCL": [0, 1, 3, 8, 9, 10, 11],
            "sceneCloudMaxPercent": 80,
        },
        "rgbReducer": "per-band median before visualization; reflectance = harmonized DN / 10000",
        "builtReducer": "mean Dynamic World built probability; source product already cloud/shadow masked",
        "minimumObservationsEachDate": MIN_OBS,
        "grid": {
            "crs": "EPSG:3857",
            "width": width,
            "height": height,
            "transform": list(transform)[:6],
            "bounds3857": bbox,
            "nominalDisplayMetres": 20,
        },
        "export": {
            "method": "bounded synchronous getDownloadURL, 3x3 shards/date",
            "fileFormat": "GEO_TIFF",
            "scaleExplicitViaTransform": True,
            "unmask": 65535,
            "bestEffort": False,
        },
        "rgbVisualization": {"bands": BANDS, "minDN": 0, "maxDN": 3000, "gamma": 1.2},
        "candidateRules": {
            "beforeBuiltMax": 0.20,
            "afterBuiltMin": 0.60,
            "minimumConnectedPixels": 9,
            "connectivity": 8,
            "thresholdsSensitivity": [0.50, 0.60, 0.70],
        },
        "claims": "Exploratory visual comparison and model signals only. No ground-validation accuracy or error-adjusted urban-area estimate.",
    }
    images = {}
    for year in YEARS:
        print(f"{year}: catalog and processing metadata", flush=True)
        image, base, dw, cs = build(year, aoi)
        info = ee.Dictionary(
            {
                "s2_ids": base.aggregate_array("system:index"),
                "s2_baselines": base.aggregate_array("PROCESSING_BASELINE").distinct(),
                "dw_ids": dw.aggregate_array("system:index"),
                "dw_model_versions": dw.aggregate_array(
                    "dynamicworld_algorithm_version"
                ).distinct(),
                "dw_qa_versions": dw.aggregate_array("qa_algorithm_version").distinct(),
                "cloud_score_models": cs.aggregate_array("MODEL_VERSION").distinct(),
                "source_projection": (
                    base.first().select("B4").projection().getInfo()
                    if False
                    else base.first().select("B4").projection()
                ),
            }
        ).getInfo()
        if not info["s2_ids"] or not info["dw_ids"]:
            raise RuntimeError(
                f"No matching source observations for {year}; no assets published"
            )
        manifest["periods"][str(year)] = {
            "start": f"{year}-01-01",
            "endExclusive": f"{year}-04-01",
            **info,
        }
        images[year] = image
    (RAW / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    tasks = []
    for year in YEARS:
        for iy in range(3):
            y0, y1 = height * iy // 3, height * (iy + 1) // 3
            for ix in range(3):
                x0, x1 = width * ix // 3, width * (ix + 1) // 3
                tasks.append((year, iy, ix, x0, y0, x1 - x0, y1 - y0))

    def download(task):
        year, iy, ix, x, y, tw, th = task
        path = RAW / f"{year}-{iy}-{ix}.tif"
        if path.exists():
            with rasterio.open(path) as src:
                if src.width == tw and src.height == th and src.count == 6:
                    return task, path
        tile_transform = transform * rasterio.Affine.translation(x, y)
        for attempt in range(3):
            try:
                url = (
                    images[year]
                    .unmask(65535)
                    .getDownloadURL(
                        {
                            "name": f"kozhikode-{year}-{iy}-{ix}",
                            "crs": "EPSG:3857",
                            "crs_transform": list(tile_transform)[:6],
                            "dimensions": [tw, th],
                            "format": "GEO_TIFF",
                            "filePerBand": False,
                        }
                    )
                )
                response = requests.get(url, timeout=260)
                if response.status_code != 200:
                    raise RuntimeError(
                        f"Earth Engine export HTTP {response.status_code}"
                    )
                with rasterio.MemoryFile(response.content) as mem:
                    with mem.open() as src:
                        if (src.width, src.height, src.count) != (tw, th, 6):
                            raise RuntimeError("Export dimensions or bands mismatch")
                path.write_bytes(response.content)
                return task, path
            except Exception as exc:
                # Exception URLs may contain temporary export credentials: do not log raw errors.
                print(
                    f"{year} shard {iy},{ix}: retry {attempt+1} ({type(exc).__name__})",
                    flush=True,
                )
                if attempt == 2:
                    raise RuntimeError(
                        f"Export failed for {year} shard {iy},{ix}; no analysis claimed"
                    ) from None
                time.sleep(5)

    arrays = {
        year: np.full((6, height, width), 65535, dtype=np.uint16) for year in YEARS
    }
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(download, t) for t in tasks]
        for future in as_completed(futures):
            task, path = future.result()
            year, iy, ix, x, y, tw, th = task
            with rasterio.open(path) as src:
                arrays[year][:, y : y + th, x : x + tw] = src.read()
            print(f"{year}: shard {iy},{ix} complete", flush=True)
    in_district = (
        geometry_mask([geometry], (height, width), transform=transform, invert=True)
        if False
        else None
    )
    # Geometry mask must use grid CRS, not longitude/latitude coordinates.
    from rasterio.warp import transform_geom

    in_district = geometry_mask(
        [transform_geom("EPSG:4326", "EPSG:3857", geometry)],
        (height, width),
        transform=transform,
        invert=True,
    )
    rgb_valid = {
        year: in_district
        & (a[3] >= MIN_OBS)
        & (a[3] != 65535)
        & np.all(a[:3] != 65535, axis=0)
        for year, a in arrays.items()
    }
    common_rgb = rgb_valid[2019] & rgb_valid[2025]
    dw_valid = {
        year: in_district & (a[5] >= MIN_OBS) & (a[5] != 65535) & (a[4] <= 10000)
        for year, a in arrays.items()
    }
    common = common_rgb & dw_valid[2019] & dw_valid[2025]
    if not common_rgb.any():
        raise RuntimeError("No mutually valid RGB pixels; no assets published")
    for year, a in arrays.items():
        scaled = np.clip(a[:3].astype(np.float32) / 3000, 0, 1) ** (1 / 1.2)
        rgba = np.concatenate(
            [
                np.moveaxis(np.round(scaled * 255).astype(np.uint8), 0, -1),
                (common_rgb.astype(np.uint8) * 255)[..., None],
            ],
            axis=2,
        )
        Image.fromarray(rgba).save(
            DATA / ("urban-before.png" if year == 2019 else "urban-after.png"),
            optimize=True,
        )
        profile = {
            "driver": "GTiff",
            "width": width,
            "height": height,
            "count": 6,
            "dtype": "uint16",
            "crs": "EPSG:3857",
            "transform": transform,
            "nodata": 65535,
        }
        with rasterio.open(
            RAW / f"urban-{year}.tif",
            "w",
            **{**profile, "driver": "COG", "compress": "DEFLATE"},
        ) as dst:
            dst.write(a)
            dst.descriptions = tuple(
                BANDS + ["rgb_count", "built_probability_x10000", "dw_count"]
            )
    old, new = arrays[2019][4] / 10000.0, arrays[2025][4] / 10000.0
    candidate = common & (old <= 0.20) & (new >= 0.60)
    # Minimum display mapping unit: 9 connected 20-m grid pixels; not a building detector.
    candidate = (
        sieve(candidate.astype("uint8"), size=9, connectivity=8).astype(bool)
        & candidate
    )
    persistent = common & (old >= 0.60) & (new >= 0.60)
    loss = common & (old >= 0.60) & (new <= 0.20)
    loss = sieve(loss.astype("uint8"), size=9, connectivity=8).astype(bool) & loss
    classes = np.zeros((height, width), dtype=np.uint8)
    classes[in_district] = 1  # gray unassessed area
    classes[common] = 2
    classes[persistent] = 3
    classes[loss] = 4
    classes[candidate] = 5
    palette = np.array(
        [
            [0, 0, 0, 0],
            [191, 191, 191, 255],
            [244, 241, 230, 255],
            [91, 89, 103, 255],
            [0, 114, 178, 255],
            [213, 94, 0, 255],
        ],
        dtype=np.uint8,
    )
    Image.fromarray(palette[classes]).save(DATA / "urban-candidates.png", optimize=True)
    with rasterio.open(
        RAW / "urban-signals.tif",
        "w",
        driver="COG",
        width=width,
        height=height,
        count=1,
        dtype="uint8",
        crs="EPSG:3857",
        transform=transform,
        nodata=0,
        compress="DEFLATE",
    ) as dst:
        dst.write(classes, 1)
    counts = {str(c): int((classes == c).sum()) for c in range(1, 6)}
    manifest["verification"] = {
        "inDistrictDisplayPixels": int(in_district.sum()),
        "commonRGBPixels": int(common_rgb.sum()),
        "commonRGBFraction": float(common_rgb.sum() / in_district.sum()),
        "commonAnalysisPixels": int(common.sum()),
        "commonAnalysisFraction": float(common.sum() / in_district.sum()),
        "perDateRGBValidPixels": {str(y): int(m.sum()) for y, m in rgb_valid.items()},
        "perDateDWValidPixels": {str(y): int(m.sum()) for y, m in dw_valid.items()},
        "signalClassPixels": counts,
        "rawGainSensitivityPixelsBeforeMMU": {
            str(t): int((common & (old <= 0.20) & (new >= t)).sum())
            for t in [0.50, 0.60, 0.70]
        },
        "reflectanceDNPercentiles": {
            str(y): np.percentile(arrays[y][:3, common_rgb], [1, 50, 99]).tolist()
            for y in YEARS
        },
        "registration": "Same explicit export grid verified; independent sub-pixel tie-point RMSE not measured.",
        "validation": "No independent stratified ground-reference sample; candidate signals are not confirmed urban expansion.",
    }
    # Cross-check a small server-side valid-observation scalar against the exported raster.
    loc = ee.Geometry.Point([75.8, 11.3]).transform("EPSG:3857")
    probe = (
        images[2019]
        .select("rgb_count")
        .reduceRegion(
            ee.Reducer.first(),
            loc,
            crs="EPSG:3857",
            crsTransform=list(transform)[:6],
            maxPixels=10,
        )
        .getInfo()
    )
    col, row = ~transform * Transformer.from_crs(4326, 3857, always_xy=True).transform(
        75.8, 11.3
    )
    local = int(arrays[2019][3, int(row), int(col)])
    manifest["verification"]["scalarCrossCheck"] = {
        "location": [75.8, 11.3],
        "serverRGBCount2019": probe.get("rgb_count"),
        "localRGBCount2019": local,
        "agrees": probe.get("rgb_count") == local,
    }
    if not manifest["verification"]["scalarCrossCheck"]["agrees"]:
        raise RuntimeError("Server/local cross-check failed")
    manifest["outputs"] = {
        p.name: {"sha256": fingerprint(p), "bytes": p.stat().st_size}
        for p in [
            DATA / "urban-before.png",
            DATA / "urban-after.png",
            DATA / "urban-candidates.png",
        ]
    }
    manifest["status"] = "completed"
    (RAW / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (DATA / "urban-provenance.json").write_text(json.dumps(manifest, indent=2) + "\n")
    legend = [
        {"label": "Candidate built-up gain", "color": "#d55e00"},
        {"label": "Persistent high built signal", "color": "#5b5967"},
        {"label": "Candidate built-up loss", "color": "#0072b2"},
        {"label": "Other assessed pixels", "color": "#f4f1e6"},
        {"label": "Insufficient observations", "color": "#bfbfbf"},
    ]
    entry = {
        "id": "urban",
        "title": "Urban change · 2019–2025",
        "image": "urban-after.png",
        "beforeImage": "urban-before.png",
        "afterImage": "urban-after.png",
        "gainImage": "urban-candidates.png",
        "bounds": thematic["layers"][0]["bounds"],
        "legend": legend,
        "source": "Harmonized Sentinel-2 L2A / Cloud Score+ / Dynamic World V1; computed with Google Earth Engine",
        "sourceUrl": "https://developers.google.com/earth-engine/datasets/catalog/GOOGLE_DYNAMICWORLD_V1",
        "license": "Copernicus Sentinel Data Terms; Dynamic World and Cloud Score+ CC BY 4.0",
        "attribution": "Contains modified Copernicus Sentinel data 2019, 2025. Dynamic World produced by Google in partnership with National Geographic Society and the World Resources Institute.",
        "period": "1 January–31 March 2019 compared with 1 January–31 March 2025",
        "resolution": "10 m source RGB and model probabilities; 20 m aligned display grid",
        "method": f'Matched-season median surface-reflectance RGB; cs_cdf ≥0.60 plus SCL masks; ≥3 observations/date. Identical 0–0.30 reflectance stretch, gamma 1.2. Candidate gain: seasonal mean built probability ≤0.20 in 2019 and ≥0.60 in 2025; ≥9 connected display pixels. Common RGB coverage {manifest["verification"]["commonRGBFraction"]:.1%}; jointly assessed signal coverage {manifest["verification"]["commonAnalysisFraction"]:.1%}.',
        "limitations": "Candidate model signals, not verified new buildings or an urban-area estimate. Seasonal land management, exposed soil, haze, mixed pixels and classification errors can appear as change. Independent positional RMSE and ground-reference accuracy not measured. No-data is explicit; display is not native-resolution building detection.",
        "inputCrs": "Sentinel-2 MGRS UTM granules; see urban-provenance.json",
        "displayCrs": "EPSG:3857",
        "displayGrid": manifest["grid"],
        "stats": manifest["verification"],
        "provenanceFile": "urban-provenance.json",
    }
    thematic["layers"] = [x for x in thematic["layers"] if x["id"] != "urban"] + [entry]
    (DATA / "thematic.json").write_text(json.dumps(thematic, indent=2) + "\n")
    from optimize_urban_web import main as optimize_web

    optimize_web()
    print(json.dumps(manifest["verification"], indent=2), flush=True)
    print(
        "Earth Engine run completed; published genuine imagery and exploratory signal assets.",
        flush=True,
    )


if __name__ == "__main__":
    main()
