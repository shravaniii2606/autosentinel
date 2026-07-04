#!/usr/bin/env python3
import argparse
import os
import time
import requests
import geopandas as gpd
from shapely.geometry import Point, LineString, Polygon


def element_to_geometry(el):
    if el['type'] == 'node':
        return Point(el['lon'], el['lat'])
    coords = [(pt['lon'], pt['lat']) for pt in el.get('geometry', [])]
    if len(coords) < 2:
        return None
    if coords[0] == coords[-1] and len(coords) >= 4:
        return Polygon(coords)
    return LineString(coords)


def overpass_query(bbox, query_parts):
    south, west, north, east = bbox
    query_parts = [part.format(south=south, west=west, north=north, east=east) for part in query_parts]
    query = '[out:json][timeout:60];(' + ';'.join(query_parts) + ';);out geom;'
    headers = {
        'User-Agent': 'AutoSentinel/1.0 (https://github.com/autosentinel)',
        'Accept': 'application/json'
    }
    urls = [
        'https://overpass.openstreetmap.fr/api/interpreter',
        'https://overpass.kumi.systems/api/interpreter',
        'https://overpass-api.de/api/interpreter',
        'https://lz4.overpass-api.de/api/interpreter'
    ]

    last_exc = None
    for url in urls:
        for attempt in range(2):
            response = None
            try:
                response = requests.post(url, data={'data': query}, headers=headers, timeout=120)
                if response.status_code == 406:
                    print(f'Overpass 406 from {url}, trying next endpoint')
                    break
                if response.status_code in (429, 503, 504):
                    print(f'Overpass {response.status_code} from {url}; trying next endpoint')
                    break
                response.raise_for_status()
                return response.json()
            except Exception as exc:
                last_exc = exc
                print(f'Overpass query failed on {url} attempt {attempt + 1}: {exc}')
                if response is not None and hasattr(response, 'text'):
                    print(response.text[:800])
                if response is None or response.status_code not in (429, 503, 504):
                    break
        print(f'Moving to next Overpass endpoint after {url}')
    raise last_exc


def fetch_osm_layer(bbox, query_parts, fallback_name):
    try:
        osm_json = overpass_query(bbox, query_parts)
        return osm_to_gdf(osm_json)
    except Exception as exc:
        print(f'Failed to fetch {fallback_name}: {exc}')
        return gpd.GeoDataFrame(columns=['geometry'], geometry='geometry', crs='EPSG:4326')


def osm_to_gdf(osm_json):
    rows = []
    for el in osm_json.get('elements', []):
        geom = element_to_geometry(el)
        if geom is None:
            continue
        props = el.get('tags', {}) or {}
        props['osm_id'] = el.get('id')
        props['osm_type'] = el.get('type')
        rows.append({**props, 'geometry': geom})
    if not rows:
        return gpd.GeoDataFrame(columns=['geometry'], geometry='geometry', crs='EPSG:4326')
    return gpd.GeoDataFrame(rows, geometry='geometry', crs='EPSG:4326')


def save_layer(gdf, path, name):
    if gdf is None or gdf.empty:
        print(f'No features for {name}, saving empty layer.')
        gdf = gpd.GeoDataFrame(columns=['geometry'], geometry='geometry', crs='EPSG:4326')
    else:
        gdf = gdf.to_crs('EPSG:4326')
    os.makedirs(os.path.dirname(path), exist_ok=True)
    gdf.to_file(path, driver='GeoJSON')
    print(f'Saved {name} layer to {path} ({len(gdf)} features)')


def main(output_dir, bbox):
    if bbox is None:
        bbox = (19.35, 72.80, 19.50, 72.95)

    print('Fetching airports...')
    airports = fetch_osm_layer(
        bbox,
        ['node["aeroway"="aerodrome"]({south},{west},{north},{east})',
         'way["aeroway"="aerodrome"]({south},{west},{north},{east})',
         'relation["aeroway"="aerodrome"]({south},{west},{north},{east})'],
        'airports'
    )
    save_layer(airports, os.path.join(output_dir, 'osm_airports.geojson'), 'airports')

    print('Fetching railways...')
    railways = fetch_osm_layer(
        bbox,
        ['way["railway"]({south},{west},{north},{east})',
         'relation["railway"]({south},{west},{north},{east})'],
        'railways'
    )
    save_layer(railways, os.path.join(output_dir, 'osm_railways.geojson'), 'railways')

    print('Fetching rivers...')
    rivers = fetch_osm_layer(
        bbox,
        ['way["waterway"~"river|stream|canal"]({south},{west},{north},{east})',
         'relation["waterway"~"river|stream|canal"]({south},{west},{north},{east})'],
        'rivers'
    )
    save_layer(rivers, os.path.join(output_dir, 'osm_rivers.geojson'), 'rivers')

    print('Fetching industrial zones...')
    industrial = fetch_osm_layer(
        bbox,
        ['way["landuse"~"industrial|industrial_area"]({south},{west},{north},{east})',
         'relation["landuse"~"industrial|industrial_area"]({south},{west},{north},{east})'],
        'industrial zones'
    )
    save_layer(industrial, os.path.join(output_dir, 'osm_industrial.geojson'), 'industrial zones')

    print('Fetching protected areas...')
    protected = fetch_osm_layer(
        bbox,
        ['way["boundary"="protected_area"]({south},{west},{north},{east})',
         'relation["boundary"="protected_area"]({south},{west},{north},{east})'],
        'protected areas'
    )
    save_layer(protected, os.path.join(output_dir, 'osm_protected.geojson'), 'protected areas')

    print('OSM layer export complete.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Fetch OSM infrastructure layers for Vasai-Virar.')
    parser.add_argument('--output-dir', type=str, default='data', help='Directory to store OSM GeoJSON layers.')
    parser.add_argument('--bbox', nargs=4, type=float, metavar=('SOUTH', 'WEST', 'NORTH', 'EAST'), help='Optional bbox to limit the OSM query.')
    args = parser.parse_args()
    main(args.output_dir, tuple(args.bbox) if args.bbox else None)
