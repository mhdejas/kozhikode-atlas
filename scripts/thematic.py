#!/usr/bin/env python3
"""Build accurate Kozhikode thematic overlays.

All screen rasters are true RGBA pixel arrays (Pillow; no matplotlib figures),
warped to an EPSG:3857 grid at approximately 100 m/pixel. Continuous terrain
is analysed in metric EPSG:32643; categorical rasters use nearest resampling.
"""
from __future__ import annotations
import json, os, urllib.request
from datetime import date
import numpy as np
from PIL import Image
import rasterio
from rasterio.enums import Resampling
from rasterio.features import geometry_mask
from rasterio.merge import merge
from rasterio.transform import from_bounds
from rasterio.warp import calculate_default_transform, reproject, transform_geom
from shapely.geometry import shape

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "site/data")
RAW = os.path.join(ROOT, "raw/thematic")
BOUNDARY = os.path.join(ROOT, "raw/geoBoundaries-IND-ADM2.geojson")
os.makedirs(OUT, exist_ok=True)
os.makedirs(RAW, exist_ok=True)

# Requested fallback context, replaced by the actual Kozhikode boundary bbox below.
FALLBACK = (75.50, 11.10, 76.20, 11.85)
DEM_URLS = [
    "https://copernicus-dem-30m.s3.eu-central-1.amazonaws.com/Copernicus_DSM_COG_10_N11_00_E075_00_DEM/Copernicus_DSM_COG_10_N11_00_E075_00_DEM.tif",
    "https://copernicus-dem-30m.s3.eu-central-1.amazonaws.com/Copernicus_DSM_COG_10_N11_00_E076_00_DEM/Copernicus_DSM_COG_10_N11_00_E076_00_DEM.tif",
]
WC_URL = "https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/ESA_WorldCover_10m_2021_v200_N09E075_Map.tif"
DEM_LICENSE = "Copernicus DEM free public license"
WC_LICENSE = "Creative Commons Attribution 4.0 International (CC BY 4.0)"
RETRIEVED = date.today().isoformat()


def get_boundary():
    data = json.load(open(BOUNDARY, encoding="utf-8"))
    fs = [
        f
        for f in data["features"]
        if f.get("properties", {}).get("shapeName") == "Kozhikode"
    ]
    if not fs:
        return None, FALLBACK, "bbox context (Kozhikode boundary unavailable)"
    geom = shape(fs[0]["geometry"])
    return geom, geom.bounds, "geoBoundaries-IND-ADM2 Kozhikode polygon"


def download(url, path):
    if not os.path.exists(path) or os.path.getsize(path) < 10000:
        print("download", url)
        urllib.request.urlretrieve(url, path)


def write_geotiff(path, arr, profile, nodata=None):
    p = profile.copy()
    p.update(driver="GTiff", compress="deflate", predictor=2, tiled=True)
    if nodata is not None:
        p["nodata"] = nodata
    if nodata is not None and np.issubdtype(arr.dtype, np.floating):
        arr = np.where(np.isfinite(arr), arr, nodata)
    with rasterio.open(path, "w", **p) as dst:
        if arr.ndim == 2:
            dst.write(arr, 1)
        else:
            dst.write(arr)


def display_grid(bounds4326, resolution=100.0):
    # Make a regular Web-Mercator grid whose bounds are the transformed district bbox.
    left, bottom, right, top = rasterio.warp.transform_bounds(
        "EPSG:4326", "EPSG:3857", *bounds4326, densify_pts=21
    )
    width = max(1, int(np.ceil((right - left) / resolution)))
    height = max(1, int(np.ceil((top - bottom) / resolution)))
    transform = from_bounds(left, bottom, right, top, width, height)
    return transform, width, height, (left, bottom, right, top)


def warp_to(
    src_path,
    dst_crs,
    dst_transform,
    width,
    height,
    resampling,
    dtype="float32",
    src_nodata=None,
):
    out = np.full(
        (height, width), np.nan if dtype.startswith("float") else 0, dtype=dtype
    )
    with rasterio.open(src_path) as src:
        reproject(
            rasterio.band(src, 1),
            out,
            src_transform=src.transform,
            src_crs=src.crs,
            src_nodata=src_nodata if src_nodata is not None else src.nodata,
            dst_transform=dst_transform,
            dst_crs=dst_crs,
            dst_nodata=np.nan if dtype.startswith("float") else 0,
            resampling=resampling,
        )
    return out


