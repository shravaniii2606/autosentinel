import osmnx as ox
import geopandas as gpd
import json

print("Fetching land use data for Vasai Virar from OSM...")

# Fetch land use polygons from OpenStreetMap
tags = {'landuse': True, 'natural': True, 'leisure': True}
vasai_bbox = (19.35, 72.80, 19.50, 72.95)  # north, south, east, west... actually:
gdf_landuse = ox.features_from_bbox(
    bbox=(19.50, 19.35, 72.95, 72.80),
    tags=tags
)

print(f"Land use zones fetched: {len(gdf_landuse)}")
print("Land use types found:")
print(gdf_landuse['landuse'].value_counts().head(20))

# Keep only geometry and relevant columns
cols = ['geometry', 'landuse', 'natural', 'leisure', 'name']
cols = [c for c in cols if c in gdf_landuse.columns]
gdf_landuse = gdf_landuse[cols].copy()
gdf_landuse = gdf_landuse.to_crs('EPSG:4326')

# Save raw landuse
gdf_landuse.to_file('data/landuse.geojson', driver='GeoJSON')
print("Saved data/landuse.geojson")

# Load your flagged zones
gdf_zones = gpd.read_file('data/scored_zones.geojson')
gdf_zones = gdf_zones.to_crs('EPSG:4326')

# Spatial join — find what land type each flagged zone falls on
gdf_joined = gpd.sjoin(
    gdf_zones,
    gdf_landuse[['geometry', 'landuse', 'natural']],
    how='left',
    predicate='intersects'
)

# Drop duplicate matches, keep first
gdf_joined = gdf_joined[~gdf_joined.index.duplicated(keep='first')]

print(f"\nZoning cross-reference complete")
print("Land use breakdown of flagged zones:")
print(gdf_joined['landuse'].value_counts())
print(gdf_joined['natural'].value_counts())

# Define violation severity based on land type
def get_violation_type(row):
    natural = str(row.get('natural', '')).lower()
    landuse = str(row.get('landuse', '')).lower()

    if any(x in natural for x in ['wood', 'forest', 'scrub', 'wetland']):
        return 'FOREST_ENCROACHMENT'
    elif 'water' in natural or 'wetland' in natural:
        return 'WATER_BODY_ENCROACHMENT'
    elif any(x in landuse for x in ['forest', 'conservation']):
        return 'PROTECTED_LAND'
    elif 'farmland' in landuse or 'agricultural' in landuse or 'farm' in landuse:
        return 'AGRICULTURAL_LAND'
    elif 'residential' in landuse or 'commercial' in landuse:
        return 'POSSIBLE_PERMIT_VIOLATION'
    else:
        return 'UNVERIFIED_ZONE'

gdf_joined['violation_type'] = gdf_joined.apply(get_violation_type, axis=1)

print("\nViolation type breakdown:")
print(gdf_joined['violation_type'].value_counts())

# Save final enriched output
gdf_joined.to_file('data/zoned_violations.geojson', driver='GeoJSON')
print("\nSaved data/zoned_violations.geojson")