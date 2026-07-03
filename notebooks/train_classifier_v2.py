# notebooks/train_classifier_v2.py
import pandas as pd
import numpy as np
import geopandas as gpd
import xgboost as xgb
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, precision_score, recall_score
import pickle
import json
import os


VISION_DEFAULTS = {
    'construction_detected': False,
    'crane_present': False,
    'building_present': False,
    'container_present': False,
    'vision_confidence': 0.0,
}


def load_vision_features(path='data/flagged_zones.json'):
    if not os.path.exists(path):
        return {}

    with open(path, encoding='utf-8') as f:
        zones = json.load(f)

    return {str(zone.get('id')): zone for zone in zones}


def vision_value(vision_by_id, zone_id, field):
    value = vision_by_id.get(str(zone_id), {}).get(field, VISION_DEFAULTS[field])
    if field == 'vision_confidence':
        return float(value or 0.0)
    return 1 if bool(value) else 0

# Load real labels
real_labels = pd.read_csv('data/labels.csv')
real_labels['is_real_label'] = True
print(f"Real labels: {len(real_labels)}")

# Load synthetic labels
synthetic = pd.read_csv('data/synthetic_labels.csv')
synthetic_labels = synthetic[['id', 'synthetic_label']].rename(
    columns={'synthetic_label': 'label'}
)
synthetic_labels['is_real_label'] = False

# Remove synthetic labels where we have real ones
synthetic_labels = synthetic_labels[
    ~synthetic_labels['id'].isin(real_labels['zone_id'])
]
print(f"Synthetic labels added: {len(synthetic_labels)}")

# Build feature matrix
gdf = gpd.read_file('data/zoned_violations.geojson')
gdf_proj = gdf.to_crs('EPSG:32643')
vision_by_id = load_vision_features()

rows = []
for idx, row in gdf_proj.iterrows():
    area = float(row['area_sqm'])
    perimeter = float(row.geometry.length)
    compactness = (4 * np.pi * area) / (perimeter ** 2) if perimeter > 0 else 0
    violation = str(row.get('violation_type', 'UNVERIFIED_ZONE'))
    microsoft = bool(row.get('microsoft_confirmed', False))

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
        'construction_detected': vision_value(vision_by_id, idx, 'construction_detected'),
        'crane_present': vision_value(vision_by_id, idx, 'crane_present'),
        'building_present': vision_value(vision_by_id, idx, 'building_present'),
        'container_present': vision_value(vision_by_id, idx, 'container_present'),
        'vision_confidence': vision_value(vision_by_id, idx, 'vision_confidence'),
    })

features_df = pd.DataFrame(rows)

# Merge real labels
real_merged = features_df.merge(
    real_labels[['zone_id', 'label']],
    left_on='id', right_on='zone_id', how='inner'
)
real_merged['weight'] = 3.0  # Real labels weighted 3x

# Merge synthetic labels
synth_merged = features_df.merge(
    synthetic_labels[['id', 'label']],
    on='id', how='inner'
)
synth_merged['weight'] = 1.0  # Synthetic labels weighted 1x

# Combine
combined = pd.concat([
    real_merged[features_df.columns.tolist() + ['label', 'weight']],
    synth_merged[features_df.columns.tolist() + ['label', 'weight']]
], ignore_index=True)

print(f"\nCombined dataset: {len(combined)}")
print(f"Label=1: {combined['label'].sum()}")
print(f"Label=0: {(combined['label']==0).sum()}")

feature_cols = ['area_sqm', 'log_area', 'compactness', 'perimeter',
                'is_forest', 'is_agricultural', 'is_unverified',
                'risk_score', 'microsoft_confirmed', 'construction_detected',
                'crane_present', 'building_present', 'container_present',
                'vision_confidence']

X = combined[feature_cols]
y = combined['label']
w = combined['weight']

X_train, X_test, y_train, y_test, w_train, w_test = train_test_split(
    X, y, w, test_size=0.2, random_state=42, stratify=y
)

model = xgb.XGBClassifier(
    n_estimators=100,
    max_depth=4,
    learning_rate=0.1,
    scale_pos_weight=len(y[y==0]) / max(len(y[y==1]), 1),
    random_state=42,
    eval_metric='logloss',
    verbosity=0
)
model.fit(X_train, y_train, sample_weight=w_train)

y_pred = model.predict(X_test)
print("\nModel Performance:")
print(classification_report(y_test, y_pred,
    target_names=['False Positive', 'Real Construction']))
print(f"Precision: {precision_score(y_test, y_pred, zero_division=0):.2f}")
print(f"Recall: {recall_score(y_test, y_pred, zero_division=0):.2f}")

print("\nFeature Importance:")
for feat, imp in sorted(zip(feature_cols, model.feature_importances_),
                         key=lambda x: -x[1]):
    print(f"  {feat}: {imp:.3f}")

# Save model
with open('data/classifier_model_v2.pkl', 'wb') as f:
    pickle.dump(model, f)
print("\nModel v2 saved")

# Score all zones
all_features = features_df[feature_cols]
features_df['ml_confidence'] = model.predict_proba(all_features)[:, 1]
features_df['is_likely_real'] = model.predict(all_features)

real_count = int(features_df['is_likely_real'].sum())
print(f"\nOf 931 zones — Likely real: {real_count}, Likely false positive: {931-real_count}")

# Update flagged_zones.json
with open('data/flagged_zones.json') as f:
    zones = json.load(f)

ml_dict = dict(zip(features_df['id'].astype(str),
                   features_df['ml_confidence']))
real_dict = dict(zip(features_df['id'].astype(str),
                     features_df['is_likely_real']))

for zone in zones:
    zone_id = str(zone['id'])
    zone['ml_confidence'] = round(float(ml_dict.get(zone_id, 0.5)), 2)
    zone['is_likely_real'] = bool(real_dict.get(zone_id, True))

with open('data/flagged_zones.json', 'w') as f:
    json.dump(zones, f, indent=2)

print("Updated flagged_zones.json")
