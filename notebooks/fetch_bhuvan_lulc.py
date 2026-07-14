#!/usr/bin/env python3
"""Prepare and optionally apply Dahisar land-use verification.

Despite its legacy filename, this is not a Bhuvan scraper.  It uses a local,
reviewable OSM-derived Dahisar extract through a provider interface, leaving a
single replacement point for the future official ISRO Bhuvan provider.
"""
from __future__ import annotations

import argparse
import os

import geopandas as gpd

from landuse_providers import LocalGeoJSONProvider, annotate_zones


def main(source: str, output: str, bbox=None, zones_path=None, zones_output=None) -> None:
    provider = LocalGeoJSONProvider(source)
    layer = provider.load_landuse(bbox)
    os.makedirs(os.path.dirname(output) or ".", exist_ok=True)
    layer.to_file(output, driver="GeoJSON")
    print(f"Loaded {len(layer)} land-use polygons from {source}")
    print(f"Saved normalised land-use layer to {output}")

    if not zones_path:
        return
    zones = gpd.read_file(zones_path)
    annotated = annotate_zones(zones, layer)
    target = zones_output or zones_path
    annotated.to_file(target, driver="GeoJSON")
    print(f"Intersected {len(annotated)} zones")
    for position, (_, zone) in enumerate(annotated.iterrows(), start=1):
        print(f"Zone {position} -> {zone['bhuvan_land_type']} ({zone['bhuvan_overlap_percent']:.1f}%)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Load and apply the Dahisar land-use verification layer.")
    parser.add_argument("--source", default="data/dahisar_landuse.geojson", help="Independent normalised local GeoJSON layer.")
    parser.add_argument("--output", default="data/bhuvan_lulc.geojson", help="Compatibility output for the existing legal-scoring stage.")
    parser.add_argument("--bbox", nargs=4, type=float, metavar=("WEST", "SOUTH", "EAST", "NORTH"), help="Optional crop extent.")
    parser.add_argument("--zones", help="Optional detected-construction GeoJSON to annotate.")
    parser.add_argument("--zones-output", help="Where to write annotated zones; defaults to --zones.")
    args = parser.parse_args()
    main(args.source, args.output, args.bbox, args.zones, args.zones_output)
