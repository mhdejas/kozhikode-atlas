#!/usr/bin/env python3
"""Annotate the existing GSI derivative with audited research, not a new model.
Run after prepare_landslides.py. Does not change zone geometry or class pixels.
"""
from pathlib import Path
from datetime import datetime, timezone
import json
import xml.etree.ElementTree as ET
import geopandas as gpd
from shapely import make_valid
from shapely.geometry import shape
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "site/data"
SOURCES = {
    "ksdma": "https://sdma.kerala.gov.in/hazard-maps/",
    "policy": "https://geodataindia.gov.in/assets/Document_Pdf/4.%20Data%20Dissemination%20policy%202019.pdf",
    "pib": "https://www.pib.gov.in/PressReleasePage.aspx?PRID=2158420",
    "sop": "https://bhusanket.gsi.gov.in/Landslide_Hazard_pdf/Mesoscale%20Landslide%20Susceptibility%20Mapping%20-%20SOP%20of%20GSI.cleaned.pdf",
    "local": "https://sdma.kerala.gov.in/wp-content/uploads/2020/11/KSDMA-REPORT.pdf",
    "inventory": "https://doi.org/10.17026/dans-x6c-y7x2",
    "paper": "https://essd.copernicus.org/articles/12/2899/2020/",
    "study": "https://www.mdpi.com/2073-445x/14/7/1453",
    "nrsc": "https://www.isro.gov.in/Landslide_Atlas_India.html",
    "catchments": "https://www.frontiersin.org/journals/earth-science/articles/10.3389/feart.2026.1741697/full",
    "thiruvambadi": "https://recovery.preventionweb.net/publication/documents-and-publications/landslide-susceptibility-assessment-and-preparedness",
    "bhuvan": "https://bhuvan-app1.nrsc.gov.in/disaster/disaster.php?id=landslide",
    "imd": "https://www.imdpune.gov.in/cmpg/Griddata/Rainfall_25_NetCDF.html",
    "imerg": "https://gpm.nasa.gov/data/imerg",
    "dem": "https://dataspace.copernicus.eu/explore-data/data-collections/copernicus-contributing-missions/collections-description/COP-DEM",
    "soils": "https://bhoomigeoportal-nbsslup.in/",
}


