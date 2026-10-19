#!/usr/bin/env python3
"""Prepare GSI 2022 / KSDMA landslide classes; no new prediction model.

Retains source classes, repairs invalid multipart polygons in their native UTM
CRS, clips to the atlas DISTRICT boundary, and rasterizes pixel centres onto the
existing query/display grid. Unmapped district cells are explicit, never Low.
"""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import urllib.request
import zipfile
import geopandas as gpd
import numpy as np
from PIL import Image
from pyproj import Transformer
from rasterio.features import rasterize, geometry_mask
from rasterio.transform import Affine
from shapely import make_valid
from shapely.geometry import shape

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "raw/landslides"
DATA = ROOT / "site/data"
URL = "https://sdma.kerala.gov.in/wp-content/uploads/2025/08/Kozhikode.zip"
SOURCE = "https://sdma.kerala.gov.in/hazard-maps/"
CLASSES = {1: "Low", 2: "Moderate", 3: "High", 4: "Not mapped in source"}
COLORS = {1: "#fff7bc", 2: "#fec44f", 3: "#993404", 4: "#d6dce0"}
LIMITS = (
    "Relative susceptibility zones, not numerical probabilities, live warnings or a site-safety assessment. "
    "Low does not mean safe. Grey is not mapped in the supplied source, not zero susceptibility. "
    "No current rainfall, soil saturation or field validation is added. Debris runout can affect land beyond mapped zones. "
    "The source and atlas district boundaries differ; source gaps are retained. Display cells generalise zone edges. "
    "Consult KSDMA and local authorities for current warnings and qualified specialists for site decisions."
)


