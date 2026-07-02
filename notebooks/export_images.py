import ee
import os
import requests
import json

ee.Initialize(project='ee-autosentinel')

with open('data/flagged_zones.json') as f:
    zones = json.load(f)

# Get HIGH zones not already exported
already_exported = set()
images_dir = 'data/images'
for f in os.listdir(images_dir):
    if '_before.png' in f:
        zone_id = f.replace('zone_', '').replace('_before.png', '')
        already_exported.add(zone_id)

print(f"Already have images for {len(already_exported)} zones")

# Target HIGH and remaining CRITICAL/MEDIUM zones
target_zones = [z for z in zones 
                if z['severity'] in ['HIGH', 'CRITICAL', 'MEDIUM'] 
                and str(z['id']) not in already_exported][:50]

print(f"Exporting {len(target_zones)} new zones...")
os.makedirs(images_dir, exist_ok=True)

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
    response = requests.get(url, timeout=60)
    filename = f'{images_dir}/zone_{zone_id}_{period}.png'
    with open(filename, 'wb') as f:
        f.write(response.content)
    return filename

for zone in target_zones:
    try:
        print(f"Exporting zone {zone['id']} ({zone['severity']})...")
        export_thumbnail(before, zone['id'], 'before', zone['lat'], zone['lon'])
        export_thumbnail(after, zone['id'], 'after', zone['lat'], zone['lon'])
        print(f"  Done")
    except Exception as e:
        print(f"  Failed: {e}")

print("Export complete")