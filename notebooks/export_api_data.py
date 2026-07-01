import geopandas as gpd
import json

# Load scored zones
gdf = gpd.read_file('data/scored_zones.geojson')

# Fix centroid warning - reproject to metric CRS first
gdf_projected = gdf.to_crs('EPSG:32643')  # UTM Zone 43N - correct for Maharashtra
gdf['lat'] = gdf_projected.geometry.centroid.to_crs('EPSG:4326').y
gdf['lon'] = gdf_projected.geometry.centroid.to_crs('EPSG:4326').x

# Build clean API-ready JSON
output = []
for idx, row in gdf.iterrows():
    output.append({
        'id': int(idx),
        'lat': round(float(row['lat']), 6),
        'lon': round(float(row['lon']), 6),
        'area_sqm': round(float(row['area_sqm']), 1),
        'severity': row['severity'],
        'risk_score': float(row['risk_score']),
        'action': row['action']
    })

# Sort by risk score descending
output.sort(key=lambda x: x['risk_score'], reverse=True)

# Save
with open('data/flagged_zones.json', 'w') as f:
    json.dump(output, f, indent=2)

print(f"Exported {len(output)} zones to flagged_zones.json")
print(f"Top 3 zones:")
for zone in output[:3]:
    print(f"  [{zone['severity']}] score:{zone['risk_score']} area:{zone['area_sqm']}sqm @ {zone['lat']},{zone['lon']}")