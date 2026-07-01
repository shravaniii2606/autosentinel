import ee
import geemap
import numpy as np
import argparse
import sys
import os


def main(minx, miny, maxx, maxy, out_tif):
    # Initialize
    ee.Initialize(project='ee-autosentinel')
    print("GEE Connected")

    region = ee.Geometry.Rectangle([minx, miny, maxx, maxy])

    # Before image (2019)
    before = (ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
        .filterBounds(region)
        .filterDate('2019-01-01', '2019-12-31')
        .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 10))
        .median()
        .clip(region))

    # After image (2023)
    after = (ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
        .filterBounds(region)
        .filterDate('2023-01-01', '2023-12-31')
        .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 10))
        .median()
        .clip(region))

    # NDBI change detection
    ndbi_before = before.normalizedDifference(['B11', 'B8'])
    ndbi_after = after.normalizedDifference(['B11', 'B8'])
    change = ndbi_after.subtract(ndbi_before)
    new_construction = change.gt(0.15)

    print("Images loaded, running change detection...")

    out_dir = os.path.dirname(out_tif)
    if out_dir and not os.path.exists(out_dir):
        os.makedirs(out_dir, exist_ok=True)

    # Use geemap helper to export to local file (blocks until finished)
    print(f"Exporting change mask to {out_tif} (this may take a few minutes)")
    geemap.ee_export_image(new_construction.selfMask(), filename=out_tif, scale=10, region=[minx, miny, maxx, maxy])
    print("Export complete")


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('minx', type=float)
    parser.add_argument('miny', type=float)
    parser.add_argument('maxx', type=float)
    parser.add_argument('maxy', type=float)
    parser.add_argument('out_tif', type=str)
    args = parser.parse_args()
    main(args.minx, args.miny, args.maxx, args.maxy, args.out_tif)