def main():
    RAW.mkdir(parents=True, exist_ok=True)
    archive = RAW / "Kozhikode.zip"
    if not archive.exists():
        urllib.request.urlretrieve(URL, archive)
    with zipfile.ZipFile(archive) as z:
        z.extractall(RAW)
    src = gpd.read_file(RAW / "Kozhikode/Kozhikode_GSI_LS.shp")
    assert src.crs.to_epsg() == 32643, "Do not guess source CRS"
    assert len(src) == 3 and set(src.Susceptibi) == {"High", "Low", "Moderate"}
    assert not src.geometry.is_empty.any() and not src.geometry.isna().any()
    atlas = json.loads((DATA / "atlas.geojson").read_text())
    boundary = shape(
        next(
            f["geometry"]
            for f in atlas["features"]
            if f["properties"]["kind"] == "boundary"
        )
    )
    district = gpd.GeoSeries([make_valid(boundary)], crs=4326).to_crs(src.crs).iloc[0]
    records, geometries = [], {}
    for _, row in src.iterrows():
        original = row.geometry
        fixed = make_valid(original)
        assert fixed.geom_type in ("Polygon", "MultiPolygon") and fixed.is_valid
        clipped = make_valid(fixed.intersection(district))
        assert clipped.is_valid and not clipped.is_empty
        records.append(
            {
                "class": row.Susceptibi,
                "invalidBefore": not original.is_valid,
                "areaBeforeRepairM2": original.area,
                "areaAfterRepairM2": fixed.area,
                "areaAfterDistrictClipM2": clipped.area,
            }
        )
        geometries[row.Susceptibi] = clipped
    # Save the repaired analysis artifact outside the published runtime folder.
    gpkg = RAW / "kozhikode-gsi-2022-clipped.gpkg"
    if gpkg.exists():
        gpkg.unlink()
    gpd.GeoDataFrame(
        {"susceptibility": list(geometries)},
        geometry=list(geometries.values()),
        crs=src.crs,
    ).to_file(gpkg, layer="susceptibility", driver="GPKG")
    inspector = json.loads((DATA / "inspector.json").read_text())
    grid = inspector["grid"]
    h, w = grid["height"], grid["width"]
    transform = Affine(*grid["transform"][:6])
    district3857 = gpd.GeoSeries([make_valid(boundary)], crs=4326).to_crs(3857).iloc[0]
    mask = geometry_mask([district3857], (h, w), transform, invert=True)
    projected = {
        name: gpd.GeoSeries([g], crs=src.crs).to_crs(3857).iloc[0]
        for name, g in geometries.items()
    }
    burns = {}
    for code in (1, 2, 3):
        burns[code] = rasterize(
            [(projected[CLASSES[code]], code)],
            (h, w),
            transform=transform,
            dtype="uint8",
            fill=0,
        )
    overlap = sum((a > 0).astype("uint8") for a in burns.values())
    values = np.where(mask, 4, 0).astype("uint8")
    for code in (1, 2, 3):
        values[mask & (burns[code] > 0)] = code
    assert not np.any(values[~mask])
    rgba = np.zeros((h, w, 4), dtype="uint8")
    for code, color in COLORS.items():
        rgba[values == code] = [int(color[i : i + 2], 16) for i in (1, 3, 5)] + [255]
    Image.fromarray(rgba).save(DATA / "landslide-susceptibility.png", optimize=True)
    # Red channel contains the exact categorical code used by inspector.js.
    rgb = np.zeros((h, w, 3), dtype="uint8")
    rgb[:, :, 0] = values
    rgb[:, :, 2] = 255
    Image.fromarray(rgb).save(DATA / "inspector-landslide.png", optimize=True)
    definition = {
        "image": "inspector-landslide.png",
        "encoding": "uint8",
        "scale": 1,
        "offset": 0,
        "nodata": 0,
        "units": "GSI susceptibility class (not probability)",
        "classCodes": CLASSES,
        "source": "Geological Survey of India (GSI), via KSDMA",
        "sourceUrl": SOURCE,
        "period": "GSI April 2022; KSDMA shapefile published August 2025",
        "date": "GSI 2022",
        "resolution": "1:50,000 GSI NLSM programme scale; original district cell size and positional accuracy not established; ~100 m atlas query cells are display sampling",
        "method": "Native UTM43N polygon repair and district clip; pixel-centre categorical rasterization on shared query grid.",
    }
    definition["rights"] = (
        "GSI web-display and redistribution rights remain unresolved. Attribution, this caveat and owner approval do not grant permission."
    )
    definition["rightsNoticeFile"] = "GSI_RIGHTS.md"
    inspector["datasets"]["landslide"] = definition
    (DATA / "inspector.json").write_text(json.dumps(inspector, indent=2) + "\n")
    meta = json.loads((DATA / "thematic.json").read_text())
    template = next(x for x in meta["layers"] if x["id"] == "slope")
    layer = {
        "id": "landslide",
        "title": "Landslide susceptibility · GSI zones",
        "image": "landslide-susceptibility.png",
        "bounds": template["bounds"],
        "legend": [
            {
                "label": CLASSES[c]
                + (" susceptibility" if c < 4 else " · not safe by default"),
                "color": COLORS[c],
            }
            for c in COLORS
        ],
        "source": definition["source"],
        "sourceUrl": SOURCE,
        "license": "GSI web-display and redistribution rights remain unresolved. Source attribution, this caveat and owner approval do not grant permission. Public download is not an open reuse licence; source rights retained.",
        "period": definition["period"],
        "resolution": definition["resolution"],
        "method": definition["method"]
        + " Source Low, Moderate and High labels retained unchanged; no DEM-derived prediction or weighting.",
        "limitations": LIMITS,
        "inputCrs": "EPSG:32643",
        "displayCrs": "EPSG:3857",
        "coverage": "Kozhikode district; mapped source zones plus explicitly unmapped district cells",
        "attribution": "Geological Survey of India, 2022 / Kerala State Disaster Management Authority. Atlas display adaptation, not an official warning product.",
        "provenanceFile": "landslide-provenance.json",
    }
    layer["rightsStatus"] = "unresolved"
    layer["rightsNoticeFile"] = "GSI_RIGHTS.md"
    layer["permanentGsiRedistributionCleared"] = False
    layer["stats"] = {
        "validPixels": int(mask.sum()),
        "totalPixels": int(values.size),
        "validFraction": float(mask.mean()),
        "unmappedDistrictPixels": int((values == 4).sum()),
        "note": "Visible coverage includes explicit unmapped grey cells; pixel counts are not area estimates.",
    }
    meta["layers"] = [x for x in meta["layers"] if x["id"] != "landslide"] + [layer]
    (DATA / "thematic.json").write_text(json.dumps(meta, indent=2) + "\n")
    to_ll = Transformer.from_crs(3857, 4326, always_xy=True)
    samples = []
    for code in CLASSES:
        rows, cols = np.where(values == code)
        assert len(rows) > 0
        # Validate three rendered cells against source polygon membership, not colour alone.
        for index in (len(rows) // 4, len(rows) // 2, 3 * len(rows) // 4):
            y, x = int(rows[index]), int(cols[index])
            px, py = transform * (x + 0.5, y + 0.5)
            from shapely.geometry import Point

            point = Point(px, py)
            membership = [c for c in (1, 2, 3) if projected[CLASSES[c]].covers(point)]
            assert (code == 4 and not membership) or (code < 4 and code in membership)
            lon, lat = to_ll.transform(px, py)
            samples.append(
                {
                    "classCode": code,
                    "class": CLASSES[code],
                    "row": y,
                    "column": x,
                    "longitude": lon,
                    "latitude": lat,
                }
            )
    provenance = {
        "sourceUrl": SOURCE,
        "downloadUrl": URL,
        "officialMapUrl": "https://sdma.kerala.gov.in/wp-content/uploads/2025/06/Landslide_Susceptibility_Zones_Districts_FINAL.pdf",
        "sourceSHA256": hashlib.sha256(archive.read_bytes()).hexdigest(),
        "retrievedUTC": datetime.now(timezone.utc).isoformat(),
        "sourcePeriod": layer["period"],
        "inputCrs": str(src.crs),
        "sourceFeatureCount": len(src),
        "sourceField": "Susceptibi",
        "geometryAccounting": records,
        "grid": grid,
        "classCodes": CLASSES,
        "colors": COLORS,
        "pixelCounts": {CLASSES[c]: int((values == c).sum()) for c in CLASSES},
        "overlappingClassPixelCentres": int(((overlap > 1) & mask).sum()),
        "overlapRule": "If source classes overlap at a pixel centre, High overrides Moderate overrides Low; conflicts recorded, not blended.",
        "displayNotAreaEstimate": True,
        "sampleChecks": samples,
        "method": layer["method"],
        "limitations": LIMITS,
        "license": layer["license"],
        "attribution": layer["attribution"],
        "sourceScale": "Not specified by supplied shapefile metadata; do not infer site-level accuracy from display pixel size.",
        "pipeline": "scripts/prepare_landslides.py",
    }
    provenance["rightsStatus"] = "unresolved"
    provenance["rightsNoticeFile"] = "GSI_RIGHTS.md"
    provenance["permanentGsiRedistributionCleared"] = False
    (DATA / "landslide-provenance.json").write_text(
        json.dumps(provenance, indent=2) + "\n"
    )
    (RAW / "DATA_SOURCES.md").write_text(
        "# Kozhikode landslide susceptibility\n\nGSI 2022, served by KSDMA. "
        + SOURCE
        + "\n\nDownload: "
        + URL
        + "\n\n"
        + layer["license"]
        + "\n\n"
        + LIMITS
        + "\n"
    )
    print(
        json.dumps(
            {
                "features": len(src),
                "geometryAccounting": records,
                "pixelCounts": provenance["pixelCounts"],
                "overlapPixels": provenance["overlappingClassPixelCentres"],
                "verifiedSamples": len(samples),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
