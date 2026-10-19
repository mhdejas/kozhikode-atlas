# Urban comparison (2019–2025)

This is an **optional exploratory comparison**, not a validated urban-area estimate. It places matched January–March Sentinel-2 surface-reflectance RGB composites and Dynamic World built-probability signals on an explicit EPSG:3857 display grid. The output distinguishes visual differences from candidate built-up signals; a candidate is not a confirmed new building, a cadastral result, or a ground-validated area measurement.

## Reproduce the run

1. Install the pinned environment:

   ```bash
   python -m venv .venv
   . .venv/bin/activate
   python -m pip install -r requirements.txt
   ```

2. Authenticate Earth Engine using the normal Earth Engine CLI/browser flow for the account and Cloud project authorized by your organization. Do not put credentials, tokens, private URLs, email addresses, or project identifiers in this repository.

3. Initialize/run with your own registered project (the placeholder is intentional):

   ```bash
   earthengine authenticate
   python scripts/urban_gee.py --project YOUR_PROJECT
   ```

   The script filters Sentinel-2 Harmonized, Cloud Score+, and Dynamic World observations to the Kozhikode boundary and 1 January–31 March in each year. It uses Cloud Score+ `cs_cdf >= 0.60`, explicit SCL exclusions, at least three observations per date, per-band RGB medians, mean Dynamic World built probability, and a nine-connected-pixel minimum mapping unit for candidate signals.

4. Verify the generated `site/data/urban-provenance.json` has `status: completed`, then run:

   ```bash
   python -m unittest discover -s tests -v
   ```

   The generated `raw/urban/manifest.json` retains the run metadata and catalogue IDs. The runtime catalogue entry records its own `displayGrid` (CRS, transform, width, height, and bounds); do not assume that it shares the older thematic layers' 100 m grid.

## Outputs and interpretation

- `urban-before.png` and `urban-after.png` are aligned transparent PNG visualizations using the same RGB stretch and one shared 127-colour palette. Indexed encoding keeps each file below the temporary host's 5 MB limit without changing the spatial grid; decoded transparency is checked against both dates. It is a web-display optimization, not additional analytical precision. Original COG reflectance and probability values remain unchanged.
- `urban-candidates.png` documents candidate gain, persistent high built signal, candidate loss, assessed pixels, and insufficient observations with its generated legend.
- Optional `raw/urban/urban-2019.tif` and `urban-2025.tif` are six-band COG exports (RGB, RGB observation count, built probability ×10,000, and Dynamic World count). `urban-signals.tif` is the class raster.
- `urban-provenance.json` records exact collection IDs, date windows, model/version metadata, masking, thresholds, coverage/counts, checksums, and a scalar server/local cross-check.

The candidate rule is a signal threshold (`<= 0.20` in 2019 and `>= 0.60` in 2025) after common validity and connected-pixel filtering. It is not a building detector and has no independent stratified ground-reference accuracy assessment. Seasonal crop cycles, exposed soil, shadows, haze, mixed pixels, source processing differences, model uncertainty, boundary/mask effects, and registration error can all produce apparent differences. The script explicitly reports that no positional RMSE or error-adjusted urban-area estimate was measured. Do not convert candidate pixel counts into a validated urban expansion claim.

## Data and model provenance

The imagery is Copernicus Sentinel-2 Harmonized surface reflectance; cloud scoring uses Google Cloud Score+; built probability uses Dynamic World V1. Product versions, processing baselines, observation IDs, and the exact boundary checksum are written into the generated provenance file. The boundary is the existing Kozhikode geoBoundaries extract retained by this repository. Consult the collection documentation and licenses linked by the generated catalogue entry before redistribution. A new Earth Engine run may change available scenes, model metadata, or outputs; retain the provenance file with every publication.
