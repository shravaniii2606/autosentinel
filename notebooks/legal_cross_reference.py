#!/usr/bin/env python3
import argparse
import os
import geopandas as gpd
import pandas as pd
from shapely.ops import unary_union
from shapely.geometry import Point
from landuse_providers import annotate_zones


def load_layer(path, required_columns=None):
    if not os.path.exists(path):
        print(f'Warning: missing layer {path}. Continuing with empty layer.')
        return gpd.GeoDataFrame(columns=['geometry'], geometry='geometry', crs='EPSG:4326')
    gdf = gpd.read_file(path)
    if gdf.crs is None:
        gdf = gdf.set_crs('EPSG:4326')
    else:
        gdf = gdf.to_crs('EPSG:4326')
    if required_columns:
        for col in required_columns:
            if col not in gdf.columns:
                gdf[col] = 0 if col == 'priority' else ('Unknown' if col == 'land_type' else 'Unknown source')
    return gdf


def add_bhuvan_flags(zones, bhuvan):
    zones = annotate_zones(zones, bhuvan)
    zones['legal_flags'] = zones['legal_flags'].apply(list)
    zones['risk_boost_total'] = zones['risk_boost_total'].astype(float)

    if bhuvan.empty:
        return zones
    boosts = {
        'Forest': ('FOREST_ENCROACHMENT', 15),
        'Wetland': ('WETLAND_ENCROACHMENT', 20),
        'Water Body': ('WATER_BODY_ENCROACHMENT', 20),
        'Park': ('PARK_ENCROACHMENT', 15),
        'Agriculture': ('AGRICULTURAL_LAND_VIOLATION', 10),
    }
    for index, zone in zones.iterrows():
        penalty = boosts.get(zone['bhuvan_land_type'])
        if penalty:
            flag, boost = penalty
            zones.at[index, 'legal_flags'].append(flag)
            zones.at[index, 'risk_boost_total'] += boost
    return zones


def add_osm_flags(zones, osm_layers):
    if 'legal_flags' not in zones.columns:
        zones['legal_flags'] = zones.apply(lambda _: [], axis=1)
    if 'risk_boost_total' not in zones.columns:
        zones['risk_boost_total'] = 0.0

    if osm_layers['airports'].empty and osm_layers['railways'].empty and osm_layers['rivers'].empty and osm_layers['protected'].empty and osm_layers['industrial'].empty:
        return zones

    # Airport proximity
    if not osm_layers['airports'].empty:
        airports = osm_layers['airports'].copy()
        airports = airports.to_crs('EPSG:32643')
        airports['geometry'] = airports.geometry.buffer(1000)
        airports = airports.to_crs('EPSG:4326')
        joined = gpd.sjoin(zones, airports[['geometry']], how='inner', predicate='intersects')
        for idx in joined.index.unique():
            zones.at[idx, 'legal_flags'].append('AIRPORT_BUFFER_VIOLATION')
            zones.at[idx, 'risk_boost_total'] += 20

    # Railway intersects
    if not osm_layers['railways'].empty:
        joined = gpd.sjoin(zones, osm_layers['railways'][['geometry']], how='inner', predicate='intersects')
        for idx in joined.index.unique():
            if 'RAILWAY_BUFFER_VIOLATION' not in zones.at[idx, 'legal_flags']:
                zones.at[idx, 'legal_flags'].append('RAILWAY_BUFFER_VIOLATION')
                zones.at[idx, 'risk_boost_total'] += 15

    # Rivers intersects
    if not osm_layers['rivers'].empty:
        joined = gpd.sjoin(zones, osm_layers['rivers'][['geometry']], how='inner', predicate='intersects')
        for idx in joined.index.unique():
            if 'RIVER_BUFFER_VIOLATION' not in zones.at[idx, 'legal_flags']:
                zones.at[idx, 'legal_flags'].append('RIVER_BUFFER_VIOLATION')
                zones.at[idx, 'risk_boost_total'] += 15

    # Protected areas inside
    if not osm_layers['protected'].empty:
        joined = gpd.sjoin(zones, osm_layers['protected'][['geometry']], how='inner', predicate='intersects')
        for idx in joined.index.unique():
            if 'PROTECTED_ZONE_VIOLATION' not in zones.at[idx, 'legal_flags']:
                zones.at[idx, 'legal_flags'].append('PROTECTED_ZONE_VIOLATION')
                zones.at[idx, 'risk_boost_total'] += 25

    return zones


