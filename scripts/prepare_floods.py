"""Add EARTHSIM-Omega flood evidence to the atlas as native map themes.

Usage:
    python scripts/prepare_floods.py --earthsim /path/to/earthsim-omega

Reads processed EARTHSIM-Omega rasters and result files (read-only) and
updates the atlas in place:

* site/data/floods/*.png      five opaque, legend-exact overlays on a 50 m
                               EPSG:3857 grid with the atlas display bounds;
* site/data/inspector-flood-*.png
                               uint8 value grids on the atlas 100 m query grid,
                               read by the point inspector;
* site/data/thematic.json     flood layer entries (ids starting "flood-");
* site/data/inspector.json    flood inspector datasets;
* site/data/floods/*.json     rain-trigger replay, outlook snapshot and
                               provenance with SHA-256 of every input;
* site/data/floods/figures/   the project's phone figures as JPEG.

Running it again replaces earlier flood entries. Requires numpy, rasterio,
scipy and Pillow. Paths written to the outputs are relative to the
EARTHSIM-Omega repository, never absolute.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import rasterio
from PIL import Image
from rasterio.enums import Resampling
from rasterio.features import geometry_mask
from rasterio.transform import from_bounds
from rasterio.warp import reproject, transform_geom
from rasterio.warp import transform as warp_points
from scipy import ndimage

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "site" / "data"
OUT = DATA / "floods"
PROJECT = "https://github.com/mhdejas/earthsim-omega"
NOT_OFFICIAL = "EARTHSIM-Omega research layer, not an official warning or hazard map; follow IMD, CWC and KSDMA."

FIGURES = [
    ("01_catchments_MODELLED.png", "modelled", "River catchments traced from the terrain model"),
    ("02_sar_flood_2018-08-14_OBSERVED.png", "observed", "Flooding seen by Sentinel-1 radar on 14 Aug 2018"),
    ("03_hindcast_aug2019_SIMULATED.png", "simulated", "Simulated flood depths, 1–10 Aug 2019"),
    ("04_calibration_heldout_SIMULATED.png", "simulated", "How the flood model scored on a year it never saw"),
    ("05_rain_trigger_replay_OBSERVED_vs_FORECAST.png", "forecast", "Rain trigger replayed over the 2024–2026 monsoons"),
    ("06_live_outlook_2026-10-23_FORECAST.png", "forecast", "Experimental 3-day outlook issued 23 Oct 2026"),
]

# Class colours (opaque; overlay opacity is applied by the map).
C_FLOOD, C_WATER, C_UNSEEN = "#d1495b", "#5b8fb9", "#b9b9b9"
SUS = [("Top 1 % of district", "#6a1b6f"), ("Top 1–5 %", "#b2307f"), ("Top 5–10 %", "#e46aa7"), ("Top 10–25 %", "#f6b7cf")]
HAND = [("0–0.5 m above stream", "#0b4f8a"), ("0.5–2 m above stream", "#3c8dc5"), ("2–5 m above stream", "#a9d1ea")]
DEPTH = [("0.3–1 m deep", "#c9d8ee"), ("1–2 m deep", "#7fa6d9"), ("2–5 m deep", "#3c62b3"), ("5 m or deeper", "#1b2f6e")]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def rgb(hex_colour: str) -> tuple[int, int, int]:
    h = hex_colour.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


class Grid:
    def __init__(self, bounds3857, width, height, boundary_geom4326):
        self.bounds = bounds3857
        self.width, self.height = width, height
        self.shape = (height, width)
        self.transform = from_bounds(*bounds3857, width, height)
        geom = transform_geom("EPSG:4326", "EPSG:3857", boundary_geom4326)
        self.inside = ~geometry_mask([geom], out_shape=self.shape, transform=self.transform)

    def warp(self, path: Path, resampling, array=None):
        with rasterio.open(path) as src:
            data = src.read(1).astype("float32") if array is None else array.astype("float32")
            if array is None and src.nodata is not None and not math.isnan(src.nodata):
                data[data == src.nodata] = np.nan
            dst = np.full(self.shape, np.nan, dtype="float32")
            reproject(data, dst, src_transform=src.transform, src_crs=src.crs, src_nodata=np.nan,
                      dst_transform=self.transform, dst_crs="EPSG:3857", dst_nodata=np.nan,
                      resampling=resampling)
        return dst


def sar_classes(grid: Grid, path: Path) -> np.ndarray:
    """0 outside, 1 seen with no new water, 2 newly flooded, 3 normal water, 4 not covered."""
    with rasterio.open(path) as src:
        cls = src.read(1)
    flooded = np.nan_to_num(grid.warp(path, Resampling.max, (cls == 2))) > 0
    water = np.nan_to_num(grid.warp(path, Resampling.max, (cls == 3))) > 0
    seen = np.nan_to_num(grid.warp(path, Resampling.average, (cls > 0))) >= 0.5
    out = np.where(seen, 1, 4).astype(np.uint8)
    out[water] = 3
    out[flooded] = 2
    out[~grid.inside] = 0
    return out


def sus_rank(grid: Grid, path: Path) -> np.ndarray:
    """1 = top 1 % of district cells ... 100 = lowest; 0 = no data."""
    score = grid.warp(path, Resampling.average)
    valid = grid.inside & np.isfinite(score)
    vals = score[valid]
    order = vals.argsort(kind="stable").argsort(kind="stable")
    top_share = 100.0 * (len(vals) - order) / len(vals)  # highest score -> ~0
    out = np.zeros(grid.shape, np.uint8)
    out[valid] = np.clip(np.ceil(top_share), 1, 100).astype(np.uint8)
    return out


def coded(grid: Grid, path: Path, resampling, step: float) -> tuple[np.ndarray, np.ndarray]:
    """uint8 code 1 + round(value / step), capped at 255; 0 = no data. Also returns values."""
    v = grid.warp(path, resampling)
    valid = grid.inside & np.isfinite(v)
    out = np.zeros(grid.shape, np.uint8)
    out[valid] = np.clip(np.round(np.maximum(v[valid], 0) / step) + 1, 1, 255).astype(np.uint8)
    return out, np.where(valid, v, np.nan)


def save_overlay(classes: np.ndarray, palette: dict[int, str], name: str) -> dict:
    rgba = np.zeros(classes.shape + (4,), np.uint8)
    for code, colour in palette.items():
        sel = classes == code
        rgba[sel, :3] = rgb(colour)
        rgba[sel, 3] = 255
    path = OUT / name
    Image.fromarray(rgba, "RGBA").save(path, optimize=True)
    counts = {colour: int((classes == code).sum()) for code, colour in palette.items()}
    return {"file": f"floods/{name}", "validPixels": int((rgba[..., 3] > 0).sum()), "pixelsByColour": counts,
            "bytes": path.stat().st_size, "sha256": sha256(path)}


def save_value_grid(values: np.ndarray, name: str) -> dict:
    arr = np.dstack([values, np.zeros_like(values), np.full_like(values, 255)])
    path = DATA / name
    Image.fromarray(arr, "RGB").save(path, optimize=True)
    return {"file": name, "bytes": path.stat().st_size, "sha256": sha256(path)}


def nearest_place(lat, lon, places):
    best, best_d = None, 1e18
    for p in places:
        dlat, dlon = math.radians(p["lat"] - lat), math.radians(p["lon"] - lon)
        a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat)) * math.cos(math.radians(p["lat"])) * math.sin(dlon / 2) ** 2
        d = 2 * 6371.0 * math.asin(math.sqrt(a))
        if d < best_d:
            best, best_d = p["name"], d
    return best, best_d


def largest_patches(path: Path, places, n_max=6):
    with rasterio.open(path) as src:
        cls, crs, tr = src.read(1), src.crs, src.transform
        px_km2 = abs(src.res[0] * src.res[1]) / 1e6
    lab, n = ndimage.label(cls == 2, structure=np.ones((3, 3), int))
    sizes = ndimage.sum(np.ones_like(lab), lab, index=np.arange(1, n + 1)) if n else np.array([])
    patches = []
    for idx in np.argsort(sizes)[::-1][:n_max]:
        rows, cols = np.nonzero(lab == idx + 1)
        x, y = rasterio.transform.xy(tr, rows.mean(), cols.mean())
        lon, lat = warp_points(crs, "EPSG:4326", [x], [y])
        name, dist = nearest_place(lat[0], lon[0], places)
        patches.append({"area_km2": round(float(sizes[idx]) * px_km2, 3), "lat": round(lat[0], 5), "lon": round(lon[0], 5),
                        "near": name, "near_km": round(dist, 1)})
    return {"flooded_km2": round(float((cls == 2).sum()) * px_km2, 2), "patch_count": int(n), "largest_patches": patches}



def rain_trigger_held_out(es):
    """Pooled leave-one-monsoon-out score for the 1-day-ahead trigger (EARTHSIM-Omega results)."""
    v = json.loads((es / "experiments" / "results" / "rain_trigger_verification.json").read_text())
    d1 = v["trigger_tuning_loyo"]["by_lead"]["day1"]
    pooled = d1["pooled_held_out"]
    return {"method": "trigger chosen on two monsoons, scored on the held-out third (pooled over 2024, 2025, 2026)",
            "triggers_chosen_mm": [f["chosen_T_mm"] for f in d1["folds"]],
            "deployed_trigger_mm": d1["deploy_T_mm_all_years"],
            "heavy_days": pooled["hits"] + pooled["misses"], "caught": pooled["hits"],
            "false_alarms": pooled["false_alarms"], "false_alarm_ratio": round(pooled["far_false_alarm_ratio"], 2),
            "csi": round(pooled["csi"], 2),
            "source": "earthsim-omega/experiments/results/rain_trigger_verification.json"}

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--earthsim", required=True, type=Path, help="EARTHSIM-Omega checkout with processed data")
    es = ap.parse_args().earthsim.resolve()
    proc, res_dir = es / "data" / "processed", es / "experiments" / "results"
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "figures").mkdir(exist_ok=True)
    inputs = {
        "susceptibility": proc / "flood" / "flood_susceptibility_score.tif",
        "sar_2018_08_14": proc / "flood" / "s1_flood_observed_2018-08-14.tif",
        "sar_2019_08_10": proc / "flood" / "s1_flood_observed_2019-08-10.tif",
        "hand": proc / "terrain" / "hand.tif",
        "hindcast_depth_max": proc / "hydraulics" / "base_depth_max.tif",
        "calibration_test": res_dir / "calibration_test.json",
        "rain_trigger_verification": res_dir / "rain_trigger_verification.json",
        "forecast_alert": res_dir / "forecast_alert_20261023T0331_IST.json",
    }
    for key, p in inputs.items():
        if not p.is_file():
            raise SystemExit(f"missing EARTHSIM-Omega input for {key}: {p.relative_to(es)}")
    for stale in ("lookup-values.png", "lookup-observed.png", "places.json", "district.geojson"):
        (OUT / stale).unlink(missing_ok=True)

    thematic = load_json(DATA / "thematic.json")
    inspector = load_json(DATA / "inspector.json")
    atlas = load_json(DATA / "atlas.geojson")
    boundary = next(f for f in atlas["features"] if f["properties"].get("kind") == "boundary")["geometry"]
    places = [{"name": f["properties"]["name"], "lat": f["geometry"]["coordinates"][1], "lon": f["geometry"]["coordinates"][0]}
              for f in atlas["features"] if f["properties"].get("kind") == "settlement" and f["properties"].get("name")]
    base = thematic["displayGrid"]
    bounds_ll = next(l["bounds"] for l in thematic["layers"] if l["id"] == "elevation")
    disp = Grid(base["bounds3857"], base["width"] * 2, base["height"] * 2, boundary)
    query = Grid(inspector["grid"]["bounds3857"], inspector["grid"]["width"], inspector["grid"]["height"], boundary)
    disp_grid_meta = {"crs": "EPSG:3857", "width": disp.width, "height": disp.height, "bounds3857": list(disp.bounds),
                      "transform": list(disp.transform)[:6], "pixelSizeMetres": 50,
                      "note": "Atlas display bounds at twice the base resolution."}

    files, layers, datasets = {}, [], {}
    common = {"bounds": bounds_ll, "inputCrs": "EPSG:32643", "displayCrs": "EPSG:3857", "displayGrid": disp_grid_meta,
              "provenanceFile": "floods/provenance.json", "project": PROJECT, "official": False}
    s1_attr = "Contains modified Copernicus Sentinel data 2018–2019, processed by EARTHSIM-Omega from Microsoft Planetary Computer Sentinel-1 RTC."
    dem_attr = "Produced using Copernicus WorldDEM-30 © DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018 provided under COPERNICUS by the European Union and ESA; all rights reserved."

    # Observed radar floods ------------------------------------------------
    sar_summary = {}
    for key, lid, date, label, cover in (
        ("sar_2018_08_14", "flood-2018", "2018-08-14", "14 Aug 2018", "almost the whole district (0.03 % radar gaps)"),
        ("sar_2019_08_10", "flood-2019", "2019-08-10", "10 Aug 2019", "eastern 14 % of district"),
    ):
        cls = sar_classes(disp, inputs[key])
        palette = {2: C_FLOOD, 3: C_WATER, 4: C_UNSEEN}
        legend = [{"label": "Newly flooded open water", "color": C_FLOOD}, {"label": "Normal river, lake or backwater", "color": C_WATER}]
        if (cls == 4).any():
            legend.append({"label": "Not seen by this radar pass", "color": C_UNSEEN})
        else:
            palette.pop(4)
        info = save_overlay(cls, palette, f"{lid}.png")
        files[lid] = info
        sar_summary[lid] = {"date": date, "coverage": cover, **largest_patches(inputs[key], places)}
        layers.append({**common, "id": lid, "title": f"Flood seen by radar · {label}", "image": info["file"], "legend": legend,
                       "evidence": "observed", "source": f"Sentinel-1 RTC radar, {label} pass (EARTHSIM-Omega flood detection)",
                       "sourceUrl": "https://planetarycomputer.microsoft.com/dataset/sentinel-1-rtc",
                       "license": "Copernicus Sentinel data terms (free, full and open)", "period": label,
                       "resolution": "30 m analysis; 50 m display (a cell shows flooding if any 30 m pixel inside it did)",
                       "method": "VV backscatter drop of at least 3 dB against same-orbit dry-season references and post-event backscatter below −15 dB; permanent water from the dry-season references.",
                       "limitations": "Observed open water at one moment only. Radar misses water under trees, between buildings and at the true peak; areas without colour were not seen to flood, which does not mean they stayed dry or are safe." + (" The 14 Aug 2018 pass came before the 14–16 Aug rain peak, so the extent is a lower bound." if lid == "flood-2018" else " This pass covers only the eastern part of the district."),
                       "attribution": s1_attr, "stats": {"validPixels": info["validPixels"], "flooded_km2_native": sar_summary[lid]["flooded_km2"]}})
        q = sar_classes(query, inputs[key])
        datasets[lid] = {"image": save_value_grid(q, f"inspector-{lid}.png")["file"], "encoding": "uint8", "scale": 1, "offset": 0, "nodata": 0,
                         "units": "radar class", "classCodes": {"1": "No new open water seen", "2": "Newly flooded open water seen", "3": "Normal water (river, lake, backwater)", "4": "Not covered by this radar pass"},
                         "evidence": "observed", "source": "Sentinel-1 RTC via EARTHSIM-Omega", "sourceUrl": PROJECT, "period": label, "date": label,
                         "resolution": "30 m analysis; ~100 m query cell (flooded if any 30 m pixel inside was)"}

    # Modelled: low land near streams (HAND) ---------------------------------
    _, hand_v = coded(disp, inputs["hand"], Resampling.average, 0.25)
    hc = np.zeros(disp.shape, np.uint8)
    ok = np.isfinite(hand_v)
    hc[ok & (hand_v <= 0.5)] = 1
    hc[ok & (hand_v > 0.5) & (hand_v <= 2)] = 2
    hc[ok & (hand_v > 2) & (hand_v <= 5)] = 3
    info = save_overlay(hc, {i + 1: c for i, (_, c) in enumerate(HAND)}, "flood-low-land.png")
    files["flood-low-land"] = info
    layers.append({**common, "id": "flood-low-land", "title": "Low land near streams", "image": info["file"],
                   "legend": [{"label": l, "color": c} for l, c in HAND], "evidence": "modelled",
                   "source": "Height above nearest drainage (HAND) from Copernicus DEM GLO-30 (EARTHSIM-Omega)",
                   "sourceUrl": "https://registry.opendata.aws/copernicus-dem/", "license": "Copernicus DEM free public licence", "period": "2021 DEM release",
                   "resolution": "30 m analysis; 50 m display (cell average)",
                   "method": "Priority-Flood depression filling, D8 flow directions, streams where the upstream area reaches 1 km², then height of each cell above the stream it drains to.",
                   "limitations": "A surface model that includes trees and buildings. Low height above a stream means water could reach it in a flood; it is not a flood record. Land higher than 5 m is left clear, which does not mean safe.",
                   "attribution": dem_attr, "stats": {"validPixels": info["validPixels"]}})
    hq, _ = coded(query, inputs["hand"], Resampling.average, 0.25)
    datasets["flood-low-land"] = {"image": save_value_grid(hq, "inspector-flood-low-land.png")["file"], "encoding": "uint8", "scale": 0.25, "offset": -0.25,
                                  "nodata": 0, "units": "m above nearest stream (255 = 63.5 m or more)", "evidence": "modelled",
                                  "source": "HAND from Copernicus DEM GLO-30 via EARTHSIM-Omega", "sourceUrl": PROJECT, "period": "2021 DEM release",
                                  "date": "2021 DEM release", "resolution": "30 m analysis; ~100 m query cell average"}

    # Modelled: susceptibility rank -----------------------------------------
    rank = sus_rank(disp, inputs["susceptibility"])
    sc = np.zeros(disp.shape, np.uint8)
    sc[(rank >= 1) & (rank <= 1)] = 1
    sc[(rank > 1) & (rank <= 5)] = 2
    sc[(rank > 5) & (rank <= 10)] = 3
    sc[(rank > 10) & (rank <= 25)] = 4
    info = save_overlay(sc, {i + 1: c for i, (_, c) in enumerate(SUS)}, "flood-susceptibility.png")
    files["flood-susceptibility"] = info
    layers.append({**common, "id": "flood-susceptibility", "title": "Flood susceptibility rank", "image": info["file"],
                   "legend": [{"label": l, "color": c} for l, c in SUS], "evidence": "modelled",
                   "source": "EARTHSIM-Omega logistic flood-susceptibility score", "sourceUrl": PROJECT,
                   "license": "Derived from Copernicus DEM and Sentinel data; see provenance", "period": "Fit on 14 Aug 2018 radar flooding",
                   "resolution": "30 m analysis; 50 m display, ranked within the district",
                   "method": "Logistic model on terrain predictors fit to 2018 radar flooding with 5 km spatial-block cross-validation; cells ranked by score within the district.",
                   "limitations": "A relative rank, not a probability. On the held-out 2019 test it did not beat the simple ‘0.5 m above a stream’ rule. The lowest 75 % of cells are left clear, which does not mean safe.",
                   "attribution": dem_attr, "stats": {"validPixels": info["validPixels"]}})
    datasets["flood-susceptibility"] = {"image": save_value_grid(sus_rank(query, inputs["susceptibility"]), "inspector-flood-susceptibility.png")["file"],
                                        "encoding": "uint8", "scale": 1, "offset": 0, "nodata": 0, "units": "rank, 1 = top 1 % of district cells",
                                        "evidence": "modelled", "source": "EARTHSIM-Omega susceptibility score", "sourceUrl": PROJECT,
                                        "period": "Fit on 2018 radar flooding", "date": "2018 fit", "resolution": "~100 m query cell, ranked within district"}

    # Simulated: 2019 hindcast peak depth -----------------------------------
    _, dv = coded(disp, inputs["hindcast_depth_max"], Resampling.nearest, 0.1)
    dc = np.zeros(disp.shape, np.uint8)
    ok = np.isfinite(dv)
    dc[ok & (dv >= 0.3) & (dv < 1)] = 1
    dc[ok & (dv >= 1) & (dv < 2)] = 2
    dc[ok & (dv >= 2) & (dv < 5)] = 3
    dc[ok & (dv >= 5)] = 4
    info = save_overlay(dc, {i + 1: c for i, (_, c) in enumerate(DEPTH)}, "flood-hindcast-2019.png")
    files["flood-hindcast-2019"] = info
    layers.append({**common, "id": "flood-hindcast-2019", "title": "Simulated flood · 1–10 Aug 2019", "image": info["file"],
                   "legend": [{"label": l, "color": c} for l, c in DEPTH], "evidence": "simulated",
                   "source": "EARTHSIM-Omega rain-on-grid flood model driven by ERA5 rain", "sourceUrl": PROJECT,
                   "license": "ERA5: Copernicus Climate Change Service licence; model output from EARTHSIM-Omega", "period": "1–10 Aug 2019 (410 mm district-mean rain)",
                   "resolution": "240 m model cells; 50 m display (nearest)",
                   "method": "Local-inertial 2-D shallow-water solver, runoff coefficient 0.7, default settings; peak depth over the run.",
                   "limitations": "What the model produced, not what happened. Uniform rain, no infiltration, channel shape, tides or dams; uncalibrated run. Depths under 0.3 m are left clear.",
                   "attribution": "Contains modified Copernicus Climate Change Service information (ERA5) and Copernicus DEM data.", "stats": {"validPixels": info["validPixels"]}})
    dq, _ = coded(query, inputs["hindcast_depth_max"], Resampling.nearest, 0.1)
    datasets["flood-hindcast-2019"] = {"image": save_value_grid(dq, "inspector-flood-hindcast-2019.png")["file"], "encoding": "uint8", "scale": 0.1, "offset": -0.1,
                                       "nodata": 0, "units": "m simulated peak depth (255 = 25.4 m or more)", "evidence": "simulated",
                                       "source": "EARTHSIM-Omega hindcast, ERA5 rain", "sourceUrl": PROJECT, "period": "1–10 Aug 2019", "date": "Aug 2019 hindcast",
                                       "resolution": "240 m model cell"}

    # Merge into the atlas catalogues (idempotent) ---------------------------
    thematic["layers"] = [l for l in thematic["layers"] if not l["id"].startswith("flood-")] + layers
    (DATA / "thematic.json").write_text(json.dumps(thematic, indent=2) + "\n", encoding="utf-8")
    inspector["datasets"] = {k: v for k, v in inspector["datasets"].items() if not k.startswith("flood-")} | datasets
    (DATA / "inspector.json").write_text(json.dumps(inspector, indent=2) + "\n", encoding="utf-8")

    # Rain-trigger replay -----------------------------------------------------
    rt = load_json(inputs["rain_trigger_verification"])
    trigger = 50.0
    heavy = []
    for day, e in sorted(rt["event_days"].items()):
        fc1 = e.get("fc_precipitation_previous_day1")
        heavy.append({"date": day, "era5_mm": round(e["era5_mm"], 1), "forecast_1day_mm": None if fc1 is None else round(fc1, 1),
                      "flagged": None if fc1 is None else bool(fc1 >= trigger)})
    daily = [{"date": d, "era5": round(v["era5"], 1), "fc1": None if v.get("precipitation_previous_day1") is None else round(v["precipitation_previous_day1"], 1)}
             for d, v in sorted(rt["daily"].items())]
    (OUT / "rain-replay.json").write_text(json.dumps({
        "truth": rt["truth"], "model": rt["model"], "season": rt["season"], "years": rt["years"], "day_definition": rt["day_definition"],
        "heavy_threshold_mm": 64.5, "trigger_mm": trigger, "heavy_days": heavy,
        "flagged_1day": {"caught": sum(1 for e in heavy if e["flagged"]), "of": len(heavy)}, "daily": daily,
        "sources": rt["sources"]}, separators=(",", ":")), encoding="utf-8")

    # Outlook snapshot --------------------------------------------------------
    alert = load_json(inputs["forecast_alert"])
    scen = []
    for mk, mv in alert["flood_scenarios"]["members"].items():
        pk = mv["peak_of_snapshots"]
        scen.append({"member": mk, "rain_72h_mm": mv["forecast_72h_mm"], "wet_km2": pk["wet_km2"], "buildings": pk["buildings"],
                     "schools": pk["facilities"].get("school", 0), "hospitals": pk["facilities"].get("hospital", 0), "major_road_km": pk["major_road_km"]})
    (OUT / "outlook-2026-10-23.json").write_text(json.dumps({
        "run_id": alert["run_id"], "issued_ist": alert["issued_ist"], "official": alert["official"], "disclaimer": alert["disclaimer"],
        "level_next_72h": alert["overall_level_next_72h"], "level_basis": alert["level_basis"],
        "trigger_mm": alert["rain_outlook"]["trigger_mm"], "antecedent_5day_mm": alert["rain_outlook"]["antecedent_5day_mm"],
        "days": [{k: d[k] for k in ("day_ending_0830_ist", "lead_day", "in_progress", "deterministic_mm", "ensemble_p10_p50_p90_mm",
                                    "prob_heavy", "prob_very_heavy", "rain_level")} for d in alert["rain_outlook"]["days"]],
        "flood_params": alert["flood_scenarios"]["params"], "scenarios": scen}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    # Figures -----------------------------------------------------------------
    figs = []
    for name, label, title in FIGURES:
        src = es / "figures" / "phone" / name
        im = Image.open(src).convert("RGB")
        im.thumbnail((720, 900), Image.LANCZOS)
        dest = OUT / "figures" / (Path(name).stem.lower().replace("_", "-") + ".jpg")
        im.save(dest, "JPEG", quality=86, optimize=True, progressive=True)
        figs.append({"file": f"floods/figures/{dest.name}", "evidence": label, "title": title,
                     "source": f"earthsim-omega/figures/phone/{name}", "sourceSha256": sha256(src)})

    # Provenance --------------------------------------------------------------
    (OUT / "provenance.json").write_text(json.dumps({
        "title": "Kozhikode flood evidence from EARTHSIM-Omega", "project": PROJECT, "official": False, "notice": NOT_OFFICIAL,
        "evidenceLabels": {"observed": "measured by satellite", "modelled": "derived from measurements by a rule or statistical model",
                           "simulated": "physics model output driven by past rain", "forecast": "about rain that had not yet fallen"},
        "displayGrid": disp_grid_meta, "queryGrid": "atlas inspector grid (~100 m), see inspector.json",
        "heldOutCsi_2019_08_10": {"ksdma_25yr_footprint": 0.023, "calibrated_model": 0.019, "calibrated_model_95ci": [0.001, 0.036],
                                  "hand_le_0_5m": 0.015, "default_model": 0.014},
        "rainTrigger_1day_2024_2026": rain_trigger_held_out(es),
        "observedFloods": sar_summary, "files": files, "inspectorDatasets": sorted(datasets), "figures": figs,
        "inputs": {k: {"path": str(p.relative_to(es)), "sha256": sha256(p)} for k, p in inputs.items()},
    }, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({k: {"validPixels": v["validPixels"], "bytes": v["bytes"]} for k, v in files.items()}, indent=1))
    print(json.dumps({k: {"km2": v["flooded_km2"], "patches": v["patch_count"]} for k, v in sar_summary.items()}))


if __name__ == "__main__":
    main()
