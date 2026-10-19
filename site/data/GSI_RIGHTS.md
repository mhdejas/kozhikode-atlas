# GSI landslide layer: attribution and unresolved rights

**Web-display and redistribution rights for this GSI district derivative remain unresolved.** Attribution and this caveat do not grant permission. Public availability is not an open reuse licence. This is a non-official atlas, not a GSI or KSDMA product or warning service; neither organisation's endorsement is claimed.

## Source attribution

Geological Survey of India (GSI), *Landslide Susceptibility Zones of Districts of Kerala*, 2022, supplied publicly through the Kerala State Disaster Management Authority (KSDMA). GSI is the source organisation; KSDMA hosts the district download and statewide map. GSI's policy states that copyright in its products remains with GSI.

- [KSDMA hazard-map catalogue](https://sdma.kerala.gov.in/hazard-maps/), which labels the district shapefiles “GSI, 2022”.
- [Public Kozhikode district source ZIP](https://sdma.kerala.gov.in/wp-content/uploads/2025/08/Kozhikode.zip).
- [KSDMA statewide GSI 2022 map PDF](https://sdma.kerala.gov.in/wp-content/uploads/2025/06/Landslide_Susceptibility_Zones_Districts_FINAL.pdf).
- [GSI Data Sharing and Accessibility Policy, 2019](https://geodataindia.gov.in/assets/Document_Pdf/4.%20Data%20Dissemination%20policy%202019.pdf): section 3 on ownership/copyright; section 7.6 on NLSM 1:50,000 products; the digital-product terms and Annexure IV on transfer/transmission and acknowledgements.

The provenance identifies an April 2022 GSI/Bhukosh source snapshot and KSDMA derivative processing on 12–15 August 2025. Those packaging/processing dates are not a new field survey. The recorded source ZIP SHA-256 is `7afa02ce8897fe59a6ee1d3465bda625acac69846da777592f3212be9946e312`. The original ZIP is linked, not bundled.

## Files used by the app

- `landslide-susceptibility.png`: the atlas's categorical RGBA display raster.
- `inspector-landslide.png`: the encoded class-query raster, not a natural-colour map.
- `landslide-provenance.json`: source URLs, dates, acquisition checksum, grid, class encoding, processing, sample checks and limitations.
- `landslide-research.json`: the public-source evidence record, including unresolved rights and validation gaps. It is not permission or legal advice.
- `thematic.json`: the active landslide catalogue entry and legend.
- `inspector.json`: the active query grid and class dataset entry.

The PNGs retain the source classes. Provenance, research and catalogue entries carry the unresolved-rights notices. Upstream processing tool names and dates are retained; machine-specific workstation paths are omitted.

## Atlas processing and interpretation

The workflow repaired polygons in their native UTM zone 43N coordinate system, clipped them to the atlas district boundary and rasterised pixel centres onto an approximately 100 m Web Mercator display/query grid. It retained Low, Moderate and High classes and represented unmapped district cells separately. These are processing/display adaptations, not a new susceptibility model.

The GSI NLSM programme scale is 1:50,000. No finer accuracy is inferred from screen pixels. The supplied district derivative does not establish original raster cell size, local positional accuracy or an independent district validation score.

The classes are relative susceptibility zones, not probabilities, forecasts, live warnings, site assessments or safe-land designations. Low does not mean safe. Grey/unmapped is unknown, not safe. No current rainfall, soil saturation or field validation is added; runout can affect land beyond mapped zones. Source and atlas district boundaries differ.

## What the rights caveat means

The KSDMA page provides public downloads but does not establish an explicit open reuse grant for this district derivative. GSI's public policy retains copyright and contains transfer/transmission restrictions. The precise downstream permission applicable to the KSDMA-hosted derivative has not been resolved.

Including the files in an atlas or repository, hosting the app, giving attribution or obtaining a repository owner's approval does not establish rights-holder permission. This notice is not a licence. The project MIT licence and the separate 2018 inventory's CC BY 4.0 licence do not cover this GSI susceptibility material. No written permission or open reuse grant is claimed.

The susceptibility theme and click inspector use these files directly. The app and source panels repeat the rights caveat. GSI map exports remain blocked; that restriction does not resolve web-display or repository-redistribution rights.
