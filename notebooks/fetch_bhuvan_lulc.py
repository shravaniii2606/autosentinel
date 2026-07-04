#!/usr/bin/env python3
import argparse
import os
import geopandas as gpd
from shapely.geometry import box


def normalize_land_type(value):
    text = str(value or '').strip().lower()
    if not text:
        return 'unverified'
    if any(term in text for term in ['forest', 'woodland', 'tree', 'jungle', 'wood']):
        return 'forest'
    if any(term in text for term in ['wetland', 'marsh', 'swamp', 'bog', 'fen', 'lake', 'pond', 'river', 'stream', 'reservoir', 'canal', 'waterbody', 'water body', 'water']):
        return 'waterbody'
    if any(term in text for term in ['agricult', 'farmland', 'farm', 'crop', 'paddy', 'field']):
        return 'agriculture'
    if any(term in text for term in ['built-up', 'builtup', 'built up', 'urban', 'settlement', 'residential', 'commercial']):
        return 'built-up'
    if any(term in text for term in ['barren', 'waste', 'rock', 'sand', 'desert', 'scrub']):
        return 'barren'
    return 'unverified'


def extract_land_type(row):
    fields = ['land_type', 'landuse', 'natural', 'class', 'label', 'category', 'type', 'lulc', 'land_cover']
    candidates = []
    for field in fields:
        if field in row and row[field] not in [None, '']:
            candidates.append(str(row[field]))
    return normalize_land_type(' '.join(candidates))


def polygonize_geometries(gdf):
    gdf = gdf[gdf.geometry.notna()].copy()
    if not gdf.empty:
        gdf['geometry'] = gdf.geometry.buffer(0)
        gdf = gdf[gdf.geometry.type.isin(['Polygon', 'MultiPolygon'])]
    return gdf


def main(source, output, bbox):
    default_source = os.path.join('data', 'zoned_violations_enriched.geojson')
    if source is None:
        source = default_source if os.path.exists(default_source) else None

    if source is None:
        raise ValueError('A source path or URL is required for Bhuvan LULC data. Use --source or provide data/zoned_violations_enriched.geojson.')

    if source.startswith(('http://', 'https://')) or os.path.exists(source):
        gdf = gpd.read_file(source)
    else:
        raise FileNotFoundError(f'Bhuvan source not found: {source}')

    if gdf.crs is None:
        gdf = gdf.set_crs('EPSG:4326')
    else:
        gdf = gdf.to_crs('EPSG:4326')

    if bbox is not None:
        minx, miny, maxx, maxy = bbox
        bbox_poly = gpd.GeoDataFrame(
            geometry=[box(minx, miny, maxx, maxy)],
            crs='EPSG:4326'
        )
        gdf = gdf[gdf.intersects(bbox_poly.geometry.iloc[0])]

    if gdf.empty:
        raise RuntimeError('Loaded Bhuvan LULC source contains no features after filtering.')

    gdf = gdf.copy()
    gdf['land_type'] = gdf.apply(extract_land_type, axis=1)
    gdf = gdf[['land_type', 'geometry']].copy()
    gdf = polygonize_geometries(gdf)
    if gdf.empty:
        raise RuntimeError('No polygonal land-use features were retained after normalization.')

    os.makedirs(os.path.dirname(output), exist_ok=True)
    gdf[['land_type', 'geometry']].to_file(output, driver='GeoJSON')
    print(f'Saved Bhuvan LULC to {output} ({len(gdf)} features)')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Fetch and normalize ISRO Bhuvan LULC layers for Vasai-Virar.')
    parser.add_argument('--source', type=str, default=None, help='Local file path or WFS/GeoJSON URL for Bhuvan LULC source.')
    parser.add_argument('--output', type=str, default='data/bhuvan_lulc.geojson', help='Output GeoJSON path.')
    parser.add_argument('--bbox', nargs=4, type=float, metavar=('MINX', 'MINY', 'MAXX', 'MAXY'), help='Optional bbox to crop the input data.')
    args = parser.parse_args()
    main(args.source, args.output, args.bbox)
