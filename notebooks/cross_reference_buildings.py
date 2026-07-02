# notebooks\cross_reference_buildings.py
import geopandas as gpd
import json

print("Loading data...")
gdf_buildings = gpd.read_file('data/vasai_buildings_microsoft.geojson')
gdf_zones = gpd.read_file('data/zoned_violations.geojson')

print(f"Microsoft buildings: {len(gdf_buildings)}")
print(f"Flagged zones: {len(gdf_zones)}")

gdf_buildings = gdf_buildings.to_crs('EPSG:4326')
gdf_zones = gdf_zones.to_crs('EPSG:4326')

# Drop any conflicting columns before join
gdf_buildings = gdf_buildings[['geometry', 'confidence']].reset_index(drop=True)
gdf_zones = gdf_zones.reset_index(drop=True)

# Remove index_right if it exists
for col in ['index_right', 'index_left']:
    if col in gdf_zones.columns:
        gdf_zones = gdf_zones.drop(columns=[col])
    if col in gdf_buildings.columns:
        gdf_buildings = gdf_buildings.drop(columns=[col])

joined = gpd.sjoin(
    gdf_zones,
    gdf_buildings,
    how='left',
    predicate='intersects'
)
joined = joined[~joined.index.duplicated(keep='first')]

joined['microsoft_match'] = joined['confidence'].notna()
matched = joined['microsoft_match'].sum()

print(f"\nZones with Microsoft building match: {matched}/{len(gdf_zones)}")
print(f"Zones without match (likely false positives): {len(gdf_zones) - matched}")

joined.to_file('data/zoned_violations_enriched.geojson', driver='GeoJSON')
print("Saved zoned_violations_enriched.geojson")

with open('data/flagged_zones.json') as f:
    zones = json.load(f)

match_dict = dict(zip(joined.index, joined['microsoft_match']))

for zone in zones:
    zone['microsoft_confirmed'] = bool(match_dict.get(zone['id'], False))

with open('data/flagged_zones.json', 'w') as f:
    json.dump(zones, f, indent=2)

confirmed = sum(1 for z in zones if z.get('microsoft_confirmed'))
print(f"\nConfirmed by Microsoft: {confirmed}")
print(f"Not confirmed: {len(zones) - confirmed}")