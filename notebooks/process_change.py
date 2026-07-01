import rasterio
import numpy as np
import geopandas as gpd
from shapely.geometry import shape
import json
from rasterio.features import shapes

# Load the GeoTIFF
with rasterio.open('data/vasai_change.tif') as src:
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
    
    # Save as GeoJSON
    gdf.to_file('data/new_construction.geojson', driver='GeoJSON')
    print("Saved to data/new_construction.geojson")
    print(gdf.head())
else:
    print("No construction zones detected - try lowering threshold")