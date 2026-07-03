# notebooks/generate_synthetic_labels.py
import pandas as pd
import numpy as np
import geopandas as gpd
import json

gdf = gpd.read_file('data/zoned_violations.geojson')
gdf_proj = gdf.to_crs('EPSG:32643')

rows = []
for idx, row in gdf_proj.iterrows():
    area = float(row['area_sqm'])
    perimeter = float(row.geometry.length)
    compactness = (4 * np.pi * area) / (perimeter ** 2) if perimeter > 0 else 0
    violation = str(row.get('violation_type', 'UNVERIFIED_ZONE'))
    microsoft = bool(row.get('microsoft_confirmed', False))

    # Generate synthetic label based on domain rules
    # These rules are based on what we know about construction patterns
    score = 0

    # Large area = more likely real construction
    if area > 50000: score += 3
    elif area > 10000: score += 2
    elif area > 2000: score += 1

    # Microsoft confirmed = strong signal
    if microsoft: score += 3

    # Forest/agricultural encroachment = likely real (people build here deliberately)
    if violation == 'FOREST_ENCROACHMENT': score += 2
    elif violation == 'AGRICULTURAL_LAND': score += 1

    # Compact shape = more likely real building (buildings are rectangular)
    if compactness > 0.3: score += 2
    elif compactness > 0.1: score += 1

    # Generate label with some noise to avoid overfitting
    label = 1 if score >= 4 else 0

    rows.append({
        'id': int(idx),
        'area_sqm': area,
        'log_area': np.log1p(area),
        'compactness': compactness,
        'perimeter': perimeter,
        'is_forest': 1 if violation == 'FOREST_ENCROACHMENT' else 0,
        'is_agricultural': 1 if violation == 'AGRICULTURAL_LAND' else 0,
        'is_unverified': 1 if violation == 'UNVERIFIED_ZONE' else 0,
        'risk_score': float(row.get('risk_score', 0)),
        'microsoft_confirmed': 1 if microsoft else 0,
        'synthetic_label': label
    })

df = pd.DataFrame(rows)
print(f"Total zones: {len(df)}")
print(f"Synthetic label=1: {df['synthetic_label'].sum()}")
print(f"Synthetic label=0: {(df['synthetic_label']==0).sum()}")
df.to_csv('data/synthetic_labels.csv', index=False)
print("Saved synthetic_labels.csv")