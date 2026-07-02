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

# Load pre-computed Vasai Virar data
DATA_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'flagged_zones.json')
with open(DATA_PATH) as f:
    flagged_zones = json.load(f)

# In-memory job store
JOBS = {}
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIVE_ZONE_REPORTS_PATH = os.path.join(BASE_DIR, 'data', 'live_zone_reports.json')

if os.path.exists(LIVE_ZONE_REPORTS_PATH):
    with open(LIVE_ZONE_REPORTS_PATH) as f:
        LIVE_ZONE_REPORTS = json.load(f)
else:
    LIVE_ZONE_REPORTS = {}


def save_live_zone_reports():
    with open(LIVE_ZONE_REPORTS_PATH, 'w') as f:
        json.dump(LIVE_ZONE_REPORTS, f, indent=2)

# ─── Pre-computed data endpoints ───────────────────────────────────────────────

@app.get("/")
def root():
    return {"status": "AutoSentinel API running", "total_zones": len(flagged_zones)}

@app.get("/zones")
def get_all_zones():
    return {"zones": flagged_zones, "total": len(flagged_zones)}

@app.get("/zones/summary")
def get_summary():
    severity_counts = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}
    for zone in flagged_zones:
        severity_counts[zone['severity']] += 1
    return {
        "total": len(flagged_zones),
        "severity_breakdown": severity_counts,
        "area": "Vasai Virar, Maharashtra",
        "period": "2019 vs 2023"
    }

@app.get("/zones/severity/{level}")
def get_by_severity(level: str):
    filtered = [z for z in flagged_zones if z['severity'] == level.upper()]
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
    report_path = os.path.join(
        os.path.dirname(__file__), '..', 'data', f'report_zone_{zone_id}.pdf'
    )

    if not os.path.exists(report_path):
        script_path = os.path.join(
            os.path.dirname(__file__), '..', 'notebooks', 'generate_report.py'
        )
        try:
            int_id = int(zone_id)
            subprocess.run([sys.executable, script_path, str(int_id)], check=True)
        except ValueError:
            zone_payload = LIVE_ZONE_REPORTS.get(str(zone_id))
            if zone_payload:
                subprocess.run([
                    sys.executable,
                    script_path,
                    str(zone_id),
                    json.dumps(zone_payload)
                ], check=True)
            else:
                return {"error": "Report generation for live scan zones coming soon"}

    if os.path.exists(report_path):
        return FileResponse(
            report_path,
            media_type='application/pdf',
            filename=f'autosentinel_report_zone_{zone_id}.pdf'
        )
    return {"error": "Report not found"}

@app.get("/zones/{zone_id}")
def get_zone(zone_id: str):
    for zone in flagged_zones:
        if zone['id'] == zone_id:
            return zone
    return {"error": "Zone not found"}

# ─── Live scan endpoints ────────────────────────────────────────────────────────

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

    job_id = str(uuid.uuid4())[:8]
    JOBS[job_id] = {
        "status": "processing",
        "progress": "Initializing satellite scan...",
        "result": None,
        "error": None
    }

    background_tasks.add_task(run_gee_pipeline, job_id, bbox)
    return {"job_id": job_id, "status": "processing", "zones": []}

@app.post("/process_bbox")
async def process_bbox(request: Request, background_tasks: BackgroundTasks):
    """Called by leaflet-draw rectangle tool"""
    bbox = await request.json()
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
    return job

# ─── GEE Pipeline ──────────────────────────────────────────────────────────────

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

        JOBS[job_id]["progress"] = "Connecting to Google Earth Engine..."
        ee.Initialize(project='ee-autosentinel')

        # Support both bbox formats
        west  = bbox.get('minx') or bbox.get('west')
        south = bbox.get('miny') or bbox.get('south')
        east  = bbox.get('maxx') or bbox.get('east')
        north = bbox.get('maxy') or bbox.get('north')

        print(f"[JOB {job_id}] BBox: W={west} S={south} E={east} N={north}")
        region = ee.Geometry.Rectangle([west, south, east, north])

        JOBS[job_id]["progress"] = "Fetching 2019 satellite imagery..."
        before = (ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
            .filterBounds(region)
            .filterDate('2019-01-01', '2019-12-31')
            .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 20))
            .median()
            .clip(region))

        JOBS[job_id]["progress"] = "Fetching 2023 satellite imagery..."
        after = (ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
            .filterBounds(region)
            .filterDate('2023-01-01', '2023-12-31')
            .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 20))
            .median()
            .clip(region))

        JOBS[job_id]["progress"] = "Running NDBI change detection..."
        ndbi_before = before.normalizedDifference(['B11', 'B8'])
        ndbi_after  = after.normalizedDifference(['B11', 'B8'])
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

        print(f"[JOB {job_id}] Image shape: {image.shape}, unique values: {np.unique(image)}")

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

        zones = []
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
                'violation_type': 'LIVE_SCAN_RESULT'
            })

        zones.sort(key=lambda x: x['risk_score'], reverse=True)

        for zone in zones:
            LIVE_ZONE_REPORTS[str(zone['id'])] = zone
        save_live_zone_reports()

        JOBS[job_id]["status"] = "done"
        JOBS[job_id]["progress"] = f"Scan complete — {len(zones)} zones found"
        JOBS[job_id]["result"] = zones
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
    safe_id = str(zone_id).replace('/', '_')
    before_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'images', f'zone_{safe_id}_before.png')
    after_path  = os.path.join(os.path.dirname(__file__), '..', 'data', 'images', f'zone_{safe_id}_after.png')
    
    if os.path.exists(before_path) and os.path.exists(after_path):
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
            .filterDate('2019-01-01', '2019-12-31')
            .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 20))
            .median())

        after = (ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
            .filterBounds(region)
            .filterDate('2023-01-01', '2023-12-31')
            .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 20))
            .median())

        viz = {'bands': ['B4', 'B3', 'B2'], 'min': 0, 'max': 3000, 'dimensions': 512, 'region': region}

        before_url = before.getThumbURL(viz)
        after_url  = after.getThumbURL(viz)

        # Download and cache
        for url, path in [(before_url, before_path), (after_url, after_path)]:
            r = req.get(url, timeout=60)
            with open(path, 'wb') as f:
                f.write(r.content)

        return {
            "has_images": True,
            "before_url": f"http://localhost:8000/images/zone_{safe_id}_before.png",
            "after_url":  f"http://localhost:8000/images/zone_{safe_id}_after.png"
        }

    except Exception as e:
        return {"has_images": False, "error": str(e)}