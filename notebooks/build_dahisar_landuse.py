#!/usr/bin/env python3
"""Build the demo's independent Dahisar land-use layer from OpenStreetMap.

Run this during demo preparation, commit/review the resulting GeoJSON, and use
``fetch_bhuvan_lulc.py`` at scan time.  Scan-time verification is therefore
offline and never reads a detection or violation dataset.
"""
from __future__ import annotations

import argparse
import os
from typing import Sequence

import geopandas as gpd
import requests
from shapely.geometry import Polygon

from landuse_providers import LAND_USE_PRIORITY, empty_landuse, normalise_land_type

DEFAULT_DAHISAR_BBOX = (72.835, 19.215, 72.895, 19.295)  # west, south, east, north
ENDPOINTS = (
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.openstreetmap.fr/api/interpreter",
    "https://overpass-api.de/api/interpreter",
)


def _query(bbox: Sequence[float]) -> dict:
    west, south, east, north = bbox
    # Only area features are requested.  Lines are intentionally excluded: they
    # cannot support a meaningful construction-area overlap percentage.
    tags = [
        '["landuse"]', '["natural"~"water|wetland|wood|scrub|sand|bare_rock"]',
        '["leisure"~"park|garden|nature_reserve"]', '["water"]',
        '["boundary"="protected_area"]',
    ]
    selections = ";".join(
        f'way{tag}({south},{west},{north},{east});relation{tag}({south},{west},{north},{east})'
        for tag in tags
    )
    query = f'[out:json][timeout:45];({selections};);out tags geom;'
    last_error = None
    for endpoint in ENDPOINTS:
        try:
            response = requests.post(endpoint, data={"data": query}, timeout=60,
                                     headers={"User-Agent": "AutoSentinel-Dahisar-Demo/1.0"})
            response.raise_for_status()
            return response.json()
        except requests.RequestException as exc:
            last_error = exc
            print(f"Overpass request failed at {endpoint}: {exc}")
    raise RuntimeError(f"Could not obtain Dahisar OSM land use: {last_error}")


def _to_layer(payload: dict) -> gpd.GeoDataFrame:
    rows = []
    seen = set()
    for element in payload.get("elements", []):
        key = (element.get("type"), element.get("id"))
        coords = [(point["lon"], point["lat"]) for point in element.get("geometry", [])]
        if key in seen or len(coords) < 4 or coords[0] != coords[-1]:
            continue
        seen.add(key)
        try:
            geometry = Polygon(coords).buffer(0)
        except Exception:
            continue
        if geometry.is_empty or geometry.geom_type not in {"Polygon", "MultiPolygon"}:
            continue
        tags = element.get("tags", {}) or {}
        land_type = normalise_land_type(tags)
        # Protected-area boundaries remain traceable to OSM; the legal overlay
        # continues to apply the separate protected-area risk flag.
        rows.append({
            "land_type": land_type,
            "source": "OpenStreetMap (Overpass, Dahisar extract)",
            "priority": LAND_USE_PRIORITY[land_type],
            "osm_id": element.get("id"),
            "osm_type": element.get("type"),
            "geometry": geometry,
        })
    if not rows:
        return empty_landuse()
    return gpd.GeoDataFrame(rows, geometry="geometry", crs="EPSG:4326")


def main(output: str, bbox: Sequence[float]) -> None:
    print("Fetching independent OSM land-use polygons for Dahisar...")
    layer = _to_layer(_query(bbox))
    if layer.empty:
        raise RuntimeError("OSM returned no usable polygonal land-use features for Dahisar.")
    os.makedirs(os.path.dirname(output) or ".", exist_ok=True)
    layer.to_file(output, driver="GeoJSON")
    print(f"Saved {len(layer)} Dahisar land-use polygons to {output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build a normalised OSM land-use layer for the Dahisar demo area.")
    parser.add_argument("--output", default="data/dahisar_landuse.geojson")
    parser.add_argument("--bbox", nargs=4, type=float, metavar=("WEST", "SOUTH", "EAST", "NORTH"), default=DEFAULT_DAHISAR_BBOX)
    args = parser.parse_args()
    main(args.output, args.bbox)
