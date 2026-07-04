# notebooks/fetch_bhuvan_wfs.py
import requests
import geopandas as gpd
import json

# Bhuvan WFS endpoint for LULC
url = "https://bhuvan-vec1.nrsc.gov.in/bhuvan/wfs"

params = {
    'service': 'WFS',
    'version': '1.1.0',
    'request': 'GetFeature',
    'typeName': 'lulc50k_2012_13:MH',  # Maharashtra LULC
    'outputFormat': 'application/json',
    'bbox': '72.80,19.35,72.95,19.50,EPSG:4326',
    'maxFeatures': 500
}

print("Fetching Bhuvan WFS data...")
try:
    r = requests.get(url, params=params, timeout=30)
    print(f"Status: {r.status_code}")
    print(f"Content type: {r.headers.get('content-type')}")
    print(f"Response preview: {r.text[:500]}")
    
    if r.status_code == 200 and 'json' in r.headers.get('content-type', ''):
        data = r.json()
        print(f"Features found: {len(data.get('features', []))}")
        with open('data/bhuvan_lulc.geojson', 'w') as f:
            json.dump(data, f)
        print("Saved to data/bhuvan_lulc.geojson")
except Exception as e:
    print(f"Failed: {e}")