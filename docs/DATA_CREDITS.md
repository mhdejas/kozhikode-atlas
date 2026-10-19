# Data credits

The [MIT licence](../LICENSE) covers project code. It does not replace the terms below. Dates, processing and limitations are recorded in the JSON files beside the published assets.

## Reference geography

District boundary: [geoBoundaries gbOpen](https://www.geoboundaries.org/api/current/gbOpen/IND/ADM2/), with source metadata crediting Pathways Data Pvt. Ltd. and lgdirectory.gov.in. The retained inventory records CC BY 4.0 for gbOpen and ODbL 1.0 in the source metadata; retain both notices rather than treating the boundary as MIT. The atlas selects Kozhikode from the pinned ADM2 release.

Places, roads, rivers and coast: © [OpenStreetMap contributors](https://www.openstreetmap.org/copyright), [ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/). The extract is clipped to the atlas boundary and linear features are simplified in UTM zone 43N. The bundled GeoJSON and projected inspector features are derived data; ODbL obligations still apply.

The Kerala opening locator uses the geoBoundaries ADM1 release, recorded as [CC BY 2.5 India](https://creativecommons.org/licenses/by/2.5/in/). It is simplified for display. Its source and unchanged Kozhikode boundary are documented in [`kerala-region-source.json`](../site/data/kerala-region-source.json).

## Terrain, land cover and imagery

Elevation, slope, query rasters and the 3D height grid derive from [Copernicus DEM GLO-30 Public](https://registry.opendata.aws/copernicus-dem/). Attribution required for these adapted products: “produced using Copernicus WorldDEM-30 © DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018 provided under COPERNICUS by the European Union and ESA; all rights reserved”. See the [official licensing and citation guidelines](https://dataspace.copernicus.eu/explore-data/data-collections/copernicus-contributing-missions/collections-description/COP-DEM). Its public-use licence remains applicable; the derived slope and display grids are atlas modifications, not new ground measurements.

Land cover: ESA WorldCover 2021 v200, [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). The atlas uses nearest-neighbour display resampling, district masking and a custom legend. [Source and data access](https://esa-worldcover.org/en/data-access).

Urban imagery: contains modified Copernicus Sentinel data 2019 and 2025, subject to the [Copernicus Sentinel data terms](https://sentinels.copernicus.eu/documents/247904/690755/Sentinel_Data_Legal_Notice).

Dynamic World is produced by Google in partnership with National Geographic Society and the World Resources Institute, [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Cloud Score+ is also recorded as CC BY 4.0. The atlas creates matched-season composites, masks clouds and shadows, and derives threshold-dependent candidate signals. See [`urban-provenance.json`](../site/data/urban-provenance.json) and the [processing notes](URBAN_COMPARISON.md).

## Historical landslides

C.J. van Westen, University of Twente (2020). *Landslide inventory of the 2018 monsoon rainfall in Kerala, India*, version 2.0. DANS Data Station Physical and Technical Sciences. [DOI: 10.17026/dans-x6c-y7x2](https://doi.org/10.17026/dans-x6c-y7x2). [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).

Atlas changes: spatial selection within the canonical district boundary, reduced attributes, deterministic record IDs and 2D WGS 84 GeoJSON export. Original source locations are retained. The 235 points represent historical initiation locations, not runout footprints or a complete current inventory. Positional accuracy is not stated. The provenance retains source-label/boundary mismatches.

The GSI/KSDMA susceptibility raster, encoded query raster, derivative class statistics and research bundle are included and active in the atlas. This is a non-official display, not a GSI or KSDMA warning product. Web-display and redistribution permission remain unresolved; attribution, this caveat and owner approval do not grant permission. See the [full GSI rights and sources notice](../site/data/GSI_RIGHTS.md). GSI map exports remain blocked. The 2018 CC-licensed source may itself mention GSI as a historical mapping-source flag; that does not extend its CC BY licence to the separate 2022 susceptibility layer.

## Elections and portraits

Indicative constituency borders: [DataMeet Community Maps](https://projects.datameet.org/maps/assembly-constituencies/), ECI-derived, [CC BY 2.5 India](https://creativecommons.org/licenses/by/2.5/in/). These are not legal delimitation boundaries.

The structured election compilation comes from [Sushanth's Kerala election archive](https://data-analytics.github.io/Election_Data/kerala.html), whose repository permits source and binary redistribution under the terms retained in [ELECTION_ARCHIVE_LICENSE.txt](../site/data/election-archive-LICENSE.txt). That notice is from the repository root, not a separate data-specific licence. It does not establish ownership of underlying official records. Source links and verification limits remain in [`elections.json`](../site/data/elections.json); do not imply endorsement by the compiler, ECI or CEO Kerala. Current winner verification is not a verification of every secondary candidate row.

Bundled photographs are the 14 locally recorded reusable Wikimedia Commons images. [`portraits.json`](../site/data/portraits.json) retains the individual source page, creator credit, date, CC licence and licence link for each file. Keep those credits with the images. CC BY-SA images retain their ShareAlike terms; the code's MIT licence does not cover them. No rights-retained official profile images are bundled or hotlinked.

## Libraries, fonts and context tiles

- Leaflet 1.9.4 and its distribution images: [BSD-2-Clause notice](../site/vendor/leaflet-LICENSE.txt).
- Three.js and OrbitControls: [MIT notice](../site/vendor/three/LICENSE.txt).
- DM Sans and Libre Caslon Display: [DM Sans OFL](../site/vendor/DM-Sans-OFL.txt) and [Libre Caslon OFL](../site/vendor/Libre-Caslon-OFL.txt).
- Online map context is credited in the map. Tile services have their own usage terms. Tiles are not bundled and are omitted from map exports.

Do not read a public download link as permission. Preserve attribution and source caveats when copying data out of this project.
