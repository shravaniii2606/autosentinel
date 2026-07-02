import pandas as pd
import requests
import gzip
import io
from shapely.geometry import shape, box
import geopandas as gpd
import json

# Vasai Virar bbox
west, south, east, north = 72.80, 19.35, 72.95, 19.50

df = pd.read_csv("https://minedbuildings.z5.web.core.windows.net/global-buildings/dataset-links.csv")
india = df[df['Location'] == 'India']

buildings = []
checked = 0

for _, row in india.iterrows():
    url = row['Url']
    try:
        r = requests.get(url, timeout=60)
        with gzip.open(io.BytesIO(r.content), 'rt') as f:
            for line in f:
                try:
                    obj = json.loads(line)
                    geom = shape(json.loads(obj['geometry']))
                    c = geom.centroid
                    if west <= c.x <= east and south <= c.y <= north:
                        buildings.append({
                            'geometry': geom,
                            'confidence': obj.get('confidence', 0)
                        })
                except:
                    continue
        checked += 1
        if buildings:
            print(f"Found {len(buildings)} buildings so far (checked {checked} tiles)")
        if checked > 20 and not buildings:
            print("No buildings in first 20 tiles, trying next batch...")
    except Exception as e:
        continue

print(f"Total buildings found in Vasai Virar: {len(buildings)}")

if buildings:
    gdf = gpd.GeoDataFrame(buildings, crs='EPSG:4326')
    gdf.to_file('data/vasai_buildings_microsoft.geojson', driver='GeoJSON')
    print("Saved to data/vasai_buildings_microsoft.geojson")