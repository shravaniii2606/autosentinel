"""
legal_zone_check.py

Rule-based GIS verification layer.

Upgrades the old add_zoning.py / add_zoning_v2.py behaviour:
  - OLD: fetch ONE landuse layer, pick the FIRST matching category (if/elif chain)
  - NEW: fetch MULTIPLE legal layers, check a zone against ALL of them, and
         accumulate a weighted "legal_risk_score" instead of a single label.

This still uses OSM only (via osmnx) — no external shapefiles required.
The LAYER_CONFIG below is deliberately structured so that a real shapefile
(forest.shp, crz.shp, floodplain.shp, etc.) can later be dropped into
data/legal_layers/ and picked up automatically with zero code changes
elsewhere in the pipeline (see load_layer()).

Usage (same pattern as score_zones.py / add_zoning.py):
    python notebooks/legal_zone_check.py data/scored_zones.geojson data/legal_verified_zones.geojson
"""

import os
import argparse
import geopandas as gpd
import pandas as pd

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LAYER_CACHE_DIR = os.path.join(BASE_DIR, 'data', 'legal_layers')

# ─── Layer configuration ─────────────────────────────────────────────────────
# Each layer = something a zone can be checked against.
# type: 'osm'    -> fetched from OpenStreetMap via osmnx, tags below
#       'buffer' -> generated locally (e.g. railway line buffered by width)
#       'file'   -> loaded from data/legal_layers/<cache_file> if you drop in
#                   a real shapefile/geojson later (CRZ, floodplain, FSI forest, etc.)
#
# weight: contribution to legal_risk_score if a zone intersects this layer
# label:  human-readable violation reason (used in reports)

LAYER_CONFIG = [
    {
        'name': 'forest',
        'type': 'osm',
        'tags': {'natural': ['wood', 'scrub'], 'landuse': ['forest']},
        'cache_file': 'forest.geojson',
        'weight': 40,
        'label': 'FOREST_ENCROACHMENT',
    },
    {
        'name': 'water_wetland',
        'type': 'osm',
        'tags': {'natural': ['water', 'wetland']},
        'cache_file': 'water_wetland.geojson',
        'weight': 35,
        'label': 'WATER_BODY_ENCROACHMENT',
    },
    {
        'name': 'agricultural',
        'type': 'osm',
        'tags': {'landuse': ['farmland', 'farm', 'orchard']},
        'cache_file': 'agricultural.geojson',
        'weight': 15,
        'label': 'AGRICULTURAL_LAND_CONVERSION',
    },
    {
        'name': 'railway_buffer',
        'type': 'osm_buffer',
        'tags': {'railway': ['rail']},
        'cache_file': 'railway_buffer.geojson',
        'buffer_m': 30,
        'weight': 25,
        'label': 'RAILWAY_LAND_ENCROACHMENT',
    },
    # Drop a real shapefile/geojson into data/legal_layers/crz.geojson and
    # uncomment this block — no other code needs to change.
    # {
    #     'name': 'crz',
    #     'type': 'file',
    #     'cache_file': 'crz.geojson',
    #     'weight': 45,
    #     'label': 'CRZ_VIOLATION',
    # },
]


# ─── Layer loading ────────────────────────────────────────────────────────────

def load_layer(layer, bbox):
    """
    Load one legal layer, in priority order:
      1. Local cache / user-provided file in data/legal_layers/<cache_file>
      2. Fetch fresh from OSM (if type is osm / osm_buffer)
    Returns a GeoDataFrame in EPSG:4326, or None if unavailable.
    """
    os.makedirs(LAYER_CACHE_DIR, exist_ok=True)
    cache_path = os.path.join(LAYER_CACHE_DIR, layer['cache_file'])

    if os.path.exists(cache_path):
        try:
            gdf = gpd.read_file(cache_path)
            print(f"  [{layer['name']}] loaded from cache ({len(gdf)} features)")
            return gdf.to_crs('EPSG:4326')
        except Exception as e:
            print(f"  [{layer['name']}] cache read failed ({e}), refetching...")

    if layer['type'] == 'file':
        print(f"  [{layer['name']}] SKIPPED — no file at {cache_path}. "
              f"Drop a shapefile/geojson there to enable this layer.")
        return None

    # OSM-backed layers
    try:
        import osmnx as ox
        west, south, east, north = bbox
        print(f"  [{layer['name']}] fetching from OSM...")
        gdf = ox.features_from_bbox(bbox=(north, south, east, west), tags=layer['tags'])

        if gdf.empty:
            print(f"  [{layer['name']}] no features found in this area")
            return None

        keep_cols = ['geometry'] + [c for c in layer['tags'].keys() if c in gdf.columns]
        gdf = gdf[keep_cols].copy()
        gdf = gdf.to_crs('EPSG:4326')

        if layer['type'] == 'osm_buffer':
            # Buffer in metres: reproject to a metric CRS, buffer, reproject back
            gdf_m = gdf.to_crs('EPSG:32643')  # UTM zone 43N — correct for Maharashtra
            gdf_m['geometry'] = gdf_m.geometry.buffer(layer['buffer_m'])
            gdf = gdf_m.to_crs('EPSG:4326')

        gdf.to_file(cache_path, driver='GeoJSON')
        print(f"  [{layer['name']}] fetched {len(gdf)} features, cached to {cache_path}")
        return gdf

    except Exception as e:
        print(f"  [{layer['name']}] OSM fetch failed ({e}) — layer skipped")
        return None