def calculate_final_score(zones):
    def boost_value(row):
        score = float(row['risk_score'])
        score += float(row.get('risk_boost_total', 0))
        if row.get('microsoft_confirmed'):
            score += 10
        if row.get('crane_present'):
            score += 10
        if row.get('building_present'):
            score += 5
        return min(100, round(score, 1))

    zones['final_risk_score'] = zones.apply(boost_value, axis=1)
    return zones


def synthesize_explanation(row):
    if not isinstance(row['legal_flags'], list) or len(row['legal_flags']) == 0:
        return 'No legal violations detected from Bhuvan or OSM overlays.'

    parts = []
    if row.get('bhuvan_land_type') and row['bhuvan_land_type'] != 'Unknown':
        parts.append(f"Dahisar land-use verification classifies this land as {row['bhuvan_land_type']} ({row.get('bhuvan_overlap_percent', 0):.1f}% overlap; {row.get('bhuvan_confidence', 'Low')} confidence).")
    if row.get('osm_flags'):
        parts.append(f"OSM infrastructure overlays detected: {', '.join(row['osm_flags']).replace('_', ' ')}.")
    parts.append(f"This construction appears to violate: {', '.join(row['legal_flags']).replace('_', ' ')}.")
    boost_parts = []
    if row.get('bhuvan_land_type') == 'Forest':
        boost_parts.append('Forest boost +15')
    if row.get('bhuvan_land_type') == 'Wetland':
        boost_parts.append('Wetland boost +20')
    if row.get('bhuvan_land_type') == 'Water Body':
        boost_parts.append('Waterbody boost +20')
    if row.get('bhuvan_land_type') == 'Agriculture':
        boost_parts.append('Agriculture boost +10')
    if 'AIRPORT_BUFFER_VIOLATION' in row['legal_flags']:
        boost_parts.append('Airport buffer boost +20')
    if 'RAILWAY_BUFFER_VIOLATION' in row['legal_flags']:
        boost_parts.append('Railway boost +15')
    if 'RIVER_BUFFER_VIOLATION' in row['legal_flags']:
        boost_parts.append('River boost +15')
    if 'PROTECTED_ZONE_VIOLATION' in row['legal_flags']:
        boost_parts.append('Protected zone boost +25')
    if row.get('bhuvan_land_type') == 'Park':
        boost_parts.append('Park boost +15')
    if row.get('microsoft_confirmed'):
        boost_parts.append('Microsoft confirmed +10')
    if row.get('crane_present'):
        boost_parts.append('Crane detected +10')
    if row.get('building_present'):
        boost_parts.append('Building detected +5')
    if boost_parts:
        parts.append('Risk reason: ' + '; '.join(boost_parts) + f'. Final risk: {row.get('final_risk_score', row.get("risk_score", 0))}/100.')
    return ' '.join(parts)


