# notebooks\download_vasai_buildings.py
import requests
import gzip
import io
import json
import geopandas as gpd
from shapely.geometry import shape

url = 'https://minedbuildings.z5.web.core.windows.net/global-buildings/2026-02-03/global-buildings.geojsonl/RegionName=India/quadkey=123300133/part-00147-4feead82-d499-422b-94cb-c036c212127a.c000.csv.gz'

west, south, east, north = 72.80, 19.35, 72.95, 19.50

print("Downloading Vasai Virar tile...")
r = requests.get(url, timeout=120)
print(f"Downloaded {len(r.content)} bytes")

buildings = []
total_in_tile = 0

with gzip.open(io.BytesIO(r.content), 'rt') as f:
    for line in f:
        try:
            obj = json.loads(line)
            total_in_tile += 1
            coords = obj['geometry']['coordinates'][0][0]
            lon, lat = coords[0], coords[1]
            if west <= lon <= east and south <= lat <= north:
                buildings.append({
                    'geometry': shape(obj['geometry']),
                    'confidence': obj['properties'].get('confidence', -1),
                    'height': obj['properties'].get('height', -1)
                })
        except:
            continue

print(f"Total buildings in tile: {total_in_tile}")
print(f"Buildings in Vasai Virar bbox: {len(buildings)}")

if buildings:
    gdf = gpd.GeoDataFrame(buildings, crs='EPSG:4326')
    gdf.to_file('data/vasai_buildings_microsoft.geojson', driver='GeoJSON')
    print(f"Saved {len(buildings)} buildings to data/vasai_buildings_microsoft.geojson")