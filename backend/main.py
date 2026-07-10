from fastapi import FastAPI, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import subprocess
import sys
import os
import json
import uuid
import threading
import importlib.util
import numpy as np
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount(
    "/images",
    StaticFiles(directory=os.path.join(os.path.dirname(__file__), '..', 'data', 'images')),
    name="images"
)

DATA_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'flagged_zones.json')
LIVE_ZONES_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'live_zones.json')

VISION_DEFAULTS = {
    "construction_detected": False,
    "objects_found": [],
    "vision_confidence": 0.0,
    "crane_present": False,
    "building_present": False,
    "container_present": False,
}


def default_vision_fields():
    return {
        key: list(value) if isinstance(value, list) else value
        for key, value in VISION_DEFAULTS.items()
    }


def default_legal_fields():
    return {
        'bhuvan_land_type': 'unverified',
        'osm_flags': [],
        'legal_flags': [],
        'risk_boost_total': 0.0,
        'legal_explanation': ''
    }


def normalize_zone(zone):
    normalized = dict(zone)
    for key, value in default_vision_fields().items():
        normalized.setdefault(key, value)
    for key, value in default_legal_fields().items():
        normalized.setdefault(key, value)

    normalized["objects_found"] = list(normalized.get("objects_found") or [])
    normalized["vision_confidence"] = float(normalized.get("vision_confidence") or 0.0)
    for key in ["construction_detected", "crane_present", "building_present", "container_present"]:
        normalized[key] = bool(normalized.get(key, False))

    return _sanitize_obj(normalized)


def find_zone(zone_id: str):
    target = str(zone_id)
    for zone in get_combined_zones():
        if str(zone.get('id')) == target:
            return zone
    return None


def find_live_zone(zone_id: str):
    target = str(zone_id)
    for zone in persisted_live_zones:
        if str(zone.get('id')) == target:
            return zone, {"status": "done", "result": persisted_live_zones}
    for job in JOBS.values():
        result = job.get('result')
        if isinstance(result, list):
            for zone in result:
                if str(zone.get('id')) == target:
                    return zone, job
    return None, None


