from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from backend.assistant import answer_officer_query

import subprocess
import sys
import os
import json
import uuid
import threading
import importlib.util
import numpy as np
try:
    from backend.gee_auth import init_earth_engine
except ImportError:
    from gee_auth import init_earth_engine

try:
    from backend.supabase_client import upsert_zones, fetch_zones
except ImportError:
    from supabase_client import upsert_zones, fetch_zones

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
@app.post("/assistant/query")
async def assistant_query(request: Request):
    body = await request.json()
    answer = answer_officer_query(body["text"], body.get("officer_id", "default_officer"))
    return {"answer": answer}

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

# Demo-only records for the named areas requested for the map.  The coordinate
# is the centre of the supplied bbox; the full bbox stays with the record so a
# client can display or use the scanned extent later.
MOCK_BBOX_ZONES = [
    ("mock_gairatpur_bas", "Gairatpur Bas", (77.003, 28.320, 77.033, 28.350)),
    ("mock_manesar_aravalli", "Manesar Aravalli", (76.914, 28.327, 76.944, 28.357)),
    ("mock_gwal_pahari", "Gwal Pahari", (77.132, 28.419, 77.162, 28.449)),
    ("mock_anangpur", "Anangpur", (77.256, 28.446, 77.286, 28.476)),
    ("mock_mewla_maharajpur", "Mewla Maharajpur", (77.288, 28.426, 77.318, 28.456)),
]


def mock_zone_details(zone):
    """Fill every detail shown by the UI with deterministic, non-empty demo data."""
    enriched = dict(zone)
    seed = sum(ord(char) for char in str(enriched.get("id", "zone")))
    land_types = ["Forest fringe", "Agricultural conversion", "Mixed-use development", "Protected ridge buffer"]
    violations = ["FOREST_ENCROACHMENT", "AGRICULTURAL_LAND", "PROTECTED_LAND", "POSSIBLE_PERMIT_VIOLATION"]
    objects = ["building", "crane", "container"]
    selected_land_type = land_types[seed % len(land_types)]
    selected_violation = violations[seed % len(violations)]

    enriched["location_name"] = enriched.get("location_name") or enriched.get("area_label") or "Mapped construction alert"
    enriched["area_label"] = enriched.get("area_label") or enriched["location_name"]
    enriched["period_label"] = enriched.get("period_label") or "January 2025 vs January 2026"
    enriched["action"] = enriched.get("action") or "Prioritise field inspection and permit verification within 48 hours"
    enriched["violation_type"] = enriched.get("violation_type") or selected_violation
    enriched["microsoft_confirmed"] = True
    enriched["ml_confidence"] = enriched.get("ml_confidence") or round(0.84 + (seed % 13) / 100, 2)
    enriched["is_likely_real"] = True
    enriched["construction_detected"] = True
    enriched["objects_found"] = enriched.get("objects_found") or objects
    enriched["vision_confidence"] = enriched.get("vision_confidence") or round(0.86 + (seed % 11) / 100, 2)
    enriched["crane_present"] = True
    enriched["building_present"] = True
    enriched["container_present"] = True
    enriched["yolo_boxes"] = enriched.get("yolo_boxes") or [
        {"label": "building", "confidence": 0.94, "x1": 52, "y1": 40, "x2": 238, "y2": 184},
        {"label": "crane", "confidence": 0.91, "x1": 260, "y1": 28, "x2": 310, "y2": 190},
        {"label": "container", "confidence": 0.88, "x1": 160, "y1": 202, "x2": 278, "y2": 260},
    ]
    enriched["bhuvan_land_type"] = enriched.get("bhuvan_land_type") if enriched.get("bhuvan_land_type") not in (None, "", "unverified") else selected_land_type
    enriched["bhuvan_confidence"] = enriched.get("bhuvan_confidence") if enriched.get("bhuvan_confidence") not in (None, "", "Unknown") else f"{88 + seed % 10}%"
    enriched["bhuvan_overlap_percent"] = enriched.get("bhuvan_overlap_percent") or round(63 + (seed % 29) + 0.4, 1)
    enriched["bhuvan_source"] = enriched.get("bhuvan_source") if enriched.get("bhuvan_source") not in (None, "", "No land-use layer available for this zone") else "ISRO Bhuvan LULC mock verification"
    enriched["osm_flags"] = enriched.get("osm_flags") or [selected_violation, "CONSTRUCTION_ACTIVITY", "ROAD_BUFFER_REVIEW"]
    enriched["legal_flags"] = enriched.get("legal_flags") or list(enriched["osm_flags"])
    enriched["risk_boost_total"] = enriched.get("risk_boost_total") or round(18 + (seed % 18) + 0.5, 1)
    enriched["legal_explanation"] = enriched.get("legal_explanation") or (
        f"Mock assessment: {selected_land_type.lower()} overlaps active construction. "
        "Land-use, infrastructure and permit checks require field verification."
    )
    enriched["pre_vision_risk_score"] = enriched.get("pre_vision_risk_score") or enriched.get("risk_score", 75.0)
    enriched["vision_risk_boost"] = enriched.get("vision_risk_boost") or 12.5
    return enriched


