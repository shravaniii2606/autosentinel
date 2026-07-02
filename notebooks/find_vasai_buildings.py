import pandas as pd
import requests
import gzip
import io
import json
import geopandas as gpd
from shapely.geometry import shape

west, south, east, north = 72.80, 19.35, 72.95, 19.50

df = pd.read_csv('https://minedbuildings.z5.web.core.windows.net/global-buildings/dataset-links.csv')
india = df[df['Location'] == 'India']

buildings = []
checked = 0

for _, row in india.iterrows():
    url = row['Url']
    try:
        r = requests.get(url, timeout=60)
        found_in_tile = 0
        with gzip.open(io.BytesIO(r.content), 'rt') as f:
            for line in f:
                try:
                    obj = json.loads(line)
                    coords = obj['geometry']['coordinates'][0][0]
                    lon, lat = coords[0], coords[1]
                    if west <= lon <= east and south <= lat <= north:
                        geom = shape(obj['geometry'])
                        buildings.append({
                            'geometry': geom,
                            'confidence': obj['properties'].get('confidence', -1),
                            'height': obj['properties'].get('height', -1)
                        })
                        found_in_tile += 1
                except:
                    continue
        checked += 1
        if found_in_tile > 0:
            print(f"Tile {checked}: found {found_in_tile} buildings! Total: {len(buildings)}")
        elif checked % 10 == 0:
            print(f"Checked {checked} tiles, {len(buildings)} buildings so far...")
    except Exception as e:
        continue

print(f"\nTotal Microsoft buildings in Vasai Virar: {len(buildings)}")

if buildings:
    gdf = gpd.GeoDataFrame(buildings, crs='EPSG:4326')
    gdf.to_file('data/vasai_buildings_microsoft.geojson', driver='GeoJSON')
    print("Saved to data/vasai_buildings_microsoft.geojson")
else:
    print("No buildings found - Vasai Virar may not be in this dataset release")