def main(new_construction_path, output_path, bhuvan_path, data_dir):
    zones = gpd.read_file(new_construction_path)
    if zones.crs is None:
        zones = zones.set_crs('EPSG:4326')
    else:
        zones = zones.to_crs('EPSG:4326')

    zones['legal_flags'] = zones.apply(lambda _: [], axis=1)
    zones['risk_boost_total'] = 0.0
    zones['bhuvan_land_type'] = 'Unknown'
    zones['bhuvan_confidence'] = 'Low'
    zones['bhuvan_overlap_percent'] = 0.0
    zones['bhuvan_source'] = 'No land-use polygon intersected'
    zones['osm_flags'] = zones.apply(lambda _: [], axis=1)
    zones['microsoft_confirmed'] = zones.get('microsoft_confirmed', False)
    zones['crane_present'] = zones.get('crane_present', False)
    zones['building_present'] = zones.get('building_present', False)
    # Keep the command-line tool safe for raw detections as well as the backend's
    # already-scored zones.
    if 'risk_score' not in zones.columns:
        zones['risk_score'] = 0.0

    bhuvan = load_layer(bhuvan_path, required_columns=['land_type', 'source', 'priority'])
    zones = add_bhuvan_flags(zones, bhuvan)

    osm_layers = {
        'airports': load_layer(os.path.join(data_dir, 'osm_airports.geojson')),
        'railways': load_layer(os.path.join(data_dir, 'osm_railways.geojson')),
        'rivers': load_layer(os.path.join(data_dir, 'osm_rivers.geojson')),
        'roads': load_layer(os.path.join(data_dir, 'osm_roads.geojson')),
        'industrial': load_layer(os.path.join(data_dir, 'osm_industrial.geojson')),
        'protected': load_layer(os.path.join(data_dir, 'osm_protected.geojson')),
    }

    zones = add_osm_flags(zones, osm_layers)
    zones['osm_flags'] = zones['legal_flags'].apply(lambda flags: [flag for flag in flags if flag in [
        'AIRPORT_BUFFER_VIOLATION', 'RAILWAY_BUFFER_VIOLATION', 'RIVER_BUFFER_VIOLATION', 'PROTECTED_ZONE_VIOLATION', 'INDUSTRIAL_ZONE_ACTIVITY']])
    zones = calculate_final_score(zones)
    zones['legal_explanation'] = zones.apply(synthesize_explanation, axis=1)

    def derive_violation_type(row):
        if 'FOREST_ENCROACHMENT' in row['legal_flags']:
            return 'FOREST_ENCROACHMENT'
        if 'WETLAND_ENCROACHMENT' in row['legal_flags']:
            return 'WETLAND_ENCROACHMENT'
        if 'WATER_BODY_ENCROACHMENT' in row['legal_flags']:
            return 'WATER_BODY_ENCROACHMENT'
        if 'AGRICULTURAL_LAND_VIOLATION' in row['legal_flags']:
            return 'AGRICULTURAL_LAND'
        if 'PARK_ENCROACHMENT' in row['legal_flags']:
            return 'PARK_ENCROACHMENT'
        if 'PROTECTED_ZONE_VIOLATION' in row['legal_flags']:
            return 'PROTECTED_ZONE_VIOLATION'
        if 'AIRPORT_BUFFER_VIOLATION' in row['legal_flags']:
            return 'AIRPORT_BUFFER_VIOLATION'
        if 'RAILWAY_BUFFER_VIOLATION' in row['legal_flags']:
            return 'RAILWAY_BUFFER_VIOLATION'
        if 'RIVER_BUFFER_VIOLATION' in row['legal_flags']:
            return 'RIVER_BUFFER_VIOLATION'
        if 'INDUSTRIAL_ZONE_ACTIVITY' in row['legal_flags']:
            return 'INDUSTRIAL_ZONE_ACTIVITY'
        return row.get('violation_type', 'UNVERIFIED_ZONE')

    zones['violation_type'] = zones.apply(derive_violation_type, axis=1)

    if 'risk_score' not in zones.columns:
        zones['risk_score'] = 0.0

    if 'final_risk_score' not in zones.columns:
        zones = calculate_final_score(zones)

    out_dir = os.path.dirname(output_path)
    if out_dir and not os.path.exists(out_dir):
        os.makedirs(out_dir, exist_ok=True)

    zones.to_file(output_path, driver='GeoJSON')
    print(f'Saved legal cross reference output: {output_path}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Perform legal cross reference using Bhuvan and OSM layers.')
    parser.add_argument('new_construction', type=str, help='Detected construction GeoJSON input')
    parser.add_argument('output', type=str, help='Scored output GeoJSON path')
    parser.add_argument('--bhuvan', type=str, default='data/bhuvan_lulc.geojson', help='Bhuvan LULC GeoJSON path')
    parser.add_argument('--data-dir', type=str, default='data', help='Directory with OSM layer GeoJSON files')
    args = parser.parse_args()
    main(args.new_construction, args.output, args.bhuvan, args.data_dir)
