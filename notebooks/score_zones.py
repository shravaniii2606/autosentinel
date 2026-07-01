import geopandas as gpd
import numpy as np

# Load detected zones
gdf = gpd.read_file('data/new_construction.geojson')
print(f"Loaded {len(gdf)} zones")

# Add severity score based on area size
# Larger construction = higher severity
def calculate_severity(area_sqm):
    if area_sqm > 50000:
        return 'CRITICAL'
    elif area_sqm > 10000:
        return 'HIGH'
    elif area_sqm > 2000:
        return 'MEDIUM'
    else:
        return 'LOW'

def calculate_score(area_sqm):
    if area_sqm > 50000:
        return 90 + min(9, (area_sqm - 50000) / 10000)
    elif area_sqm > 10000:
        return 70 + (area_sqm - 10000) / 2000
    elif area_sqm > 2000:
        return 40 + (area_sqm - 2000) / 200
    else:
        return 10 + (area_sqm - 500) / 150

gdf['severity'] = gdf['area_sqm'].apply(calculate_severity)
gdf['risk_score'] = gdf['area_sqm'].apply(calculate_score).round(1)

# Add centroid coordinates for frontend map pins
gdf['lat'] = gdf.geometry.centroid.y
gdf['lon'] = gdf.geometry.centroid.x

# Add recommended action per severity
def get_action(severity):
    actions = {
        'CRITICAL': 'Immediate ground inspection required — large unauthorized structure detected',
        'HIGH': 'Priority inspection within 48 hours — significant construction on flagged land',
        'MEDIUM': 'Schedule inspection — moderate unauthorized construction detected',
        'LOW': 'Log for routine inspection — small structure flagged'
    }
    return actions[severity]

gdf['action'] = gdf['severity'].apply(get_action)

# Summary
print("\nSeverity breakdown:")
print(gdf['severity'].value_counts())
print(f"\nTop 5 highest risk zones:")
print(gdf.nlargest(5, 'risk_score')[['area_sqm', 'severity', 'risk_score', 'lat', 'lon']])

# Save scored output
gdf.to_file('data/scored_zones.geojson', driver='GeoJSON')
print(f"\nSaved scored_zones.geojson")