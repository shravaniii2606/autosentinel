import ee
import os
import requests

ee.Initialize(project='ee-autosentinel')

import json
with open('data/flagged_zones.json') as f:
    zones = json.load(f)

# Take top 5 critical zones only
critical = [z for z in zones if z['severity'] == 'CRITICAL'][:5]

os.makedirs('data/images', exist_ok=True)

def export_thumbnail(image, zone_id, period, lat, lon):
    region = ee.Geometry.Rectangle([
        lon - 0.01, lat - 0.01,
        lon + 0.01, lat + 0.01
    ])
    url = image.clip(region).getThumbURL({
        'bands': ['B4', 'B3', 'B2'],
        'min': 0,
        'max': 3000,
        'dimensions': 512,
        'region': region
    })
    response = requests.get(url)
    filename = f'data/images/zone_{zone_id}_{period}.png'
    with open(filename, 'wb') as f:
        f.write(response.content)
    print(f"Saved {filename}")

vasai = ee.Geometry.Rectangle([72.80, 19.35, 72.95, 19.50])

before = (ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
    .filterBounds(vasai)
    .filterDate('2019-01-01', '2019-12-31')
    .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 10))
    .median())

after = (ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
    .filterBounds(vasai)
    .filterDate('2023-01-01', '2023-12-31')
    .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 10))
    .median())

for zone in critical:
    print(f"Exporting zone {zone['id']}...")
    export_thumbnail(before, zone['id'], 'before', zone['lat'], zone['lon'])
    export_thumbnail(after, zone['id'], 'after', zone['lat'], zone['lon'])

print("All images exported to data/images/")