def main():
    atlas = json.loads((DATA / "atlas.geojson").read_text())
    boundary = make_valid(
        shape(
            next(
                f["geometry"]
                for f in atlas["features"]
                if f["properties"]["kind"] == "boundary"
            )
        )
    )
    district = gpd.GeoSeries([boundary], crs=4326).to_crs(32643).iloc[0]
    zones = gpd.read_file(ROOT / "raw/landslides/kozhikode-gsi-2022-clipped.gpkg")
    assert zones.crs.to_epsg() == 32643 and zones.is_valid.all()
    mapped = unary_union(zones.geometry)
    coverage = {
        "analysisCrs": "EPSG:32643",
        "units": "km²",
        "atlasBoundaryAreaKm2": district.area / 1e6,
        "mappedUnionAreaKm2": mapped.area / 1e6,
        "unmappedAreaKm2": district.difference(mapped).area / 1e6,
        "mappedFraction": mapped.area / district.area,
        "classAreasKm2": {
            r.susceptibility: r.geometry.area / 1e6 for _, r in zones.iterrows()
        },
        "note": "Area within the atlas reference boundary, not official legal district area. Coverage only, not risk/exposure or safe land. Areas measured from vector geometry, not pixel counts.",
    }
    xml = ET.parse(ROOT / "raw/landslides/Kozhikode/Kozhikode_GSI_LS.shp.xml")
    lineage = [
        {
            "tool": process.attrib.get("Name")
            or process.attrib.get("ToolSource", "").split("\\")[-1],
            "date": process.attrib.get("Date"),
            "operation": "Upstream processing step; workstation-specific paths omitted.",
        }
        for process in xml.findall(".//Process")
    ]
    scale = "1:50,000 GSI NLSM programme scale (official policy); supplied district derivative does not declare original raster cell size or positional accuracy. ~100 m atlas query cells are display sampling, not accuracy."
    period = "GSI/Bhukosh April 2022 source snapshot; KSDMA derivative processed 12–15 August 2025 (not a 2025 survey)"
    license_note = "Publicly downloadable via KSDMA; no explicit reuse licence accompanies this district ZIP. GSI policy retains copyright and restricts transmission. Web-display and redistribution rights remain unresolved. Source attribution, this caveat and owner approval do not grant permission. GSI map exports withheld pending written clearance."
    p = json.loads((DATA / "landslide-provenance.json").read_text())
    p.update(
        {
            "sourceScale": scale,
            "sourceScaleEvidence": {
                "url": SOURCES["policy"],
                "section": "7.6 NLSM data on 1:50K scale",
                "corroboratingUrl": SOURCES["pib"],
                "scope": "Programme-level scale. No finer scale established for this derivative.",
            },
            "sourcePeriod": period,
            "sourceLineage": lineage,
            "metricCoverage": coverage,
            "validation": {
                "atlasChecks": "Geometry repair, CRS, no class-overlap pixel centres and 12 source-membership samples. These test data handling, not predictive skill.",
                "independentKozhikodeValidation": "Not established: no district confusion matrix, positional accuracy or class-threshold report found.",
                "historicalInventoryNotIndependent": "2018 inventory includes GSI and NRSC records, predates 2022 baseline and is incomplete. Overlay agreement is not predictive accuracy.",
            },
            "license": license_note,
            "researchFile": "landslide-research.json",
        }
    )
    (DATA / "landslide-provenance.json").write_text(json.dumps(p, indent=2) + "\n")
    q = json.loads((DATA / "inspector.json").read_text())
    q["datasets"]["landslide"].update(
        {
            "resolution": scale,
            "period": period,
            "sourceScale": "1:50,000 NLSM regional programme; see scale evidence in provenance",
            "accuracy": "No district-specific independent accuracy estimate established.",
        }
    )
    (DATA / "inspector.json").write_text(json.dumps(q, indent=2) + "\n")
    t = json.loads((DATA / "thematic.json").read_text())
    layer = next(x for x in t["layers"] if x["id"] == "landslide")
    layer.update(
        {
            "resolution": scale,
            "period": period,
            "license": license_note,
            "metricCoverage": coverage,
            "researchFile": "landslide-research.json",
        }
    )
    (DATA / "thematic.json").write_text(json.dumps(t, indent=2) + "\n")

    def refs(*pairs):
        return [{"label": label, "url": SOURCES[key]} for key, label in pairs]

    sections = [
        {
            "title": "Regional zones, not property precision",
            "paragraphs": [
                "GSI’s official data policy identifies National Landslide Susceptibility Mapping (NLSM) at 1:50,000. The national programme describes High, Moderate and Low as relative likelihood of landslide initiation. These are not annual probabilities, rainfall thresholds, runout zones or safe-land categories.",
                "The supplied Kozhikode shapefile does not declare the original raster cell size, local positional accuracy, minimum mapping unit or district model thresholds. Programme scale and screen pixel size are different things: sharper rendering cannot establish finer source accuracy.",
                "The atlas retains the source classes on its existing approximately 100 m display/query grid. Near a class edge, a clicked cell samples its centre, not the exact clicked location. There is no quantified source error band; a displayed edge is not a surveyed safety boundary.",
            ],
            "sources": refs(
                ("policy", "GSI policy, section 7.6: NLSM at 1:50,000"),
                ("pib", "Official class definitions and regional-planning purpose"),
            ),
        },
        {
            "title": "What the dates actually mean",
            "paragraphs": [
                "The source map is labelled GSI Bhukosh, April 2022. The download’s XML records raster-to-polygon conversion on 12 August 2025, UTM zone 44N to 43N projection and district clipping on 14 August, and class dissolve on 15 August. Those are derivative-processing dates, not new field observations.",
                "Input CRS: WGS 84 / UTM zone 43N (EPSG:32643), horizontal metres. Atlas display/query CRS: Web Mercator (EPSG:3857). The three multipart source features represent classes, not three landslides. Invalid polygons were repaired before clipping; source SHA-256 and repair accounting remain in the provenance record.",
            ],
            "sources": refs(("ksdma", "KSDMA official source ZIP and map links")),
        },
        {
            "title": "Finer local mapping exists as a lead, not a verified replacement",
            "paragraphs": [
                "GSI’s 2021 meso-scale SOP lists 1:10,000 mapping in and around Kattipara, Chamal and Vettiyozhijathottam in Kozhikode, marked “Taken up in FS 2020-21”. A completed public report, downloadable GIS layer and reuse permission for that sector have not been established here. It is not evidence of district-wide 1:10,000 coverage.",
                "The older KSDMA report includes Thiruvambadi local mapping, geotechnical case studies and a separate five-class quantitative zonation. It is not the method or validation report for the GSI 2022 three-class layer. KSDMA now says GSI replaces the older NCESS susceptibility map in its publications.",
                "A 2025 Kozhikode random-forest paper reports 231 reference landslide points, 30 m resampled inputs and ROC-AUC 0.890. AUC is discrimination, not “89% of parcels correct”. Its layers/code are available on request; no spatially independent district-wide validation is established here. It is a research lead, not a verified replacement raster.",
            ],
            "sources": refs(
                ("sop", "GSI meso-scale SOP and Kozhikode sector entry"),
                ("local", "KSDMA local study"),
                ("study", "2025 Kozhikode study and data-availability statement"),
            ),
        },
        {
            "title": "Coverage is not the same as safety",
            "paragraphs": [
                f'Using the atlas reference boundary and vector areas in UTM 43N, approximately {coverage["mappedUnionAreaKm2"]:.0f} km² ({coverage["mappedFraction"]:.1%}) is covered by the supplied GSI classes; approximately {coverage["unmappedAreaKm2"]:.0f} km² is outside those supplied classes. This is data coverage within this boundary, not the percentage of district land at risk or safe.',
                "Grey remains explicitly unmapped. Low does not mean safe. Debris can travel beyond initiation zones, and source/boundary differences contribute to gaps. Neither present rainfall nor soil saturation is included.",
            ],
            "sources": refs(
                ("ksdma", "Official distribution and reference-purpose map caveat")
            ),
        },
        {
            "title": "Historical evidence adds detail, not a hazard forecast",
            "paragraphs": [
                "The added 2018 event layer is the van Westen/Hao and colleagues compiled inventory: 4,728 Kerala initiation points, assembled from NRSC image mapping, GSI field records and manual image interpretation. DANS version 2.0 explicitly licenses the dataset CC BY 4.0. The atlas uses only points covered by its district boundary, preserving source IDs and recording district-label mismatches.",
                "The peer-reviewed paper reports 3,452 of 4,728 records (73%) supported by at least two sources, and notes completeness cannot be quantified against an independently complete inventory. This is a statewide corroboration statement, not Kozhikode positional accuracy or prediction accuracy.",
                "The inventory includes GSI/NRSC records and predates the GSI 2022 snapshot. Comparing it to GSI zones is descriptive, not independent validation. Points are initiation locations, not affected-area polygons or runout footprints. Small, obscured or unreported failures may be missing; no points does not mean no hazard.",
            ],
            "sources": refs(
                ("inventory", "DANS version 2.0, files and CC BY 4.0 licence"),
                ("paper", "Inventory methods, verification and completeness limits"),
                ("nrsc", "ISRO Landslide Atlas: complementary multi-event inventory"),
            ),
        },
        {
            "title": "Inputs that can support a defensible next analysis",
            "paragraphs": [
                "Terrain: Copernicus GLO-30 has approximately 30 m posting and is a surface model (DSM), including canopy/buildings; its nominal vertical reference is EGM2008. The current atlas slope is derived on a coarser 90 m metric grid, not native 30 m slope or bare-earth site terrain. Seek a documented bare-earth DTM and field checks for local slope/drainage decisions; do not route hydrology over an unexamined DSM.",
                "Rainfall: IMD’s 0.25° daily grid is in mm/day and is roughly 25–28 km across here. GPM IMERG is 0.1° (~10 km), with half-hourly and aggregated products; product-specific units must be checked. These support event/antecedent rainfall analysis, not property-scale rainfall. Use quality-controlled local gauges for calibration, and research Final Run IMERG rather than confusing it with a live warning.",
                "Geology and soil: seek GSI 1:50,000 geological layers with explicit permission and actual local NBSS&LUP coverage. A portal offering 1:10,000 products does not prove Kozhikode coverage. Rock strength, weathered-soil thickness, cut slopes, drainage and pore-pressure observations remain field-evidence gaps.",
                "Before any finer predictive layer: use deduplicated event records, documented geolocation uncertainty and independent later-event or field observations; separate training and test spatial blocks; test scale and terrain sensitivity; report precision/recall, calibration, area-normalised capture and uncertainty. Unmapped cells are not absences. No new weights, hotspot inference or machine-learning susceptibility model has been added.",
            ],
            "sources": refs(
                ("dem", "Copernicus DEM product and DSM limitations"),
                ("imd", "IMD daily 0.25° rainfall"),
                ("imerg", "NASA GPM IMERG"),
                ("policy", "GSI geology/data-access policy"),
                ("soils", "NBSS&LUP soil coverage discovery"),
            ),
        },
        {
            "title": "Reuse remains a real gate",
            "paragraphs": [
                "The KSDMA district ZIP has no explicit open reuse licence. GSI’s 2019 policy retains copyright and limits transmission of digital products. The exact permission applying to this KSDMA derivative is unresolved: a public download is not an open licence. The atlas displays these zones for exploration, without claiming official status or web-display and redistribution permission. Attribution and this caveat do not grant permission.",
                "GSI-layer map exports are withheld until written derivative-display and redistribution permission is obtained. Other atlas exports remain available; the historical 2018 CC BY layer is offered separately as attributed GeoJSON. The historical overlay is not included in current map exports, so an export does not silently claim to contain those observations.",
                "This work continues with public online sources only: no further emails, calls, messages, forms or institutional outreach. A future public release would need a downloadable completed layer, exact coverage and date, source scale/resolution, method, independent validation and explicit web-display/redistribution terms before incorporation. Until those public evidence gates are met, this atlas cannot responsibly promise finer hazard precision.",
            ],
            "sources": refs(
                ("policy", "GSI copyright and licensing policy"),
                ("ksdma", "KSDMA public source downloads"),
            ),
        },
    ]
    inventory = json.loads((DATA / "landslide-inventory-provenance.json").read_text())
    counts = inventory["qa_counts"]
    mismatches = inventory["district_mismatches"]
    inside = sum(x["geometry_district_label"] == "Kozhikode" for x in mismatches)
    outside = sum(x["source_district_label"] == "Kozhikode" for x in mismatches)
    sections[4]["paragraphs"].append(
        f"Boundary audit: {counts['public_feature_count']} points lie inside the atlas boundary, while {counts['district_attribute_match_count']} source records are labelled Kozhikode. There are {len(mismatches)} symmetric selection discrepancies: {inside} inside points carry other district labels, and {outside} Kozhikode-labelled points lie outside. Original labels and IDs are recorded in provenance; the atlas does not claim these boundary or coordinate differences are resolved."
    )
    classes = counts["gsi_2022_point_class_counts"]
    sections[4]["paragraphs"].append(
        f"Descriptive overlap only: {classes.get('High',0)} historical points intersect supplied High zones, {classes.get('Moderate',0)} Moderate, {classes.get('Low',0)} Low and {classes.get('unmapped',0)} fall outside the supplied zones. This is not a validation score or a spatial/temporal holdout test; event/reference-source overlap and uncertain mapping dates prevent that claim. It reinforces why Low and unmapped cannot mean safe."
    )
    public_search = json.loads(
        (ROOT / "docs/LANDSLIDE_PUBLIC_SOURCES.json").read_text()
    )
    sections.insert(
        0,
        {
            "title": "Public-source-only result: no verified precision upgrade",
            "paragraphs": [
                "The public sources checked do not establish an additional higher-detail, openly reusable Kozhikode susceptibility layer or local inventory suitable for this atlas. No new susceptibility model or layer has been created. This is a result of the sources checked, not proof that no finer dataset exists.",
                "GSI’s named 1:10,000 Kattipara–Chamal–Vettiyozhijathottam sector remains a programme lead, not a verified completed download. The official 2025 announcement of 160 completed meso-scale sectors is a national total and does not identify this Kozhikode sector.",
                "The downloadable Thiruvambadi local report is listed as a 2019 publication. Its January 2026 PreventionWeb last-checked date is not a new survey. It is a separate five-class study, not the completed GSI sector product; no openly licensed GIS supplement was verified.",
                "A newly checked March 2026 study covers Kuttiyadi and Chaliyar among five Kerala catchments, using Frequency Ratio and Random Forest. It reports a 30 m DEM, 10 m land cover and GSI inventory updated in 2023. These input postings do not establish output accuracy. Its 70:30 split and five-fold tuning do not establish an independent spatial/temporal validation; its data statement promises availability by the authors but no public GIS download was verified. No data request will be sent.",
                "NRSC/ISRO’s 2023 Atlas documents roughly 80,000 landslides from 1998–2022 and links to Bhuvan viewing, not a verified openly licensed Kozhikode bulk asset. Zenodo, Figshare and Mendeley checks did not establish another suitable local asset; a clearly licensed Raigad dataset is outside Kozhikode, and global packages without verified local coverage were not substituted.",
                "Retain the existing separate, attributed CC BY 4.0 layer of 235 recorded 2018 initiation points. Historical observations add evidence, not property-scale predictions. Public access and open-article licensing do not automatically license source data. GSI export safeguards remain unchanged.",
            ],
            "sources": refs(
                ("sop", "GSI named sector: taken up, not completion evidence"),
                (
                    "pib",
                    "160 completed sectors nationally, not named Kozhikode coverage",
                ),
                (
                    "thiruvambadi",
                    "Thiruvambadi report: 2019 publication, later index check",
                ),
                (
                    "catchments",
                    "2026 catchment study: methods, validation and data statement",
                ),
                ("nrsc", "NRSC/ISRO inventory coverage and PDF"),
                ("bhuvan", "Bhuvan public inventory viewer"),
                ("inventory", "Existing openly licensed historical inventory"),
            ),
        },
    )
    research = {
        "title": "Kozhikode landslide evidence and precision limits",
        "checkedUTC": datetime.now(timezone.utc).isoformat(),
        "verdict": "More defensible evidence, not invented precision: retain regional GSI zones, add licensed 2018 observations, and disclose the finer-scale, validation and reuse gaps.",
        "sections": sections,
        "metricCoverage": coverage,
        "inventorySelection": counts,
        "sources": SOURCES,
        "sourceScale": scale,
        "newSusceptibilityModel": False,
        "permanentGsiRedistributionCleared": False,
        "pipeline": "scripts/prepare_landslides.py → scripts/prepare_landslide_inventory.py → scripts/annotate_landslide_research.py",
    }
    research.update(
        {
            "verdict": "Public-source review: no verified higher-detail, openly reusable replacement was found in the sources checked. Retain regional GSI zones and the separate licensed 2018 observations; do not claim greater precision.",
            "publicSourceReview": public_search,
            "outreachPermitted": False,
        }
    )
    (DATA / "landslide-research.json").write_text(
        json.dumps(research, indent=2, ensure_ascii=False) + "\n"
    )
    report = (
        "# Kozhikode landslides: stronger evidence, honest precision\n\n"
        + research["verdict"]
        + "\n\n"
    )
    for section in sections:
        report += (
            "## "
            + section["title"]
            + "\n\n"
            + "\n\n".join(section["paragraphs"])
            + "\n\n"
        )
        report += (
            "\n".join(
                "- [" + x["label"] + "](" + x["url"] + ")"
                for x in section.get("sources", [])
            )
            + "\n\n"
        )
    report += "## Reproduce this update\n\nRun `python3 scripts/prepare_landslides.py`, `python3 scripts/prepare_landslide_inventory.py`, then `python3 scripts/annotate_landslide_research.py`. Run `python3 -m unittest discover -s tests -q`. The GSI source class geometry is not sharpened or reclassified. New inventory points are not incorporated into a prediction model. Source downloads, checksums and full analysis GeoPackages stay in `raw/`, outside public deployment assets.\n"
    (ROOT / "docs/LANDSLIDE_EVIDENCE.md").write_text(report)
    print(
        json.dumps(
            {
                "updatedMetadata": 3,
                "researchSections": len(sections),
                "coverage": coverage,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
