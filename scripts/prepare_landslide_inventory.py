#!/usr/bin/env python3
"""Acquire, QA, and prepare the DANS 2018 Kerala landslide inventory.

The public GeoJSON is a deterministic, district-clipped, 2-D WGS84 point
inventory.  Source fields remain available in the raw analysis GeoPackage;
public provenance is self-contained and does not depend on private paths.
"""
from __future__ import annotations
import argparse, hashlib, json
from datetime import datetime, timezone
from pathlib import Path
import requests
import geopandas as gpd
import pandas as pd
from shapely.geometry import Point

ROOT = Path(__file__).resolve().parents[1]
API = "https://phys-techsciences.datastations.nl/api/datasets/:persistentId/?persistentId=doi:10.17026/dans-x6c-y7x2"
BASE = "https://phys-techsciences.datastations.nl/api/access/datafile/"
FILES = {
    "shp6576": "Kerela landslide.shp",
    "dbf6579": "Kerela landslide.dbf",
    "shx6581": "Kerela landslide.shx",
    "prj6578": "Kerela landslide.prj",
    "cpg6575": "Kerela landslide.cpg",
    "metadata.pdf6650": "metadata.pdf",
    "xml6577": "Kerela landslide.xml",
}
IDS = {
    "shp6576": 6576,
    "dbf6579": 6579,
    "shx6581": 6581,
    "prj6578": 6578,
    "cpg6575": 6575,
    "metadata.pdf6650": 6650,
    "xml6577": 6577,
}
TYPE_CODE_EXPANSIONS = {"DF": "debris flow", "SS": "surficial slide", "RF": "rock fall"}


def sha1(p):
    h = hashlib.sha1()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()


def sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()


def fields(meta):
    out = {}
    for block in (
        meta.get("data", {}).get("latestVersion", {}).get("metadataBlocks", {}).values()
    ):
        for f in block.get("fields", []):
            out[f.get("typeName")] = f.get("value")
    return out