def _sanitize_obj(obj):
    try:
        import numpy as _np
        import pandas as _pd
        from shapely.geometry.base import BaseGeometry as _BaseGeometry
        from shapely.geometry import mapping as _mapping
    except Exception:
        _np = None
        _pd = None
        _BaseGeometry = None
        _mapping = None

    if obj is None:
        return None
    if _BaseGeometry is not None and isinstance(obj, _BaseGeometry):
        return _mapping(obj)
    if _np is not None and isinstance(obj, _np.generic):
        return obj.item()
    if _np is not None and isinstance(obj, _np.ndarray):
        return obj.tolist()
    if _pd is not None and hasattr(_pd, 'Series') and isinstance(obj, _pd.Series):
        return {k: _sanitize_obj(obj[k]) for k in obj.index}
    if isinstance(obj, dict):
        return {k: _sanitize_obj(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_obj(v) for v in obj]
    return obj


def _sanitize_job(job: dict):
    return {k: _sanitize_obj(v) for k, v in job.items()}


def load_generate_report_module():
    script_path = os.path.join(os.path.dirname(__file__), '..', 'notebooks', 'generate_report.py')
    spec = importlib.util.spec_from_file_location('generate_report', script_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


with open(DATA_PATH, encoding='utf-8') as f:
    flagged_zones = [normalize_zone(zone) for zone in json.load(f)]


def load_persisted_live_zones():
    if not os.path.exists(LIVE_ZONES_PATH):
        return []
    try:
        with open(LIVE_ZONES_PATH, encoding='utf-8') as f:
            data = json.load(f)
        return [normalize_zone(zone) for zone in data]
    except Exception as exc:
        print(f"Failed to load persisted live zones: {exc}")
        return []


persisted_live_zones = load_persisted_live_zones()


def get_combined_zones():
    return flagged_zones + persisted_live_zones


def save_live_zones(new_zones):
    existing = {str(zone.get('id')): zone for zone in persisted_live_zones}
    for zone in new_zones:
        existing[str(zone.get('id'))] = normalize_zone(zone)
    persisted_live_zones[:] = list(existing.values())
    with open(LIVE_ZONES_PATH, 'w', encoding='utf-8') as f:
        json.dump(_sanitize_obj(persisted_live_zones), f, ensure_ascii=False, indent=2)

# In-memory job store
JOBS = {}

# ─── Pre-computed data endpoints ───────────────────────────────────────────────

@app.get("/")
def root():
    return {"status": "AutoSentinel API running", "total_zones": len(get_combined_zones())}

@app.get("/zones")
def get_all_zones():
    zones = get_combined_zones()
    return {"zones": zones, "total": len(zones)}

@app.get("/zones/summary")
def get_summary():
    severity_counts = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}
    microsoft_confirmed = 0
    zones = get_combined_zones()
    for zone in zones:
        severity_counts[zone['severity']] += 1
        if zone.get('microsoft_confirmed'):
            microsoft_confirmed += 1
    latest_live = persisted_live_zones[-1] if persisted_live_zones else None
    return {
        "total": len(zones),
        "severity_breakdown": severity_counts,
        "microsoft_confirmed": microsoft_confirmed,
        "area": latest_live.get("area_label") if latest_live else "Vasai Virar, Maharashtra",
        "period": latest_live.get("period_label") if latest_live else "2019 vs 2023"
    }
@app.get("/zones/severity/{level}")
def get_by_severity(level: str):
    filtered = [z for z in get_combined_zones() if z['severity'] == level.upper()]
    return {"zones": filtered, "total": len(filtered)}

@app.get("/zones/{zone_id}/images")
def get_zone_images(zone_id: str):
    base = os.path.join(os.path.dirname(__file__), '..')
    before_path = os.path.join(base, 'data', 'images', f'zone_{zone_id}_before.png')
    after_path  = os.path.join(base, 'data', 'images', f'zone_{zone_id}_after.png')
    has_before = os.path.exists(before_path)
    has_after  = os.path.exists(after_path)
    return {
        "has_images": has_before and has_after,
        "before_url": f"http://localhost:8000/images/zone_{zone_id}_before.png" if has_before else None,
        "after_url":  f"http://localhost:8000/images/zone_{zone_id}_after.png"  if has_after  else None,
    }

@app.get("/zones/{zone_id}/report")
def get_zone_report(zone_id: str):  # changed int to str
    base = os.path.join(os.path.dirname(__file__), '..')
    report_path = os.path.join(base, 'data', f'report_zone_{zone_id}.pdf')

    zone = find_zone(zone_id)
    if zone is None:
        live_zone, live_job = find_live_zone(zone_id)
        if live_zone is None:
            return {"error": "Zone not found"}
        if live_job.get('status') != 'done':
            return {"error": "Live scan report unavailable until scan completes"}
        zone = live_zone

    module = load_generate_report_module()
    before_path = os.path.join(base, 'data', 'images', f'zone_{zone_id}_before.png')
    after_path = os.path.join(base, 'data', 'images', f'zone_{zone_id}_after.png')
    module.generate_report(
        zone,
        report_path,
        before_path=before_path,
        after_path=after_path,
    )

    if os.path.exists(report_path):
        return FileResponse(
            report_path,
            media_type='application/pdf',
            filename=f'autosentinel_report_zone_{zone_id}.pdf'
        )
    return {"error": "Report not found"}

@app.get("/zones/{zone_id}/vision")
def get_zone_vision(zone_id: str):
    zone = find_zone(zone_id)
    if not zone:
        return {"error": "Zone not found"}

    return {
        "objects_found": zone.get("objects_found", []),
        "vision_confidence": zone.get("vision_confidence", 0.0),
        "construction_detected": zone.get("construction_detected", False),
    }

@app.get("/zones/{zone_id}")
def get_zone(zone_id: str):
    zone = find_zone(zone_id)
    if zone:
        return zone
    return {"error": "Zone not found"}

# ─── Live scan endpoints ────────────────────────────────────────────────────────

@app.post("/scan")
async def scan_area(request: Request, background_tasks: BackgroundTasks):
    payload = await request.json()
    return create_scan_job(payload, background_tasks)

@app.get("/scan/{job_id}")
def get_scan_job(job_id: str):
    return get_job(job_id)

@app.post("/zones/query")
async def query_zones(request: Request, background_tasks: BackgroundTasks):
    """Called by frontend Get Data button — extracts bbox from drawn polygon and triggers live GEE scan"""
    payload = await request.json()

    # Extract geometry from GeoJSON
    if payload.get('type') == 'FeatureCollection':
        geom = payload['features'][0]['geometry']
    elif payload.get('type') == 'Feature':
        geom = payload['geometry']
    else:
        geom = payload.get('geometry') or payload

    # Get bounding box from polygon coordinates
    coords = geom['coordinates'][0]
    lons = [c[0] for c in coords]
    lats = [c[1] for c in coords]
    bbox = {
        'minx': min(lons),
        'miny': min(lats),
        'maxx': max(lons),
        'maxy': max(lats)
    }

    return create_scan_job(bbox, background_tasks)

@app.post("/process_bbox")
async def process_bbox(request: Request, background_tasks: BackgroundTasks):
    """Called by leaflet-draw rectangle tool"""
    bbox = await request.json()
    return create_scan_job(bbox, background_tasks)


def create_scan_job(bbox: dict, background_tasks: BackgroundTasks):
    job_id = str(uuid.uuid4())[:8]
    JOBS[job_id] = {
        "status": "processing",
        "progress": "Initializing satellite scan...",
        "result": None,
        "error": None
    }
    background_tasks.add_task(run_gee_pipeline, job_id, bbox)
    return {"job_id": job_id, "status": "processing"}

@app.get("/jobs/{job_id}")
def get_job(job_id: str):
    job = JOBS.get(job_id)
    if not job:
        return {"status": "error", "error": "Job not found"}
    return _sanitize_job(job)

def run_gee_pipeline(job_id: str, bbox: dict):
    print(f"[JOB {job_id}] Starting GEE pipeline for bbox: {bbox}")
    try:
        import ee
        import numpy as np
        from shapely.geometry import shape
        from rasterio.features import shapes
        import rasterio
        import requests as req
        import tempfile
        import geopandas as gpd
        import pandas as pd

        JOBS[job_id]["progress"] = "Connecting to Google Earth Engine..."
        ee.Initialize(project='ee-autosentinel')

        west = bbox.get('minx') or bbox.get('west')
        south = bbox.get('miny') or bbox.get('south')
        east = bbox.get('maxx') or bbox.get('east')
        north = bbox.get('maxy') or bbox.get('north')

        print(f"[JOB {job_id}] BBox: W={west} S={south} E={east} N={north}")
        region = ee.Geometry.Rectangle([west, south, east, north])

        JOBS[job_id]["progress"] = "Fetching 2024 satellite imagery..."
        before = (ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
            .filterBounds(region)
            .filterDate('2024-01-01', '2024-12-31')
            .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 20))
            .median()
            .clip(region))

        JOBS[job_id]["progress"] = "Fetching 2025 satellite imagery..."
        after = (ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
            .filterBounds(region)
            .filterDate('2025-01-01', '2025-12-31')
            .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 20))
            .median()
            .clip(region))

        JOBS[job_id]["progress"] = "Running NDBI change detection..."
        ndbi_before = before.normalizedDifference(['B11', 'B8'])
        ndbi_after = after.normalizedDifference(['B11', 'B8'])
        change = ndbi_after.subtract(ndbi_before)
        new_construction = change.gt(0.15)

        JOBS[job_id]["progress"] = "Downloading results from GEE..."
        url = new_construction.getDownloadURL({
            'scale': 10,
            'region': region,
            'format': 'GEO_TIFF',
            'bands': ['nd']
        })

        response = req.get(url, timeout=300)
        print(f"[JOB {job_id}] Downloaded {len(response.content)} bytes")

        with tempfile.NamedTemporaryFile(suffix='.tif', delete=False) as tmp:
            tmp.write(response.content)
            tmp_path = tmp.name

        JOBS[job_id]["progress"] = "Extracting flagged zones..."
        with rasterio.open(tmp_path) as src:
            image = src.read(1)
            transform = src.transform

        print(f"[JOB {job_id}] Image shape: {image.shape}, unique: {np.unique(image)}")

        mask = image == 1
        results = []
        for geom, val in shapes(image.astype(np.float32), mask=mask, transform=transform):
            if val == 1.0:
                s = shape(geom)
                area = s.area * 111320**2
                if area > 500:
                    results.append({'geometry': s, 'area_sqm': area})

        os.unlink(tmp_path)
        print(f"[JOB {job_id}] Found {len(results)} zones after filtering")

        # ── Severity + scoring ───────────────────────────────────────
        def get_severity(a):
            if a > 50000: return 'CRITICAL'
            elif a > 10000: return 'HIGH'
            elif a > 2000: return 'MEDIUM'
            else: return 'LOW'

        def get_score(a):
            if a > 50000: return 99.0
            elif a > 10000: return round(70 + (a - 10000) / 2000, 1)
            elif a > 2000: return round(40 + (a - 2000) / 200, 1)
            else: return round(10 + (a - 500) / 150, 1)

        action_map = {
            'CRITICAL': 'Immediate ground inspection required',
            'HIGH': 'Priority inspection within 48 hours',
            'MEDIUM': 'Schedule inspection',
            'LOW': 'Log for routine inspection'
        }

        # Build initial zones list
        zones = []
        area_label = f"Custom scanned area ({south:.4f}, {west:.4f}) to ({north:.4f}, {east:.4f})"
        for idx, r in enumerate(results):
            centroid = r['geometry'].centroid
            sev = get_severity(r['area_sqm'])
            zones.append({
                'id': f"live_{job_id}_{idx}",
                'lat': round(centroid.y, 6),
                'lon': round(centroid.x, 6),
                'area_sqm': round(r['area_sqm'], 1),
                'severity': sev,
                'risk_score': get_score(r['area_sqm']),
                'action': action_map[sev],
                'violation_type': 'UNVERIFIED_ZONE',
                'bhuvan_land_type': 'unverified',
                'osm_flags': [],
                'legal_flags': [],
                'risk_boost_total': 0.0,
                'legal_explanation': '',
                'microsoft_confirmed': False,
                'construction_detected': True,
                'vision_confidence': 0.0,
                'objects_found': [],
                'area_label': area_label,
                'period_label': '2024 vs 2025',
            })

        base_dir = os.path.join(os.path.dirname(__file__), '..')
        bhuvan_path = os.path.join(base_dir, 'data', 'bhuvan_lulc.geojson')
        osm_data_dir = os.path.join(base_dir, 'data')
        os.makedirs(os.path.join(base_dir, 'data'), exist_ok=True)

        JOBS[job_id]["progress"] = "Generating Bhuvan land-use layer..."
        try:
            subprocess.run([
                sys.executable,
                os.path.join(base_dir, 'notebooks', 'fetch_bhuvan_lulc.py'),
                    "--source", os.path.join(base_dir, 'data', 'zoned_violations_enriched.geojson'),
                '--output', bhuvan_path,
                '--bbox', str(west), str(south), str(east), str(north)
                
            ], check=True)
        except Exception as e:
            print(f"[JOB {job_id}] Bhuvan generation failed: {e}")
            JOBS[job_id]["progress"] = "Warning: Bhuvan generation failed, continuing with existing layer"

        JOBS[job_id]["progress"] = "Exporting OSM infrastructure layers..."
        try:
            subprocess.run([
                sys.executable,
                os.path.join(base_dir, 'notebooks', 'fetch_osm_layers.py'),
                '--output-dir', osm_data_dir,
                '--bbox', str(south), str(west), str(north), str(east)
            ], check=True)
        except Exception as e:
            print(f"[JOB {job_id}] OSM export failed: {e}")
            JOBS[job_id]["progress"] = "Warning: OSM export failed, continuing with existing layers"

        JOBS[job_id]["progress"] = "Applying Bhuvan and OSM legal scoring..."
        try:
            import tempfile
            import json
            import geopandas as gpd
            from shapely.geometry import Point as ShapelyPoint

            input_fd, input_path = tempfile.mkstemp(suffix='.geojson')
            output_fd, output_path = tempfile.mkstemp(suffix='.geojson')
            os.close(input_fd)
            os.close(output_fd)
            try:
                live_gdf = gpd.GeoDataFrame(
                    [{
                        'id': z['id'],
                        'area_sqm': z['area_sqm'],
                        'risk_score': z['risk_score'],
                        'severity': z['severity'],
                        'action': z['action'],
                        'violation_type': z['violation_type'],
                        'bhuvan_land_type': z['bhuvan_land_type'],
                        'osm_flags': z['osm_flags'],
                        'legal_flags': z['legal_flags'],
                        'risk_boost_total': z['risk_boost_total'],
                        'legal_explanation': z['legal_explanation'],
                        'microsoft_confirmed': z['microsoft_confirmed'],
                        'construction_detected': z['construction_detected'],
                        'vision_confidence': z['vision_confidence'],
                        'objects_found': z['objects_found'],
                    } for z in zones],
                    geometry=[r['geometry'] for r in results],
                    crs='EPSG:4326'
                )
                live_gdf.to_file(input_path, driver='GeoJSON')

                subprocess.run([
                    sys.executable,
                    os.path.join(base_dir, 'notebooks', 'legal_cross_reference.py'),
                    input_path,
                    output_path,
                    '--bhuvan', bhuvan_path,
                    '--data-dir', osm_data_dir
                ], check=True)

                enriched = gpd.read_file(output_path)
                if enriched.crs is None:
                    enriched = enriched.set_crs('EPSG:4326')
                # Compute centroids in a projected CRS for accurate results, then convert back to WGS84
                try:
                    centroids_proj = enriched.to_crs('EPSG:3857').geometry.centroid
                    centroids_wgs84 = gpd.GeoSeries(centroids_proj, crs='EPSG:3857').to_crs('EPSG:4326')
                    enriched['lat'] = centroids_wgs84.y
                    enriched['lon'] = centroids_wgs84.x
                except Exception:
                    # Fallback to simple centroid (best-effort)
                    enriched = enriched.to_crs('EPSG:4326')
                    enriched['lat'] = enriched.geometry.centroid.y
                    enriched['lon'] = enriched.geometry.centroid.x
                zones = []
                for _, row in enriched.iterrows():
                    zones.append({
                        'id': row['id'],
                        'lat': round(float(row['lat']), 6),
                        'lon': round(float(row['lon']), 6),
                        'area_sqm': float(row['area_sqm']),
                        'severity': row['severity'],
                        'risk_score': float(row.get('final_risk_score', row['risk_score'])),
                        'action': row['action'],
                        'violation_type': row.get('violation_type', 'UNVERIFIED_ZONE'),
                        'bhuvan_land_type': row.get('bhuvan_land_type', 'unverified'),
                        'osm_flags': _sanitize_obj(row.get('osm_flags', [])) or [],
                        'legal_flags': _sanitize_obj(row.get('legal_flags', [])) or [],
                        'risk_boost_total': float(row.get('risk_boost_total', 0)),
                        'legal_explanation': row.get('legal_explanation', ''),
                        'microsoft_confirmed': bool(row.get('microsoft_confirmed', False)),
                        'construction_detected': bool(row.get('construction_detected', False)),
                        'vision_confidence': float(row.get('vision_confidence', 0.0)),
                        'objects_found': row.get('objects_found', []) if isinstance(row.get('objects_found', []), list) else [],
                        'area_label': area_label,
                        'period_label': '2024 vs 2025',
                    })
            finally:
                try:
                    os.unlink(input_path)
                except Exception:
                    pass
                try:
                    os.unlink(output_path)
                except Exception:
                    pass
        except Exception as e:
            print(f"[JOB {job_id}] Legal scoring failed: {e}")
            JOBS[job_id]["progress"] = "Live scan completed, legal scoring unavailable"

        # ── Microsoft building cross-reference ───────────────────────
        JOBS[job_id]["progress"] = "Cross-referencing Microsoft buildings..."
        try:
            from shapely.geometry import Point as ShapelyPoint

            def lat_lon_to_quadkey(lat, lon, zoom=9):
                import math
                lat_rad = math.radians(lat)
                n = 2 ** zoom
                x = int((lon + 180) / 360 * n)
                y = int((1 - math.log(math.tan(lat_rad) + 1/math.cos(lat_rad)) / math.pi) / 2 * n)
                quadkey = ''
                for i in range(zoom, 0, -1):
                    digit = 0
                    mask = 1 << (i - 1)
                    if x & mask: digit += 1
                    if y & mask: digit += 2
                    quadkey += str(digit)
                return quadkey

            center_lat = (north + south) / 2
            center_lon = (east + west) / 2
            quadkey = lat_lon_to_quadkey(center_lat, center_lon, zoom=9)
            print(f"[JOB {job_id}] Microsoft quadkey: {quadkey}")

            ms_df = pd.read_csv(
                'https://minedbuildings.z5.web.core.windows.net/global-buildings/dataset-links.csv'
            )
            matches = ms_df[ms_df['Url'].str.contains(f'quadkey={quadkey}', na=False)]

            if len(matches) > 0:
                import gzip
                import io
                import json as json_lib

                tile_url = matches.iloc[0]['Url']
                r = req.get(tile_url, timeout=120)

                buildings = []
                with gzip.open(io.BytesIO(r.content), 'rt') as f:
                    for line in f:
                        try:
                            obj = json_lib.loads(line)
                            coords = obj['geometry']['coordinates'][0][0]
                            lon_b, lat_b = coords[0], coords[1]
                            if west <= lon_b <= east and south <= lat_b <= north:
                                buildings.append(shape(obj['geometry']))
                        except Exception:
                            continue

                print(f"[JOB {job_id}] Microsoft buildings in area: {len(buildings)}")

                if buildings:
                    ms_gdf = gpd.GeoDataFrame(
                        geometry=buildings, crs='EPSG:4326'
                    )
                    zone_points = gpd.GeoDataFrame(
                        zones,
                        geometry=[ShapelyPoint(z['lon'], z['lat']) for z in zones],
                        crs='EPSG:4326'
                    )
                    ms_joined = gpd.sjoin(
                        zone_points.reset_index(drop=True),
                        ms_gdf.reset_index(drop=True),
                        how='left',
                        predicate='within'
                    )
                    ms_joined = ms_joined[~ms_joined.index.duplicated(keep='first')]

                    confirmed_count = 0
                    # DEBUG
                    print(f"[JOB {job_id}] Zones before boost: {[z['risk_score'] for z in zones[:3]]}")
                    print(f"[JOB {job_id}] Joined rows: {len(ms_joined)}")
                    print(f"[JOB {job_id}] Violation types: {ms_joined['violation_type'].value_counts().to_dict()}")
                    for i, zone in enumerate(zones):
                        if i >= len(ms_joined):
                            continue

                        row = ms_joined.iloc[i]
                        ms_match = pd.notna(row.get('index_right'))
                        print(f"[JOB {job_id}] Zone {i}: microsoft_match={ms_match}")

                        if ms_match:
                            zone['microsoft_confirmed'] = True
                            confirmed_count += 1

                    print(f"[JOB {job_id}] Zones after boost: {[z['risk_score'] for z in zones[:3]]}")
                    print(f"[JOB {job_id}] Microsoft confirmed: {confirmed_count}/{len(zones)}")

        except Exception as ms_err:
            print(f"[JOB {job_id}] Microsoft cross-ref skipped: {ms_err}")

        # ── Final sort and complete ──────────────────────────────────
        zones.sort(key=lambda x: x['risk_score'], reverse=True)

        zones = [normalize_zone(zone) for zone in zones]

        JOBS[job_id]["status"] = "done"
        JOBS[job_id]["progress"] = f"Scan complete — {len(zones)} zones found"
        JOBS[job_id]["result"] = zones
        save_live_zones(zones)
        print(f"[JOB {job_id}] Complete — {len(zones)} zones")

    except Exception as e:
        import traceback
        print(f"[JOB {job_id}] ERROR: {e}")
        traceback.print_exc()
        JOBS[job_id]["status"] = "error"
        JOBS[job_id]["error"] = str(e)
        JOBS[job_id]["progress"] = f"Failed: {str(e)}"


