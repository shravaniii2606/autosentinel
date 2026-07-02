# notebooks\find_quadkey.py
def lat_lon_to_quadkey(lat, lon, zoom=13):
    import math
    lat_rad = math.radians(lat)
    n = 2 ** zoom
    x = int((lon + 180) / 360 * n)
    y = int((1 - math.log(math.tan(lat_rad) + 1/math.cos(lat_rad)) / math.pi) / 2 * n)
    
    quadkey = ''
    for i in range(zoom, 0, -1):
        digit = 0
        mask = 1 << (i - 1)
        if x & mask:
            digit += 1
        if y & mask:
            digit += 2
        quadkey += str(digit)
    return quadkey

# Vasai Virar center
lat, lon = 19.42, 72.85
qk = lat_lon_to_quadkey(lat, lon, zoom=9)
print(f"Quadkey for Vasai Virar: {qk}")

# Check which tiles in dataset start with this prefix
import pandas as pd
df = pd.read_csv('https://minedbuildings.z5.web.core.windows.net/global-buildings/dataset-links.csv')
india = df[df['Location'] == 'India']

matches = india[india['Url'].str.contains(f'quadkey={qk}')]
print(f"Matching tiles: {len(matches)}")
print(matches['Url'].tolist())