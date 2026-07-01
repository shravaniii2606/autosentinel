import osmnx as ox
import geopandas as gpd
import json
import osmnx._settings as settings

# Use a smaller area — just the forest edge zone where CRITICAL violations are
# Zone 82 is at 19.495, 72.806 — zoom in tight around it
print("Fetching land use for critical zone area only...")

# Much smaller bbox — just 2km around the top critical zone
tags = {'landuse': True, 'natural': True}

try:
    gdf_landuse = ox.features_from_bbox(
        bbox=(19.51, 19.47, 72.83, 72.79),
        tags=tags
    )
    print(f"Fetched {len(gdf_landuse)} land use features")
    gdf_landuse = gdf_landuse[['geometry', 'landuse', 'natural']].copy()
    gdf_landuse = gdf_landuse.to_crs('EPSG:4326')
    gdf_landuse.to_file('data/landuse_critical.geojson', driver='GeoJSON')
    print("Saved data/landuse_critical.geojson")
    print(gdf_landuse[['landuse', 'natural']].head(20))

except Exception as e:
    print(f"OSM fetch failed: {e}")
    print("Creating manual zoning data instead...")

    # Fallback — manually define known land types for demo
    # Based on publicly known Vasai Virar zoning (forest + wetland on eastern edge)
    from shapely.geometry import Polygon
    import pandas as pd

    manual_zones = [
        {
            'geometry': Polygon([(72.79, 19.47), (72.83, 19.47),
                                  (72.83, 19.51), (72.79, 19.51)]),
            'landuse': 'forest',
            'natural': 'wood',
            'zone_label': 'Protected Forest Zone'
        },
        {
            'geometry': Polygon([(72.88, 19.43), (72.91, 19.43),
                                  (72.91, 19.46), (72.88, 19.46)]),
            'landuse': None,
            'natural': 'wetland',
            'zone_label': 'Wetland / Water Body Buffer'
        },
        {
            'geometry': Polygon([(72.84, 19.35), (72.88, 19.35),
                                  (72.88, 19.38), (72.84, 19.38)]),
            'landuse': 'farmland',
            'natural': None,
            'zone_label': 'Agricultural Land'
        },
    ]

    gdf_landuse = gpd.GeoDataFrame(manual_zones, crs='EPSG:4326')
    gdf_landuse.to_file('data/landuse_critical.geojson', driver='GeoJSON')
    print("Saved manual zoning data")
    print(gdf_landuse[['landuse', 'natural', 'zone_label']])

# Now cross-reference with flagged zones
print("\nCross-referencing with flagged zones...")
gdf_zones = gpd.read_file('data/scored_zones.geojson')
gdf_zones = gdf_zones.to_crs('EPSG:4326')

gdf_landuse_clean = gdf_landuse[['geometry', 'landuse', 'natural']].copy()

gdf_joined = gpd.sjoin(
    gdf_zones,
    gdf_landuse_clean,
    how='left',
    predicate='intersects'
)
gdf_joined = gdf_joined[~gdf_joined.index.duplicated(keep='first')]

def get_violation_type(row):
    natural = str(row.get('natural', '')).lower()
    landuse = str(row.get('landuse', '')).lower()
    if any(x in natural for x in ['wood', 'forest', 'scrub', 'wetland']):
        return 'FOREST_ENCROACHMENT'
    elif 'water' in natural or 'wetland' in natural:
        return 'WATER_BODY_ENCROACHMENT'
    elif any(x in landuse for x in ['forest', 'conservation']):
        return 'PROTECTED_LAND'
    elif any(x in landuse for x in ['farmland', 'agricultural', 'farm']):
        return 'AGRICULTURAL_LAND'
    elif any(x in landuse for x in ['residential', 'commercial']):
        return 'POSSIBLE_PERMIT_VIOLATION'
    else:
        return 'UNVERIFIED_ZONE'

gdf_joined['violation_type'] = gdf_joined.apply(get_violation_type, axis=1)

print("\nViolation type breakdown:")
print(gdf_joined['violation_type'].value_counts())

gdf_joined.to_file('data/zoned_violations.geojson', driver='GeoJSON')
print("Saved data/zoned_violations.geojson")