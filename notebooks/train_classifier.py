import pandas as pd
import numpy as np
import geopandas as gpd
import xgboost as xgb
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, precision_score, recall_score
import pickle
import json

# Load labels
labels_df = pd.read_csv('data/labels.csv')
print(f"Labeled samples: {len(labels_df)}")

# Load zone features
gdf = gpd.read_file('data/zoned_violations.geojson')
gdf_proj = gdf.to_crs('EPSG:32643')

# Build feature matrix
rows = []
for idx, row in gdf_proj.iterrows():
    area = float(row['area_sqm'])
    perimeter = float(row.geometry.length)
    compactness = (4 * np.pi * area) / (perimeter ** 2) if perimeter > 0 else 0
    violation = str(row.get('violation_type', 'UNVERIFIED_ZONE'))

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
    })

features_df = pd.DataFrame(rows)

# Merge with labels
merged = features_df.merge(labels_df, left_on='id', right_on='zone_id', how='inner')
print(f"Matched samples: {len(merged)}")
print(f"Real construction (1): {merged['label'].sum()}")
print(f"False positive (0): {(merged['label']==0).sum()}")

feature_cols = ['area_sqm', 'log_area', 'compactness', 'perimeter',
                'is_forest', 'is_agricultural', 'is_unverified', 'risk_score']

X = merged[feature_cols]
y = merged['label']

# With small dataset use all for training, small test split
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42, stratify=y
)

model = xgb.XGBClassifier(
    n_estimators=50,
    max_depth=3,
    learning_rate=0.1,
    scale_pos_weight=len(y[y==0]) / max(len(y[y==1]), 1),
    random_state=42,
    eval_metric='logloss',
    verbosity=0
)
model.fit(X_train, y_train)

y_pred = model.predict(X_test)
print("\nModel Performance:")
print(classification_report(y_test, y_pred, target_names=['False Positive', 'Real Construction']))
print(f"Precision: {precision_score(y_test, y_pred, zero_division=0):.2f}")
print(f"Recall: {recall_score(y_test, y_pred, zero_division=0):.2f}")

# Feature importance
print("\nFeature Importance:")
for feat, imp in sorted(zip(feature_cols, model.feature_importances_), key=lambda x: -x[1]):
    print(f"  {feat}: {imp:.3f}")

# Save model
with open('data/classifier_model.pkl', 'wb') as f:
    pickle.dump(model, f)
print("\nModel saved to data/classifier_model.pkl")

# Score ALL 931 zones
all_features = features_df[feature_cols]
features_df['real_construction_probability'] = model.predict_proba(all_features)[:, 1]
features_df['is_likely_real'] = model.predict(all_features)

real_count = int(features_df['is_likely_real'].sum())
fake_count = len(features_df) - real_count
print(f"\nOf {len(features_df)} zones:")
print(f"  Likely real construction: {real_count}")
print(f"  Likely false positive: {fake_count}")

# Save scores
features_df[['id', 'real_construction_probability', 'is_likely_real']].to_csv(
    'data/ml_scores.csv', index=False
)
print("Scores saved to data/ml_scores.csv")

# Update flagged_zones.json with ML scores
with open('data/flagged_zones.json') as f:
    zones = json.load(f)

ml_dict = dict(zip(
    features_df['id'].astype(str),
    features_df['real_construction_probability']
))
real_dict = dict(zip(
    features_df['id'].astype(str),
    features_df['is_likely_real']
))

for zone in zones:
    zone_id = str(zone['id'])
    zone['ml_confidence'] = round(float(ml_dict.get(zone_id, 0.5)), 2)
    zone['is_likely_real'] = bool(real_dict.get(zone_id, True))

with open('data/flagged_zones.json', 'w') as f:
    json.dump(zones, f, indent=2)

print("Updated flagged_zones.json with ml_confidence and is_likely_real fields")