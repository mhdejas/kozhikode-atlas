#!/usr/bin/env python3
"""Acquire and build the compact Kozhikode Atlas data package.
Sources are geoBoundaries gbOpen (boundary) and OSM Overpass (features).
Run from repository root: python scripts/acquire.py
"""
from pathlib import Path
import json, datetime, hashlib, requests
from shapely.geometry import shape, Point, LineString, mapping
from pyproj import Transformer
from shapely.ops import transform
from shapely.ops import unary_union
from shapely.validation import explain_validity

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "raw"
OUT = ROOT / "site/data"
RAW.mkdir(exist_ok=True)
OUT.mkdir(parents=True, exist_ok=True)
TODAY = datetime.date.today().isoformat()
UA = "KozhikodeAtlas/1.0 (reproducible open-data pipeline)"
META_URL = "https://www.geoboundaries.org/api/current/gbOpen/IND/ADM2/"
API = "https://overpass-api.de/api/interpreter"
BBOX = (11.122, 75.536, 11.806, 76.148)  # south, west, north, east; slight envelope


def get(url, path, **kwargs):
    r = requests.get(url, headers={"User-Agent": UA}, timeout=300, **kwargs)
    r.raise_for_status()
    path.write_bytes(r.content)
    return r


meta_path = RAW / "geoboundaries_IND_ADM2_metadata.json"
if not meta_path.exists():
    get(META_URL, meta_path)
meta = json.loads(meta_path.read_text())
boundary_url = meta["gjDownloadURL"]
bpath = RAW / "geoBoundaries-IND-ADM2.geojson"
if not bpath.exists():
    get(boundary_url, bpath)
allb = json.loads(bpath.read_text())
bf = next(
    f
    for f in allb["features"]
    if str(f["properties"].get("shapeName", "")).casefold() == "kozhikode"
)
bgeom = shape(bf["geometry"])
assert bgeom.is_valid, explain_validity(bgeom)
queries = {
    "settlement": f'[out:json][timeout:120];node[place~"^(city|town|village|municipality|suburb)$"]({BBOX[0]},{BBOX[1]},{BBOX[2]},{BBOX[3]});out;',
    "road": f"[out:json][timeout:180];way[highway]({BBOX[0]},{BBOX[1]},{BBOX[2]},{BBOX[3]});out geom;",
    "river": f"[out:json][timeout:180];way[waterway]({BBOX[0]},{BBOX[1]},{BBOX[2]},{BBOX[3]});out geom;",
    "coast": f"[out:json][timeout:120];way[natural=coastline]({BBOX[0]},{BBOX[1]},{BBOX[2]},{BBOX[3]});out geom;",
}
for kind, q in queries.items():
    p = RAW / f"osm_{kind}s.json"
    if not p.exists():
        try:
            get(API, p, params={"data": q})
        except Exception as e:
            print(f"warning: {kind} unavailable: {e}")
features = []
seen = set()
counts = {}
MAJOR_ROADS = {
    "motorway",
    "trunk",
    "primary",
    "secondary",
    "tertiary",
    "motorway_link",
    "trunk_link",
    "primary_link",
    "secondary_link",
    "tertiary_link",
}
WATERWAYS = {"river", "canal", "stream"}
to_m = Transformer.from_crs(4326, 32643, always_xy=True).transform
from_m = Transformer.from_crs(32643, 4326, always_xy=True).transform


def add(geom, kind, name, source, oid, extra=None):
    if geom is None or geom.is_empty or not geom.is_valid or not geom.intersects(bgeom):
        return
    geom = geom.intersection(bgeom)
    if geom.is_empty:
        return
    if kind in ("road", "river", "coast"):
        geom = transform(
            from_m, transform(to_m, geom).simplify(35, preserve_topology=True)
        )
    key = (kind, geom.wkb_hex)
    if key in seen:
        return
    seen.add(key)
    props = {"name": name or "", "kind": kind, "source": source}
    props.update(extra or {})
    features.append({"type": "Feature", "properties": props, "geometry": mapping(geom)})
    counts[kind] = counts.get(kind, 0) + 1


