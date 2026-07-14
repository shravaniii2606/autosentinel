import ee
import requests

ee.Initialize(project='ee-autosentinel')

region = ee.Geometry.Rectangle([72.8516, 19.2419, 72.8676, 19.2569])

before = (
    ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
    .filterBounds(region)
    .filterDate('2024-01-01', '2024-12-31')
    .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 20))
    .median()
    .clip(region)
)

after = (
    ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
    .filterBounds(region)
    .filterDate('2025-01-01', '2025-12-31')
    .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 20))
    .median()
    .clip(region)
)

ndbi_before = before.normalizedDifference(['B11', 'B8']).rename('nd')
ndbi_after = after.normalizedDifference(['B11', 'B8']).rename('nd')

change = ndbi_after.subtract(ndbi_before)
new_construction = change.gt(0.15).rename('nd')

# Check whether any change exists
area_img = new_construction.selfMask().multiply(ee.Image.pixelArea())

total_area = area_img.reduceRegion(
    reducer=ee.Reducer.sum(),
    geometry=region,
    scale=10,
    maxPixels=1e9
).get('nd')

print("Flagged construction area (sqm):", total_area.getInfo())

# Download raster
url = new_construction.getDownloadURL({
    'scale': 10,
    'region': region,
    'format': 'GEO_TIFF'
})

print("Downloading...")

r = requests.get(url, timeout=300)
r.raise_for_status()

with open("dahisar_change.tif", "wb") as f:
    f.write(r.content)

print("Saved dahisar_change.tif")
print("Done.")