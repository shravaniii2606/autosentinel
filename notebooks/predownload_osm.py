import osmnx as ox
import geopandas as gpd
import warnings
warnings.filterwarnings('ignore')

ox.settings.max_query_area_size = 999999999999
ox.settings.timeout = 60
# Use alternative Overpass endpoints
ox.settings.overpass_url = "https://overpass.openstreetmap.ru/api/interpreter"

north, south, east, west = 19.50, 19.35, 72.95, 72.80

layers = [
    ({'natural': ['wood', 'scrub'], 'landuse': ['forest']}, 'FOREST_ENCROACHMENT', 'data/osm_forest.geojson'),
    ({'natural': ['wetland', 'water']}, 'WETLAND_ENCROACHMENT', 'data/osm_wetland.geojson'),
    ({'landuse': ['farmland', 'farm', 'orchard']}, 'AGRICULTURAL_LAND', 'data/osm_agricultural.geojson'),
]

for tags, violation, output in layers:
    print(f"Fetching {violation}...")
    try:
        gdf = ox.features_from_bbox(bbox=(north, south, east, west), tags=tags)
        gdf = gdf[['geometry']].copy().to_crs('EPSG:4326')
        gdf['violation_type'] = violation
        gdf.to_file(output, driver='GeoJSON')
        print(f"Saved {len(gdf)} features to {output}")
    except Exception as e:
        print(f"Failed: {e}")
        gpd.GeoDataFrame(
            columns=['geometry', 'violation_type']
        ).to_file(output, driver='GeoJSON')
        print(f"Saved empty file to {output}")