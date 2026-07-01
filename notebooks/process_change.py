import rasterio
import numpy as np
import geopandas as gpd
from shapely.geometry import shape
import json
from rasterio.features import shapes
import argparse
import os


def main(input_tif, output_geojson):
    # Load the GeoTIFF
    with rasterio.open(input_tif) as src:
        image = src.read(1)  # Read first band
        transform = src.transform
        crs = src.crs
        print(f"Image shape: {image.shape}")
        print(f"Unique values: {np.unique(image)}")
        print(f"CRS: {crs}")

    # Extract polygons where value = 1 (new construction detected)
    mask = image == 1
    results = []

    for geom, val in shapes(image.astype(np.float32), mask=mask, transform=transform):
        if val == 1.0:
            results.append({
                'geometry': geom,
                'area_sqm': shape(geom).area * 111320**2,  # rough conversion to sq meters
            })

    print(f"\nNew construction zones detected: {len(results)}")

    # Convert to GeoDataFrame
    if results:
        gdf = gpd.GeoDataFrame(
            [{'area_sqm': r['area_sqm']} for r in results],
            geometry=[shape(r['geometry']) for r in results],
            crs='EPSG:4326'
        )
        
        # Filter out tiny noise patches (less than 500 sqm)
        gdf = gdf[gdf['area_sqm'] > 500]
        print(f"After noise filtering: {len(gdf)} zones")
        
        out_dir = os.path.dirname(output_geojson)
        if out_dir and not os.path.exists(out_dir):
            os.makedirs(out_dir, exist_ok=True)

        # Save as GeoJSON
        gdf.to_file(output_geojson, driver='GeoJSON')
        print(f"Saved to {output_geojson}")
        print(gdf.head())
    else:
        print("No construction zones detected - try lowering threshold")


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('input_tif', type=str)
    parser.add_argument('output_geojson', type=str)
    args = parser.parse_args()
    main(args.input_tif, args.output_geojson)