# Dahisar land-use verification

AutoSentinel's demo land-use verification is an independent, local OpenStreetMap extract for the Dahisar bounding box. It does **not** read `zoned_violations_enriched.geojson`, detected construction, Microsoft Building Footprints, or scoring output.

## Prepare the demo data

With the project virtual environment active, run:

```powershell
.\venv\Scripts\python.exe notebooks\build_dahisar_landuse.py --output data\dahisar_landuse.geojson
```

The builder queries public OSM/Overpass once and writes reviewable polygon features with `land_type`, `source`, and `priority`. The committed local extract is used during scans, so scans do not rely on a network request.

## Runtime flow

`fetch_bhuvan_lulc.py` loads `data/dahisar_landuse.geojson` through `LocalGeoJSONProvider` and writes the compatibility layer `data/bhuvan_lulc.geojson`. `legal_cross_reference.py` then overlays each construction polygon in UTM zone 43N and returns:

- `bhuvan_land_type`
- `bhuvan_confidence`
- `bhuvan_overlap_percent`
- `bhuvan_source`

The dominant type is the polygon with the largest true intersection area. Confidence is High above 80%, Medium from 50–80%, Low from 20–50%, and Unknown below 20%. No intersection is always `Unknown` with `Low` confidence and never stops a scan.

Forest, Water Body, Wetland, Park, and Agriculture receive legal-risk boosts. Residential, Commercial, and Industrial do not. Protected-area risk remains an independent OSM legal overlay.

## Future ISRO Bhuvan integration

`notebooks/landuse_providers.py` defines `LandUseProvider`. To introduce an official ISRO Bhuvan API/WFS client, implement `FutureBhuvanProvider.load_landuse()` so it returns the same four normalised columns (`land_type`, `source`, `priority`, `geometry`) and select it in `fetch_bhuvan_lulc.py`. No caller or scoring code needs to change.