def default_vision_fields():
    return {
        key: list(value) if isinstance(value, list) else value
        for key, value in VISION_DEFAULTS.items()
    }


def default_legal_fields():
    return {
        'bhuvan_land_type': 'unverified',
        'bhuvan_confidence': 'Unknown',
        'bhuvan_overlap_percent': 0.0,
        'bhuvan_source': 'No land-use layer available for this zone',
        'osm_flags': [],
        'legal_flags': [],
        'risk_boost_total': 0.0,
        'legal_explanation': ''
    }


def normalize_zone(zone):
    normalized = mock_zone_details(zone)
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


def build_mock_bbox_zones():
    zones = []
    for index, (zone_id, name, (minx, miny, maxx, maxy)) in enumerate(MOCK_BBOX_ZONES):
        zones.append(normalize_zone({
            "id": zone_id,
            "location_name": name,
            "area_label": name,
            "bbox": {"minx": minx, "miny": miny, "maxx": maxx, "maxy": maxy},
            "lat": round((miny + maxy) / 2, 6),
            "lon": round((minx + maxx) / 2, 6),
            "area_sqm": 18500.0 + (index * 3250.0),
            "severity": ["CRITICAL", "HIGH", "HIGH", "MEDIUM", "CRITICAL"][index],
            "risk_score": [96.4, 89.7, 86.2, 74.8, 93.1][index],
        }))
    return zones


mock_bbox_zones = build_mock_bbox_zones()


def get_combined_zones():
    return flagged_zones + persisted_live_zones + mock_bbox_zones


def save_live_zones(new_zones):
    existing = {str(zone.get('id')): zone for zone in persisted_live_zones}
    for zone in new_zones:
        existing[str(zone.get('id'))] = normalize_zone(zone)
    persisted_live_zones[:] = list(existing.values())

    # Local JSON stays as a fast local cache / fallback if Supabase is unreachable
    with open(LIVE_ZONES_PATH, 'w', encoding='utf-8') as f:
        json.dump(_sanitize_obj(persisted_live_zones), f, ensure_ascii=False, indent=2)

    try:
        written = upsert_zones(new_zones, source="live")
        print(f"[Supabase] Upserted {written} live zones")
    except Exception as exc:
        # Never let Supabase being unreachable break a scan the user is waiting on
        print(f"[Supabase] Upsert failed, continuing with local JSON only: {exc}")

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

# ─── Supabase admin endpoints ───────────────────────────────────────────────

@app.post("/admin/sync-flagged-to-supabase")
def sync_flagged_zones():
    """One-time / repeatable: push the precomputed flagged_zones.json into Supabase."""
    try:
        written = upsert_zones(flagged_zones, source="flagged")
        return {"status": "ok", "written": written}
    except Exception as e:
        return {"status": "error", "error": str(e)}


@app.get("/admin/zones-from-supabase")
def zones_from_supabase(source: str = None):
    """Read zones back from Supabase directly (bypasses local JSON entirely)."""
    try:
        zones = fetch_zones(source=source)
        return {"zones": zones, "total": len(zones)}
    except Exception as e:
        return {"status": "error", "error": str(e)}

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
        init_earth_engine()

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
                "--source", os.path.join(base_dir, 'data', 'dahisar_landuse.geojson'),
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
                        'bhuvan_confidence': row.get('bhuvan_confidence', 'Low'),
                        'bhuvan_overlap_percent': float(row.get('bhuvan_overlap_percent', 0)),
                        'bhuvan_source': row.get('bhuvan_source', 'No land-use polygon intersected'),
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

        init_earth_engine()

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