def rgba_png(values, rgba, path, valid):
    # values are already classified integer indices; every visible pixel gets an exact palette color.
    out = np.zeros((values.shape[0], values.shape[1], 4), dtype=np.uint8)
    pal = np.array(
        [[int(c[i : i + 2], 16) for i in (1, 3, 5)] for c in rgba], dtype=np.uint8
    )
    ok = valid & (values >= 0) & (values < len(pal))
    out[ok, :3] = pal[values[ok]]
    out[ok, 3] = 255
    Image.fromarray(out).save(path, format="PNG", optimize=True)
    return out


def mask_for_grid(geom, crs, transform, width, height):
    if geom is None:
        return np.ones((height, width), dtype=bool)
    g = transform_geom("EPSG:4326", crs, geom.__geo_interface__)
    return ~geometry_mask(
        [g], out_shape=(height, width), transform=transform, invert=False
    )


def main():
    geom, bbox, coverage = get_boundary()
    west, south, east, north = bbox
    # retain a little context only when using the fallback; actual boundary bbox is exact.
    srcdate = RETRIEVED
    with open(os.path.join(RAW, "sources.txt"), "w", encoding="utf-8") as f:
        f.write(
            f"Retrieved {srcdate}\nCopernicus DEM tiles (both required):\n"
            + "\n".join(DEM_URLS)
            + f"\nESA WorldCover 2021 v200: {WC_URL}\nBoundary: {BOUNDARY}\n"
        )
    # Local DEM mosaic: explicitly acquire east tile; no artificial east coverage limitation.
    dem_paths = []
    for i, u in enumerate(DEM_URLS):
        p = os.path.join(RAW, f"dem_source_{i}.tif")
        download(u, p)
        dem_paths.append(p)
    srcs = [rasterio.open(p) for p in dem_paths]
    mosaic, trans = merge(srcs, bounds=FALLBACK, resampling=Resampling.bilinear)
    prof = srcs[0].profile.copy()
    prof.update(
        height=mosaic.shape[1],
        width=mosaic.shape[2],
        transform=trans,
        count=1,
        dtype="float32",
        nodata=-9999,
    )
    dem_mosaic = os.path.join(RAW, "dem_mosaic_4326.tif")
    write_geotiff(dem_mosaic, mosaic[0].astype("float32"), prof, -9999)
    for s in srcs:
        s.close()

    dtrans, dw, dh, dbounds = display_grid(bbox, 100.0)
    dmask = mask_for_grid(geom, "EPSG:3857", dtrans, dw, dh)
    # Elevation display: continuous source values, bilinear, then fixed non-negative bins.
    elev = warp_to(
        dem_mosaic, "EPSG:3857", dtrans, dw, dh, Resampling.bilinear, "float32", -9999
    )
    elev[~dmask] = np.nan
    valid_e = np.isfinite(elev) & (elev >= 0)
    elev_cls = np.digitize(elev, [0, 50, 200, 500, 1000], right=False) - 1
    elev_colors = ["#440154", "#3b528b", "#21918c", "#5ec962", "#fde725"]
    elev_labels = ["0–50 m", "50–200 m", "200–500 m", "500–1000 m", "≥1000 m"]
    elev_rgba = rgba_png(
        elev_cls, elev_colors, os.path.join(OUT, "thematic-elevation.png"), valid_e
    )
    write_geotiff(
        os.path.join(RAW, "elevation_display_3857.tif"),
        elev.astype("float32"),
        {
            "driver": "GTiff",
            "height": dh,
            "width": dw,
            "count": 1,
            "dtype": "float32",
            "crs": "EPSG:3857",
            "transform": dtrans,
        },
        -9999,
    )
    # Metric 90 m analysis grid for slope; source is ~30 m Copernicus DSM.
    aleft, abottom, aright, atop = rasterio.warp.transform_bounds(
        "EPSG:4326", "EPSG:32643", west, south, east, north, densify_pts=21
    )
    aw = max(1, int(np.ceil((aright - aleft) / 90)))
    ah = max(1, int(np.ceil((atop - abottom) / 90)))
    atrans = from_bounds(aleft, abottom, aright, atop, aw, ah)
    dem90 = warp_to(
        dem_mosaic, "EPSG:32643", atrans, aw, ah, Resampling.bilinear, "float32", -9999
    )
    # gradients only where a complete local 3x3 neighbourhood exists.
    xres = abs(atrans.a)
    yres = abs(atrans.e)
    valid90 = np.isfinite(dem90) & (dem90 >= 0)
    z = np.where(valid90, dem90, np.nan)
    gy, gx = np.gradient(z, yres, xres)
    slope = np.degrees(np.arctan(np.hypot(gx, gy))).astype("float32")
    slope[~valid90] = np.nan
    slope_path = os.path.join(RAW, "slope_analysis_utm32643_90m.tif")
    write_geotiff(
        slope_path,
        slope,
        {
            "driver": "GTiff",
            "height": ah,
            "width": aw,
            "count": 1,
            "dtype": "float32",
            "crs": "EPSG:32643",
            "transform": atrans,
        },
        -9999,
    )
    slope_display = warp_to(
        slope_path, "EPSG:3857", dtrans, dw, dh, Resampling.nearest, "float32", -9999
    )
    slope_display[~dmask] = np.nan
    slope_cls = np.digitize(slope_display, [0, 5, 15, 30], right=False) - 1
    slope_colors = ["#edf8fb", "#b2e2e2", "#66c2a4", "#238b45"]
    slope_labels = ["0–5°", "5–15°", "15–30°", "≥30°"]
    slope_valid = np.isfinite(slope_display) & (slope_display >= 0)
    rgba_png(
        slope_cls, slope_colors, os.path.join(OUT, "thematic-slope.png"), slope_valid
    )
    write_geotiff(
        os.path.join(RAW, "slope_display_3857.tif"),
        slope_display,
        {
            "driver": "GTiff",
            "height": dh,
            "width": dw,
            "count": 1,
            "dtype": "float32",
            "crs": "EPSG:3857",
            "transform": dtrans,
        },
        -9999,
    )

    # WorldCover categorical source and display nearest. WorldCover N09E075 is the 3x3-degree tile covering the bbox.
    wc_path = os.path.join(RAW, "worldcover_2021_v200_N09E075.tif")
    download(WC_URL, wc_path)
    wc = warp_to(wc_path, "EPSG:3857", dtrans, dw, dh, Resampling.nearest, "uint8", 0)
    wc[~dmask] = 0
    class_info = {
        10: ("Tree cover", "#009e73"),
        20: ("Shrubland", "#f0e442"),
        30: ("Grassland", "#ccebc5"),
        40: ("Cropland", "#e69f00"),
        50: ("Built-up", "#cc79a7"),
        60: ("Bare / sparse vegetation", "#bdbdbd"),
        70: ("Snow / ice", "#f7f7f7"),
        80: ("Permanent water", "#0072b2"),
        90: ("Herbaceous wetland", "#56b4e9"),
        95: ("Mangroves", "#8c510a"),
        100: ("Moss / lichen", "#8c6bb1"),
    }
    present = sorted(int(x) for x in np.unique(wc) if int(x) in class_info)
    wc_cls = np.full(wc.shape, -1, dtype="int16")
    wc_colors = []
    wc_labels = []
    for i, c in enumerate(present):
        wc_cls[wc == c] = i
        wc_colors.append(class_info[c][1])
        wc_labels.append(f"{c} — {class_info[c][0]}")
    wc_valid = wc_cls >= 0
    rgba_png(wc_cls, wc_colors, os.path.join(OUT, "thematic-landcover.png"), wc_valid)
    write_geotiff(
        os.path.join(RAW, "landcover_display_3857.tif"),
        wc.astype("uint8"),
        {
            "driver": "GTiff",
            "height": dh,
            "width": dw,
            "count": 1,
            "dtype": "uint8",
            "crs": "EPSG:3857",
            "transform": dtrans,
        },
        0,
    )

    bounds = [[float(south), float(west)], [float(north), float(east)]]

    def common_stats(arr, valid):
        v = arr[valid]
        return {
            "validPixels": int(v.size),
            "totalPixels": int(arr.size),
            "validFraction": float(v.size / arr.size),
            "min": float(np.nanmin(v)) if v.size else None,
            "max": float(np.nanmax(v)) if v.size else None,
        }

    layers = [
        {
            "id": "elevation",
            "title": "Elevation (m)",
            "image": "thematic-elevation.png",
            "bounds": bounds,
            "legend": [
                {"label": l, "color": c} for l, c in zip(elev_labels, elev_colors)
            ],
            "source": "Copernicus DEM GLO-30 Public (2021 release; DSM, EGM2008 heights)",
            "sourceUrl": "https://registry.opendata.aws/copernicus-dem/",
            "license": DEM_LICENSE,
            "period": "2021 release",
            "resolution": "~30 m original; ~100 m display",
            "method": "Mosaicked Copernicus N11 E075 and N11 E076 COGs; bilinear warp to EPSG:3857 ~100 m display grid; fixed non-negative elevation bins; district mask; exact RGBA PNG",
            "limitations": f"{coverage}; DSM includes vegetation/buildings; negative source values are transparent, not placed in the lowest bin.",
            "inputCrs": "EPSG:4326",
            "displayCrs": "EPSG:3857",
            "stats": common_stats(elev, valid_e),
        },
        {
            "id": "slope",
            "title": "Slope (degrees)",
            "image": "thematic-slope.png",
            "bounds": bounds,
            "legend": [
                {"label": l, "color": c} for l, c in zip(slope_labels, slope_colors)
            ],
            "source": "Derived from Copernicus DEM GLO-30 Public",
            "sourceUrl": "https://registry.opendata.aws/copernicus-dem/",
            "license": DEM_LICENSE,
            "period": "2021 release",
            "resolution": "~30 m original DEM; 90 m metric analysis; ~100 m display",
            "method": "DEM bilinear warp to EPSG:32643 at 90 m; finite-difference slope in metres; categorical result nearest-warped to EPSG:3857 ~100 m display grid; district mask; exact RGBA PNG",
            "limitations": f"{coverage}; derived from DSM, not bare-earth DTM; no hydrological conditioning.",
            "inputCrs": "EPSG:4326",
            "displayCrs": "EPSG:3857",
            "analysisCrs": "EPSG:32643",
            "analysisResolution": "90 m",
            "stats": common_stats(slope_display, slope_valid),
        },
        {
            "id": "landcover",
            "title": "Land cover",
            "image": "thematic-landcover.png",
            "bounds": bounds,
            "legend": [{"label": l, "color": c} for l, c in zip(wc_labels, wc_colors)],
            "source": "ESA WorldCover 10 m 2021 v200",
            "sourceUrl": "https://esa-worldcover.org/en/data-access",
            "license": WC_LICENSE,
            "period": "2021",
            "resolution": "10 m original; ~100 m display",
            "method": "Nearest warp from WorldCover categorical COG to EPSG:3857 ~100 m display grid; district mask; noData transparent; class 95 explicitly mapped to Mangroves; exact RGBA PNG",
            "limitations": f"{coverage}; only classes present in the masked raster are shown; product thematic accuracy varies by class and region.",
            "inputCrs": "EPSG:4326",
            "displayCrs": "EPSG:3857",
            "classCodes": {str(c): class_info[c][0] for c in present},
            "stats": {
                "presentClasses": present,
                "validPixels": int(wc_valid.sum()),
                "totalPixels": int(wc.size),
                "validFraction": float(wc_valid.mean()),
            },
        },
    ]
    json.dump(
        {
            "layers": layers,
            "generated": RETRIEVED,
            "displayGrid": {
                "crs": "EPSG:3857",
                "pixelSizeMetres": 100,
                "width": dw,
                "height": dh,
                "bounds3857": list(map(float, dbounds)),
            },
            "coverage": coverage,
        },
        open(os.path.join(OUT, "thematic.json"), "w"),
        indent=2,
    )
    # Validation: dimensions are exact and visible colors are members of the legends.
    for fn, cols in [
        ("thematic-elevation.png", elev_colors),
        ("thematic-slope.png", slope_colors),
        ("thematic-landcover.png", wc_colors),
    ]:
        im = np.asarray(Image.open(os.path.join(OUT, fn)).convert("RGBA"))
        assert im.shape == (dh, dw, 4)
        allowed = {tuple(int(c[i : i + 2], 16) for i in (1, 3, 5)) for c in cols}
        observed = {tuple(x) for x in im[:, :, :3][im[:, :, 3] > 0]}
        assert observed <= allowed, (fn, observed - allowed)
        print(
            fn,
            im.shape,
            "visible colors",
            len(observed),
            "transparent",
            int((im[:, :, 3] == 0).sum()),
        )
    print("district bbox", bounds, "display", dw, dh, "classes", present)


if __name__ == "__main__":
    main()
