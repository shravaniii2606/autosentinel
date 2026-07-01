import ee
import geemap
import numpy as np

# Initialize
ee.Initialize(project='ee-autosentinel')
print("GEE Connected")

# Define Vasai Virar area
vasai = ee.Geometry.Rectangle([72.80, 19.35, 72.95, 19.50])

# Before image (2019)
before = (ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
    .filterBounds(vasai)
    .filterDate('2019-01-01', '2019-12-31')
    .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 10))
    .median()
    .clip(vasai))

# After image (2023)
after = (ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
    .filterBounds(vasai)
    .filterDate('2023-01-01', '2023-12-31')
    .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 10))
    .median()
    .clip(vasai))

# NDBI change detection
ndbi_before = before.normalizedDifference(['B11', 'B8'])
ndbi_after = after.normalizedDifference(['B11', 'B8'])
change = ndbi_after.subtract(ndbi_before)
new_construction = change.gt(0.15)

print("Images loaded, running change detection...")

# Export new construction mask as GeoJSON to local data folder
task = ee.batch.Export.image.toDrive(
    image=new_construction,
    description='vasai_new_construction',
    folder='autosentinel',
    fileNamePrefix='vasai_change',
    region=vasai,
    scale=10,
    fileFormat='GeoTIFF'
)
task.start()
print(f"Export task started: {task.status()}")