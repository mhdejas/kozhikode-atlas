#!/usr/bin/env python3
"""Prepare lossless click-inspector assets from the shared thematic grid."""
from __future__ import annotations
import argparse, json, math, struct, zlib
from pathlib import Path
import numpy as np
import rasterio
from pyproj import Transformer

DATE = "2026-10-19"
WGS84_TO_UTM = Transformer.from_crs("EPSG:4326", "EPSG:32643", always_xy=True)


def png_rgb(path: Path, rgb: np.ndarray) -> None:
    """Write an 8-bit, non-interlaced RGB PNG without palette/alpha."""
    if rgb.dtype != np.uint8 or rgb.ndim != 3 or rgb.shape[2] != 3:
        raise ValueError("expected uint8 HxWx3 RGB array")
    h, w, _ = rgb.shape
    raw = b"".join(b"\x00" + row.tobytes() for row in rgb)

    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + kind
            + data
            + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )


def round_coords(c):
    if isinstance(c, (list, tuple)):
        return [round_coords(x) for x in c]
    return round(float(c), 1)


def project_geometry(g):
    t = g["type"]
    c = g.get("coordinates")

    def xy(p):
        x, y = WGS84_TO_UTM.transform(float(p[0]), float(p[1]))
        return [round(x, 1), round(y, 1)]

    def walk(v):
        if isinstance(v, (list, tuple)) and v and isinstance(v[0], (int, float)):
            return xy(v)
        return [walk(x) for x in v]

    return {"type": t, "coordinates": walk(c)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = ap.parse_args()
    root = args.root
    raw = root / "raw/thematic"
    out = root / "site/data"
    out.mkdir(parents=True, exist_ok=True)
    paths = {
        k: raw / f"{k}_display_3857.tif" for k in ("elevation", "slope", "landcover")
    }
    arrays = {}
    meta = {}
    for k, p in paths.items():
        with rasterio.open(p) as s:
            arrays[k] = s.read(1, masked=True)
            meta[k] = {
                "width": s.width,
                "height": s.height,
                "crs": s.crs.to_string(),
                "bounds": [
                    s.bounds.left,
                    s.bounds.bottom,
                    s.bounds.right,
                    s.bounds.top,
                ],
                "transform": list(s.transform),
                "xResolution": abs(s.transform.a),
                "yResolution": abs(s.transform.e),
                "sourceNodata": s.nodata,
            }
    base = meta["elevation"]
    for k in ("slope", "landcover"):
        if any(
            meta[k][x] != base[x]
            for x in ("width", "height", "crs", "bounds", "transform")
        ):
            raise RuntimeError(f"{k} is not on the shared grid")
    h, w = base["height"], base["width"]

    # Each value occupies two 8-bit channels (high then low); all outputs are opaque RGB.
    def u16_rgb(values, valid):
        vals = np.where(valid, values, 65535).astype(np.uint16)
        return np.stack(
            [
                (vals >> 8).astype(np.uint8),
                (vals & 255).astype(np.uint8),
                np.full((h, w), 255, np.uint8),
            ],
            axis=2,
        )

    elev = arrays["elevation"]
    ev = ~elev.mask
    elev_i = np.rint(np.asarray(elev.filled(0))).clip(0, 65534)
    png_rgb(out / "inspector-elevation.png", u16_rgb(elev_i, ev))
    slope = arrays["slope"]
    sv = ~slope.mask
    slope_i = np.rint(np.asarray(slope.filled(0)) * 100).clip(0, 65534)
    png_rgb(out / "inspector-slope.png", u16_rgb(slope_i, sv))
    lc = arrays["landcover"]
    lv = ~lc.mask
    lcv = np.asarray(lc.filled(0), dtype=np.uint8)
    rgb = np.stack(
        [
            np.where(lv, lcv, 0),
            np.full((h, w), 255, np.uint8),
            np.full((h, w), 255, np.uint8),
        ],
        axis=2,
    )
    png_rgb(out / "inspector-landcover.png", rgb)

    thematic = json.loads((out / "thematic.json").read_text())
    layer_map = {x["id"]: x for x in thematic["layers"]}
    datasets = {}
    specs = {
        "elevation": {
            "image": "inspector-elevation.png",
            "encoding": "uint16",
            "scale": 1,
            "offset": 0,
            "nodata": 65535,
            "units": "m",
            "method": "rounded to integer metres from the existing shared-grid display raster",
        },
        "slope": {
            "image": "inspector-slope.png",
            "encoding": "uint16",
            "scale": 0.01,
            "offset": 0,
            "nodata": 65535,
            "units": "degrees",
            "method": "rounded to 0.01 degree from the existing shared-grid display raster",
        },
        "landcover": {
            "image": "inspector-landcover.png",
            "encoding": "uint8",
            "scale": 1,
            "offset": 0,
            "nodata": 0,
            "units": "ESA WorldCover class code",
            "method": "copied class code from the existing shared-grid display raster",
            "classCodes": {
                "10": "Tree cover",
                "20": "Shrubland",
                "30": "Grassland",
                "40": "Cropland",
                "50": "Built-up",
                "60": "Bare / sparse vegetation",
                "80": "Permanent water",
                "90": "Herbaceous wetland",
                "95": "Mangroves",
            },
        },
    }
    for k, sp in specs.items():
        src = layer_map[k]
        sp.update(
            {
                "source": src.get("source"),
                "sourceUrl": src.get("sourceUrl"),
                "period": src.get("period"),
                "date": src.get("period"),
                "resolution": src.get("resolution"),
                "provenance": {
                    "input": f"raw/thematic/{k}_display_3857.tif",
                    "source": src.get("source"),
                    "sourceUrl": src.get("sourceUrl"),
                    "date": src.get("period"),
                    "resolution": src.get("resolution"),
                    "method": src.get("method"),
                    "displayValues": "~100 m query grid; not native 10 m data",
                },
            }
        )
        datasets[k] = sp
    grid = {
        "crs": "EPSG:3857",
        "bounds3857": base["bounds"],
        "width": w,
        "height": h,
        "transform": base["transform"],
        "pixelSize": [base["xResolution"], base["yResolution"]],
        "note": "Values are sampled from the existing ~100 m query grid, not native 10 m measurements.",
    }
    (out / "inspector.json").write_text(
        json.dumps({"version": 1, "grid": grid, "datasets": datasets}, indent=2) + "\n"
    )

    atlas = json.loads((out / "atlas.geojson").read_text())
    features = []
    for f in atlas.get("features", []):
        p = f.get("properties") or {}
        name = p.get("name")
        if not name or p.get("kind") == "boundary":
            continue
        if not f.get("geometry"):
            continue
        features.append(
            {
                "name": str(name),
                "kind": p.get("kind"),
                "source": p.get(
                    "source", "OpenStreetMap contributors via Overpass API"
                ),
                "osm_id": p.get("osm_id"),
                "date": DATE,
                "geometry": project_geometry(f["geometry"]),
            }
        )
    features.sort(
        key=lambda x: (x["name"].casefold(), x["kind"] or "", str(x.get("osm_id")))
    )
    contract = {
        "crs": "EPSG:32643",
        "date": DATE,
        "source": "site/data/atlas.geojson; named features only; district boundary excluded",
        "features": features,
    }
    (out / "inspector-features.json").write_text(
        json.dumps(contract, separators=(",", ":"), ensure_ascii=False) + "\n"
    )
    print(
        json.dumps(
            {
                "grid": [w, h],
                "features": len(features),
                "outputs": [
                    str(out / x)
                    for x in (
                        "inspector.json",
                        "inspector-elevation.png",
                        "inspector-slope.png",
                        "inspector-landcover.png",
                        "inspector-features.json",
                    )
                ],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