# ─── Zone vs. layer checking ──────────────────────────────────────────────────

def check_zones_against_layers(gdf_zones, layers):
    """
    For each layer, spatially join ALL zones against it (vectorised — fast,
    no per-zone python loop), and accumulate weighted hits per zone.

    Returns gdf_zones with new columns:
      legal_risk_score   (0-100, capped)
      legal_violations   (comma-separated list of matched layer labels)
      violation_type     (single highest-weight match, for backward
                           compatibility with score_zones.py / reports / API)
    """
    n = len(gdf_zones)
    accumulated_score = pd.Series([0] * n, index=gdf_zones.index, dtype=float)
    hits = [[] for _ in range(n)]  # list of (label, weight) per zone

    for layer, gdf_layer in layers:
        if gdf_layer is None or gdf_layer.empty:
            continue

        joined = gpd.sjoin(
            gdf_zones[['geometry']],
            gdf_layer[['geometry']],
            how='inner',
            predicate='intersects'
        )
        matched_idx = joined.index.unique()

        print(f"  {layer['name']}: {len(matched_idx)} zone(s) intersect")

        for idx in matched_idx:
            accumulated_score.loc[idx] += layer['weight']
            hits[gdf_zones.index.get_loc(idx)].append((layer['label'], layer['weight']))

    gdf_zones = gdf_zones.copy()
    gdf_zones['legal_risk_score'] = accumulated_score.clip(upper=100).round(1)
    gdf_zones['legal_violations'] = [
        ', '.join(f"{label}" for label, _ in h) if h else 'NONE' for h in hits
    ]
    gdf_zones['violation_type'] = [
        max(h, key=lambda x: x[1])[0] if h else 'UNVERIFIED_ZONE' for h in hits
    ]
    return gdf_zones


def combine_scores(gdf_zones):
    """
    Blend the existing area-based risk_score (from score_zones.py) with the
    new legal_risk_score into a single final_risk_score.

    Construction size still drives the base score; sitting on a legal /
    protected layer adds a bonus on top, capped at 100. This keeps a huge
    structure on unverified land properly flagged, while making a
    forest/wetland hit push an otherwise-medium zone up in priority.
    """
    if 'risk_score' not in gdf_zones.columns:
        gdf_zones['risk_score'] = 0.0

    bonus = gdf_zones['legal_risk_score'] * 0.5  # legal hit contributes up to +50
    gdf_zones['final_risk_score'] = (gdf_zones['risk_score'] + bonus).clip(upper=100).round(1)
    return gdf_zones


# ─── Main ─────────────────────────────────────────────────────────────────────

def main(input_geojson, output_geojson):
    print(f"Loading zones from {input_geojson}...")
    gdf_zones = gpd.read_file(input_geojson)
    gdf_zones = gdf_zones.to_crs('EPSG:4326')
    print(f"Loaded {len(gdf_zones)} zones")

    # Derive a bounding box straight from the zones, padded a bit, instead of
    # a hardcoded Vasai-Virar box — makes this reusable for any region.
    minx, miny, maxx, maxy = gdf_zones.total_bounds
    pad = 0.01
    bbox = (minx - pad, miny - pad, maxx + pad, maxy + pad)  # (west, south, east, north)
    print(f"Legal-layer search bbox: {bbox}")

    print("\nLoading legal layers...")
    layers = []
    for layer in LAYER_CONFIG:
        gdf_layer = load_layer(layer, bbox)
        layers.append((layer, gdf_layer))

    active = [l['name'] for l, g in layers if g is not None]
    print(f"\nActive layers this run: {active if active else 'NONE — all layers unavailable'}")

    print("\nChecking zones against legal layers...")
    gdf_zones = check_zones_against_layers(gdf_zones, layers)
    gdf_zones = combine_scores(gdf_zones)

    print("\nLegal violation breakdown:")
    print(gdf_zones['violation_type'].value_counts())

    print("\nTop 5 zones by final_risk_score:")
    cols = [c for c in ['area_sqm', 'risk_score', 'legal_risk_score',
                         'final_risk_score', 'violation_type'] if c in gdf_zones.columns]
    print(gdf_zones.nlargest(5, 'final_risk_score')[cols])

    out_dir = os.path.dirname(output_geojson)
    if out_dir and not os.path.exists(out_dir):
        os.makedirs(out_dir, exist_ok=True)

    gdf_zones.to_file(output_geojson, driver='GeoJSON')
    print(f"\nSaved {output_geojson}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('input_geojson', type=str, nargs='?',
                         default=os.path.join(BASE_DIR, 'data', 'scored_zones.geojson'))
    parser.add_argument('output_geojson', type=str, nargs='?',
                         default=os.path.join(BASE_DIR, 'data', 'legal_verified_zones.geojson'))
    args = parser.parse_args()
    main(args.input_geojson, args.output_geojson)