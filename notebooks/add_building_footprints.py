import geopandas as gpd
import pandas as pd
from shapely.geometry import box
import json
import requests

# Vasai Virar bounding box
west, south, east, north = 72.80, 19.35, 72.95, 19.50

# Download Maharashtra building footprints
# Get the download URL from Microsoft's GitHub dataset table
url = "https://minedbuildings.z5.web.core.windows.net/global-buildings/dataset-links.csv"
df = pd.read_csv(url)

# Find India/Maharashtra row
india_rows = df[df['Location'].str.contains('India', na=False)]
print(india_rows[['Location', 'Url']].to_string())