def stable_ids(g):
    """Use source No plus deterministic source-row occurrence for duplicate No values."""
    no = pd.to_numeric(g["No"], errors="raise").astype(int)
    occurrence = no.groupby(no, sort=False).cumcount() + 1
    return (
        [
            f"kerala2018-no-{n:05d}-row-{i:04d}"
            for n, i in zip(no, range(1, len(g) + 1))
        ],
        no,
        occurrence,
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    raw = ROOT / "raw/landslide-inventory"
    raw.mkdir(parents=True, exist_ok=True)
    work = ROOT / "work"
    work.mkdir(parents=True, exist_ok=True)
    site = ROOT / "site/data"
    site.mkdir(parents=True, exist_ok=True)
    retrieved = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    response = requests.get(API, timeout=90)
    response.raise_for_status()
    api_meta = response.json()
    version = api_meta["data"]["latestVersion"]
    if (version.get("versionNumber"), version.get("versionMinorNumber")) != (2, 0):
        raise RuntimeError(
            "Archive version changed; review source and licence before continuing."
        )
    meta = api_meta
    lic = api_meta["data"]["latestVersion"]["license"]["name"]
    if lic != "CC-BY-4.0":
        raise RuntimeError(
            "Expected the verified CC-BY-4.0 licence; review before publishing."
        )
    (raw / "archive-metadata.json").write_text(json.dumps(api_meta, indent=2) + "\n")
    filemeta = {
        f.get("dataFile", {}).get("id"): f.get("dataFile", {})
        for f in api_meta["data"]["latestVersion"]["files"]
    }
    manifest = []
    for key, fn in FILES.items():
        p = raw / fn
        fid = IDS[key]
        expected = filemeta.get(fid, {}).get("checksum", {}).get("value")
        if not expected:
            raise RuntimeError(
                f"Missing source checksum for {fn}; not safe to verify acquisition."
            )
        if (
            a.force
            or not p.exists()
            or (expected and sha1(p).lower() != expected.lower())
        ):
            r = requests.get(BASE + str(fid), timeout=180)
            r.raise_for_status()
            p.write_bytes(r.content)
        got = sha1(p)
        manifest.append(
            {
                "key": key,
                "id": fid,
                "filename": fn,
                "bytes": p.stat().st_size,
                "sha1": got,
                "expected_sha1": expected,
                "verified": (not expected or got.lower() == expected.lower()),
            }
        )
    if not all(x["verified"] for x in manifest):
        raise RuntimeError("SHA-1 verification failed")
    (raw / "manifest.json").write_text(
        json.dumps(
            {
                "source_doi": "10.17026/DANS-X6C-Y7X2",
                "api": API,
                "retrieved_at_utc": retrieved,
                "release_date": api_meta["data"]["latestVersion"].get(
                    "publicationDate"
                ),
                "license": lic,
                "files": manifest,
            },
            indent=2,
        )
        + "\n"
    )

    shp = raw / "Kerela landslide.shp"
    g = gpd.read_file(shp)
    if g.crs is None or g.crs.to_epsg() != 4326:
        raise RuntimeError(
            f"Unexpected or missing source CRS; expected declared EPSG:4326, got {g.crs}"
        )
    source_crs = g.crs.to_string()
    geom_types = g.geometry.geom_type.value_counts(dropna=False).to_dict()
    null_geom = int(g.geometry.isna().sum())
    empty_geom = int(g.geometry.is_empty.sum())
    invalid = int((~g.geometry.is_valid & g.geometry.notna()).sum())
    cols = [str(c) for c in g.columns if c != "geometry"]
    lower = {c.lower(): c for c in cols}

    def pick(names):
        for n in names:
            if n in lower:
                return lower[n]
        for c in cols:
            if any(n in c.lower() for n in names):
                return c
        return None

    type_col = pick(["type", "landslide_type", "ls_type", "class"])
    method_col = pick(["source", "method", "mapping", "inventory"])
    source_cols = [c for c in ["NRSC", "GSI", "New"] if c in g.columns]
    district_col = pick(["district", "dist"])
    dup_geom = int(g.geometry.duplicated().sum())
    dup_rows = int(g.astype(str).duplicated().sum())
    public_ids, source_no, no_occurrence = stable_ids(g)
    g["_record_id"] = public_ids
    g["_source_no"] = source_no
    g["_no_occurrence"] = no_occurrence

    # Canonical project district boundary: atlas.geojson, kind=boundary. Never infer/relabel CRS.
    atlas_path = ROOT / "site/data/atlas.geojson"
    atlas = gpd.read_file(atlas_path)
    if atlas.crs is None or atlas.crs.to_epsg() != 4326:
        raise RuntimeError(f"Unexpected or missing atlas CRS: {atlas.crs}")
    boundary = atlas[
        (atlas["kind"].astype(str).str.casefold() == "boundary")
        & (atlas["name"].astype(str).str.casefold() == "kozhikode")
    ].copy()
    if len(boundary) != 1:
        raise RuntimeError(
            f"Expected exactly one canonical Kozhikode atlas boundary, got {len(boundary)}"
        )
    koz = boundary.iloc[[0]]
    atlas_geom_hash = sha256_bytes(koz.geometry.iloc[0].normalize().wkb)
    prior = gpd.read_file(ROOT / "site/data/kerala-region.geojson")
    prior_koz = prior[
        prior.get("kind", "").astype(str).str.casefold().eq("boundary")
        & prior.get("name", "").astype(str).str.casefold().eq("kozhikode")
    ]
    prior_geom_hash = (
        sha256_bytes(prior_koz.geometry.iloc[0].normalize().wkb)
        if len(prior_koz) == 1
        else None
    )
    prior_geom_identical = bool(
        len(prior_koz) == 1 and koz.geometry.iloc[0].equals(prior_koz.geometry.iloc[0])
    )

    pts = g[g.geometry.geom_type.isin(["Point", "MultiPoint"])].copy()
    if pts.geometry.geom_type.eq("MultiPoint").any():
        pts = pts.explode(index_parts=False)
    pts4326 = pts.to_crs(4326)
    joined = gpd.sjoin(
        pts4326,
        koz[["name", "geometry"]],
        predicate="within",
        how="left",
        lsuffix="source",
        rsuffix="boundary",
    )
    geometry_district = joined["name"].where(joined["name"].notna(), None)
    source_labels = (
        joined[district_col].where(joined[district_col].notna(), None)
        if district_col
        else pd.Series([None] * len(joined), index=joined.index)
    )
    norm = lambda s: (
        str(s).strip().casefold().replace(" ", "")
        if s is not None and not pd.isna(s)
        else None
    )
    # This is a single-district selection: another source district outside
    # Kozhikode is agreement, not a failed multi-district spatial assignment.
    source_is_kozhikode = source_labels.map(norm).eq("kozhikode")
    geometry_is_kozhikode = geometry_district.notna()
    mismatch_mask = source_is_kozhikode ^ geometry_is_kozhikode
    mismatch_rows = []
    for idx, row in joined.loc[mismatch_mask].iterrows():
        mismatch_rows.append(
            {
                "record_id": row["_record_id"],
                "source_no": int(row["_source_no"]),
                "source_district_label": (
                    None
                    if pd.isna(row.get(district_col))
                    else str(row.get(district_col)).strip()
                ),
                "geometry_district_label": (
                    None if pd.isna(row.get("name")) else str(row.get("name")).strip()
                ),
            }
        )
    matched = geometry_district.notna()
    matched_n = int(matched.sum())
    attr_match = (
        int(source_labels.map(norm).eq("kozhikode").sum()) if district_col else None
    )
    attr_unmatched = int(len(pts) - attr_match) if district_col else None
    out = joined.loc[matched].copy()
    out["district"] = "Kozhikode"

    def valcol(row, c):
        return None if not c or pd.isna(row.get(c)) else str(row.get(c)).strip()

    out["type"] = [valcol(r, type_col) for _, r in out.iterrows()]
    out["source_method"] = [
        (
            valcol(r, method_col)
            if method_col
            else ";".join(
                c for c in source_cols if str(r.get(c, "")).strip().upper() == "Y"
            )
            or None
        )
        for _, r in out.iterrows()
    ]
    # Explicitly drop any Z dimension; the dataset asserts no vertical measurement.
    out["geometry"] = out.geometry.map(
        lambda p: (
            Point(float(p.x), float(p.y)) if p is not None and not p.is_empty else p
        )
    )
    out = (
        out[["_record_id", "type", "source_method", "district", "geometry"]]
        .rename(columns={"_record_id": "record_id"})
        .sort_values("record_id")
        .reset_index(drop=True)
    )
    out.to_file(site / "landslide-inventory-2018.geojson", driver="GeoJSON")

    gpkg = raw / "landslide-inventory-2018-analysis.gpkg"
    if gpkg.exists():
        gpkg.unlink()
    g.drop(columns=["_record_id", "_source_no", "_no_occurrence"]).to_file(
        gpkg, layer="kerala_inventory", driver="GPKG"
    )

    comp_path = ROOT / "raw/landslides/kozhikode-gsi-2022-clipped.gpkg"
    comp = {}
    if comp_path.exists():
        c = gpd.read_file(comp_path)
        ccols = [x for x in c.columns if x != "geometry"]
        cc = next(
            (
                x
                for x in ccols
                if any(k in x.lower() for k in ["class", "zone", "suscept", "type"])
            ),
            None,
        )
        comp["gsi_2022_feature_count"] = len(c)
        comp["gsi_2022_fields"] = ccols
        comp["gsi_2022_polygon_class_counts"] = (
            {
                str(k): int(v)
                for k, v in c[cc].fillna("NULL").astype(str).value_counts().items()
            }
            if cc
            else {}
        )
        pts_for_join = out.to_crs(c.crs)
        hits = gpd.sjoin(
            pts_for_join,
            c[[cc, "geometry"]] if cc else c[["geometry"]],
            predicate="within",
            how="left",
        )
        point_class = (
            hits[cc].fillna("unmapped").astype(str)
            if cc
            else pd.Series(["unmapped"] * len(hits), index=hits.index)
        )
        comp["gsi_2022_point_class_counts"] = {
            str(k): int(v) for k, v in point_class.value_counts().items()
        }
        comp["gsi_2022_point_unmapped_count"] = int(point_class.eq("unmapped").sum())
        comp["2018_kozhikode_points"] = len(out)
        comp["2018_points_within_2022_polygons"] = int(point_class.ne("unmapped").sum())
        comp["comparison_note"] = (
            "Descriptive overlap and point class counts only; not accuracy, and not an accuracy assessment. 2018 event inventory predates the 2022 GSI/NRSC product."
        )

    qa = {
        "version": "2.0",
        "schema_version": "2.0",
        "run_at_utc": retrieved,
        "source": {
            "doi": "10.17026/DANS-X6C-Y7X2",
            "title": fields(meta).get("title"),
            "license": lic,
            "release_date": api_meta["data"]["latestVersion"].get("publicationDate"),
            "acquisition_date_utc": retrieved,
            "input_expected_total": 4728,
            "units_time_period": "2018 monsoon rainfall; source Length/Width in m, Area in m2, RASTERVALU in degrees; point coordinates in WGS 84.",
        },
        "metadata_pdf_inspection": {
            "file": "metadata.pdf",
            "attribute_notes": "NRSC, GSI and New are Y/N source flags; Type_of_sl is a landslide type code; POINT_X and POINT_Y are WGS 84 coordinates.",
            "type_code_expansions": TYPE_CODE_EXPANSIONS,
            "positional_accuracy": "Unknown; the metadata PDF explains attributes but does not state positional accuracy.",
        },
        "source_inspection": {
            "feature_count": len(g),
            "crs": source_crs,
            "geometry_types": geom_types,
            "fields": cols,
            "null_geometry_count": null_geom,
            "empty_geometry_count": empty_geom,
            "invalid_geometry_count": invalid,
            "duplicate_geometry_count": dup_geom,
            "duplicate_full_row_count": dup_rows,
            "no_unique_count": int(source_no.nunique()),
            "no_duplicate_count": int(source_no.duplicated().sum()),
            "positional_accuracy": "Unknown; not stated in inspected metadata.",
        },
        "district_boundary": {
            "canonical_source": "site/data/atlas.geojson feature kind=boundary name=Kozhikode",
            "crs": "EPSG:4326",
            "geometry_hash_sha256": atlas_geom_hash,
            "prior_kerala_region_geometry_hash_sha256": prior_geom_hash,
            "prior_geom_identical": prior_geom_identical,
        },
        "district_extraction": {
            "geometry_covered_count": len(pts),
            "geometry_covered_kozhikode_count": matched_n,
            "geometry_unmatched_count": int(len(pts) - matched_n),
            "district_field": district_col,
            "district_field_matched_count": attr_match,
            "district_field_unmatched_count": attr_unmatched,
            "mismatch_count": len(mismatch_rows),
            "mismatch_ids_and_source_labels": mismatch_rows,
            "mismatch_note": "Symmetric source district versus canonical boundary results are retained separately and recorded before public district is overwritten; public output retains geometry-covered Kozhikode points only.",
        },
        "output": {
            "public_feature_count": len(out),
            "crs": "EPSG:4326",
            "fields": ["record_id", "type", "source_method", "district"],
            "geometry": "2-D Point; original point locations transformed to WGS84; no vertical measurement asserted",
            "record_id_rule": "kerala2018-no-{No:05d}-row-{source row:04d}; No is not unique, so source row occurrence is included deterministically.",
        },
        "comparison_2022": comp,
    }
    (work / "landslide-inventory-qa.json").write_text(
        json.dumps(qa, indent=2, default=str) + "\n"
    )
    prov = {
        "version": "2.0",
        "schema_version": "2.0",
        "source_doi": "https://doi.org/10.17026/dans-x6c-y7x2",
        "dataset_title": fields(meta).get("title"),
        "license": "CC-BY-4.0",
        "license_url": "https://creativecommons.org/licenses/by/4.0/",
        "release_date": api_meta["data"]["latestVersion"].get("publicationDate"),
        "acquisition_date_utc": retrieved,
        "crs": "EPSG:4326 (declared source and canonical boundary CRS; no CRS guessed)",
        "feature_count": len(out),
        "units_time_period": qa["source"]["units_time_period"],
        "positional_accuracy": "Unknown; not stated in inspected metadata.",
        "extraction_method": "Read declared WGS84 source points; spatially joined points within the canonical atlas.geojson Kozhikode boundary; public district label then set to Kozhikode; exported deterministic sorted 2-D GeoJSON.",
        "qa_counts": {
            "source_feature_count": len(g),
            "public_feature_count": len(out),
            "invalid_geometry_count": invalid,
            "null_geometry_count": null_geom,
            "geometry_covered_kozhikode_count": matched_n,
            "geometry_unmatched_count": int(len(pts) - matched_n),
            "district_attribute_match_count": attr_match,
            "district_attribute_unmatched_count": attr_unmatched,
            "district_mismatch_count": len(mismatch_rows),
            "gsi_2022_point_class_counts": comp.get("gsi_2022_point_class_counts", {}),
            "gsi_2022_point_unmapped_count": comp.get("gsi_2022_point_unmapped_count"),
        },
        "district_mismatches": mismatch_rows,
        "source_district_labels_in_mismatches": sorted(
            {
                x["source_district_label"]
                for x in mismatch_rows
                if x["source_district_label"] is not None
            }
        ),
        "type_code_expansions": TYPE_CODE_EXPANSIONS,
        "canonical_boundary": qa["district_boundary"],
        "sha_file_manifest": [
            {"filename": x["filename"], "sha1": x["sha1"], "bytes": x["bytes"]}
            for x in manifest
        ],
        "attribution": "C.J. van Westen, University of Twente; DANS Data Station Physical and Technical Sciences; CC BY 4.0.",
    }
    (site / "landslide-inventory-provenance.json").write_text(
        json.dumps(prov, indent=2) + "\n"
    )
    print(
        json.dumps(
            {
                "source_total": len(g),
                "geometry_covered": len(pts),
                "geometry_covered_kozhikode": matched_n,
                "public": len(out),
                "district_mismatches": len(mismatch_rows),
                "invalid": invalid,
                "null": null_geom,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