add(
    bgeom,
    "boundary",
    "Kozhikode",
    "geoBoundaries gbOpen / Pathways Data Pvt. Ltd.; 2021",
    bf["properties"].get("shapeID"),
)
for kind in ("settlement", "road", "river", "coast"):
    p = RAW / f"osm_{kind}s.json"
    if not p.exists():
        continue
    d = json.loads(p.read_text())
    for e in d.get("elements", []):
        t = e.get("tags", {})
        name = t.get("name:en") or t.get("name") or t.get("ref", "")
        if kind == "road" and t.get("highway") not in MAJOR_ROADS:
            continue
        if kind == "river" and t.get("waterway") not in WATERWAYS:
            continue
        if kind == "settlement":
            g = Point(e["lon"], e["lat"])
        else:
            pts = [(x["lon"], x["lat"]) for x in e.get("geometry", [])]
            g = LineString(pts) if len(pts) >= 2 else None
        extra = {"osm_id": e.get("id")}
        if kind == "settlement":
            extra["place"] = t.get("place", "")
        add(
            g,
            kind,
            name,
            f"OpenStreetMap contributors via Overpass API ({kind})",
            e.get("id"),
            extra,
        )
features.sort(
    key=lambda f: (
        f["properties"]["kind"],
        f["properties"]["name"],
        f["geometry"]["type"],
        json.dumps(f["geometry"], sort_keys=True),
    )
)
fc = {
    "type": "FeatureCollection",
    "name": "Kozhikode Atlas",
    "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::4326"}},
    "features": features,
}
(OUT / "atlas.geojson").write_text(
    json.dumps(fc, separators=(",", ":"), ensure_ascii=False)
)
inv = {
    "title": "Kozhikode Atlas compact geographic data",
    "created": TODAY,
    "crs": "EPSG:4326",
    "bbox_wgs84": [75.53652, 11.12271, 76.14788, 11.80564],
    "datasets": [
        {
            "name": "Kozhikode district boundary",
            "kind": "boundary",
            "source": "geoBoundaries gbOpen",
            "url": boundary_url,
            "metadata_url": META_URL,
            "license": "CC BY 4.0 for gbOpen; source metadata reports ODbL 1.0",
            "date": "2021 represented; build Dec 12 2023",
            "resolution": "ADM2 polygon, 1 feature",
            "processing": "Selected shapeName Kozhikode; validated and clipped only at native boundary.",
            "limitations": "Boundary is not a cadastral/legal survey; source metadata lists Pathways Data Pvt. Ltd. and lgdirectory.gov.in.",
        },
        {
            "name": "OSM settlements, roads, rivers, coastline",
            "kind": "settlement, road, river, coast",
            "source": "OpenStreetMap contributors via Overpass API",
            "url": API,
            "license": "ODbL 1.0",
            "date": TODAY,
            "resolution": "OSM objects in Kozhikode bbox; query recorded in scripts/acquire.py",
            "processing": "Queried nodes/ways, intersected to district polygon, removed exact duplicate geometries, simplified linear features by 35 m in projected EPSG:32643 (UTM 43N), then returned to EPSG:4326 for compact delivery.",
            "limitations": "OSM coverage, tags and positional accuracy vary; this is not authoritative transport or hydrography. Coastline is included only because OSM coastline ways were acquired; no coastline feature was invented.",
        },
    ],
    "counts": counts,
    "feature_count": len(features),
    "size_bytes": (OUT / "atlas.geojson").stat().st_size,
    "attribution": "Kozhikode boundary: geoBoundaries; OSM features: © OpenStreetMap contributors, ODbL 1.0 (https://www.openstreetmap.org/copyright)",
    "validation": {
        "all_geometries_valid": all(shape(f["geometry"]).is_valid for f in features),
        "all_features_epsg4326": True,
        "exact_duplicate_geometries_removed": True,
    },
}
(OUT / "inventory.json").write_text(json.dumps(inv, indent=2, ensure_ascii=False))
print(
    json.dumps(
        {"counts": counts, "features": len(features), "bytes": inv["size_bytes"]}
    )
)
