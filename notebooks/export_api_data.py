import geopandas as gpd
import json
import os

# Prefer the legally-verified output if legal_zone_check.py has been run,
# fall back to the plain scored zones otherwise. Keeps this script working
# whether or not the legal verification step has been added to the pipeline.
LEGAL_PATH = 'data/legal_verified_zones.geojson'
SCORED_PATH = 'data/scored_zones.geojson'
source_path = LEGAL_PATH if os.path.exists(LEGAL_PATH) else SCORED_PATH
print(f"Loading zones from {source_path}")
gdf = gpd.read_file(source_path)

# Fix centroid warning - reproject to metric CRS first
gdf_projected = gdf.to_crs('EPSG:32643')  # UTM Zone 43N - correct for Maharashtra
gdf['lat'] = gdf_projected.geometry.centroid.to_crs('EPSG:4326').y
gdf['lon'] = gdf_projected.geometry.centroid.to_crs('EPSG:4326').x

has_legal_data = 'legal_risk_score' in gdf.columns

# Build clean API-ready JSON
output = []
for idx, row in gdf.iterrows():
    # risk_score stays the field name the frontend/backend already expect.
    # If legal verification ran, it becomes the combined score; otherwise
    # it's just the original area-based score, unchanged.
    final_score = float(row['final_risk_score']) if has_legal_data else float(row['risk_score'])

    zone = {
        'id': int(idx),
        'lat': round(float(row['lat']), 6),
        'lon': round(float(row['lon']), 6),
        'area_sqm': round(float(row['area_sqm']), 1),
        'severity': row['severity'],
        'risk_score': round(final_score, 1),
        'action': row['action'],
        'violation_type': row.get('violation_type', 'UNVERIFIED_ZONE'),
    }

    if has_legal_data:
        zone['construction_risk_score'] = float(row['risk_score'])
        zone['legal_risk_score'] = float(row['legal_risk_score'])
        zone['legal_violations'] = row.get('legal_violations', 'NONE')

    output.append(zone)

# Sort by risk score descending
output.sort(key=lambda x: x['risk_score'], reverse=True)

# Save
with open('data/flagged_zones.json', 'w') as f:
    json.dump(output, f, indent=2)

print(f"Exported {len(output)} zones to flagged_zones.json")
print(f"Top 3 zones:")
for zone in output[:3]:
    print(f"  [{zone['severity']}] score:{zone['risk_score']} area:{zone['area_sqm']}sqm @ {zone['lat']},{zone['lon']}")