@app.get("/zones/{zone_id}/live-images")
async def get_live_images(zone_id: str, lat: float, lon: float, background_tasks: BackgroundTasks):
    """Fetch before/after satellite thumbnail for any coordinate on demand"""
    
    # Check if already cached
    safe_id = ''.join(ch if ch.isalnum() or ch in ('-', '_') else '_' for ch in str(zone_id))
    before_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'images', f'zone_{safe_id}_before.png')
    after_path  = os.path.join(os.path.dirname(__file__), '..', 'data', 'images', f'zone_{safe_id}_after.png')
    
    def valid_cached_image(path):
        return os.path.exists(path) and os.path.getsize(path) > 1024

    if valid_cached_image(before_path) and valid_cached_image(after_path):
        return {
            "has_images": True,
            "before_url": f"http://localhost:8000/images/zone_{safe_id}_before.png",
            "after_url":  f"http://localhost:8000/images/zone_{safe_id}_after.png"
        }
    
    # Fetch from GEE
    try:
        import ee
        import requests as req

        ee.Initialize(project='ee-autosentinel')

        region = ee.Geometry.Rectangle([
            lon - 0.008, lat - 0.008,
            lon + 0.008, lat + 0.008
        ])

        before = (ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
            .filterBounds(region)
            .filterDate('2024-01-01', '2024-12-31')
            .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 20))
            .median()
            .clip(region))

        after = (ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
            .filterBounds(region)
            .filterDate('2025-01-01', '2025-12-31')
            .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 20))
            .median()
            .clip(region))

        viz = {'bands': ['B4', 'B3', 'B2'], 'min': 0, 'max': 3000, 'dimensions': 512, 'region': region}

        before_url = before.getThumbURL(viz)
        after_url  = after.getThumbURL(viz)

        # Download and cache
        for url, path in [(before_url, before_path), (after_url, after_path)]:
            r = req.get(url, timeout=60)
            content_type = r.headers.get('content-type', '')
            if r.status_code != 200 or 'image' not in content_type.lower() or len(r.content) < 1024:
                raise RuntimeError(f"Satellite thumbnail request failed for {safe_id}")
            with open(path, 'wb') as f:
                f.write(r.content)

        return {
            "has_images": True,
            "before_url": f"http://localhost:8000/images/zone_{safe_id}_before.png",
            "after_url":  f"http://localhost:8000/images/zone_{safe_id}_after.png"
        }

    except Exception as e:
        return {"has_images": False, "error": str(e)}
