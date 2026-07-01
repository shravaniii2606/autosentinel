from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi import Request
from pydantic import BaseModel
import subprocess
import sys
import os
import json
import os
import uuid
import threading
import time

app = FastAPI()
app.mount("/images", StaticFiles(directory=os.path.join(os.path.dirname(__file__), '..', 'data', 'images')), name="images")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Load flagged zones data
DATA_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'flagged_zones.json')


with open(DATA_PATH) as f:
    flagged_zones = json.load(f)

    # Simple in-memory job tracker
    JOBS = {}


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

@app.get("/zones/{zone_id}")
def get_zone(zone_id: int):
    for zone in flagged_zones:
        if zone['id'] == zone_id:
            return zone
    return {"error": "Zone not found"}

@app.get("/zones/severity/{level}")
def get_by_severity(level: str):
    filtered = [z for z in flagged_zones if z['severity'] == level.upper()]
    return {"zones": filtered, "total": len(filtered)}


class GeoJSONFeature(BaseModel):
    type: str
    geometry: dict


@app.post('/zones/query')
async def query_zones(request: Request):
    payload = await request.json()
    # Accept either a Feature or FeatureCollection or raw geometry
    geom = None
    if 'type' in payload and payload.get('type') == 'FeatureCollection':
        # take first feature
        features = payload.get('features', [])
        if not features:
            return {'zones': [], 'total': 0}
        geom = features[0].get('geometry')
    elif payload.get('type') == 'Feature':
        geom = payload.get('geometry')
    elif payload.get('coordinates'):
        geom = payload
    else:
        # try nested
        geom = payload.get('geometry') or payload

    if geom is None:
        return {'zones': [], 'total': 0}

    try:
        from shapely.geometry import shape, Point
    except Exception as e:
        return {'error': 'shapely not available', 'detail': str(e)}

    poly = shape(geom)
    results = []
    for z in flagged_zones:
        pt = Point(z['lon'], z['lat'])
        if poly.contains(pt):
            results.append(z)
    return {'zones': results, 'total': len(results)}
@app.get("/zones/{zone_id}/images")
def get_zone_images(zone_id: int):
    before = f"data/images/zone_{zone_id}_before.png"
    after = f"data/images/zone_{zone_id}_after.png"
    has_before = os.path.exists(os.path.join(os.path.dirname(__file__), '..', before))
    has_after = os.path.exists(os.path.join(os.path.dirname(__file__), '..', after))
    return {
        "has_images": has_before and has_after,
        "before_url": f"http://localhost:8000/images/zone_{zone_id}_before.png" if has_before else None,
        "after_url": f"http://localhost:8000/images/zone_{zone_id}_after.png" if has_after else None,
    }
@app.get("/zones/{zone_id}/report")
def get_zone_report(zone_id: int):
    report_path = os.path.join(
        os.path.dirname(__file__), '..', 'data', f'report_zone_{zone_id}.pdf'
    )
    
    # If report doesn't exist yet, generate it
    if not os.path.exists(report_path):
        script_path = os.path.join(
            os.path.dirname(__file__), '..', 'notebooks', 'generate_report.py'
        )
        subprocess.run([sys.executable, script_path, str(zone_id)], check=True)
    
    if os.path.exists(report_path):
        return FileResponse(
            report_path,
            media_type='application/pdf',
            filename=f'autosentinel_report_zone_{zone_id}.pdf'
        )
    return {"error": "Report generation failed"}


class BBox(BaseModel):
    minx: float
    miny: float
    maxx: float
    maxy: float


def _run_pipeline(job_id, bbox):
    job_dir = os.path.join(os.path.dirname(__file__), '..', 'data', 'jobs', job_id)
    os.makedirs(job_dir, exist_ok=True)
    try:
        cmd = [sys.executable, os.path.join(os.path.dirname(__file__), '..', 'notebooks', 'run_pipeline.py'),
               str(bbox['minx']), str(bbox['miny']), str(bbox['maxx']), str(bbox['maxy']), job_dir]
        JOBS[job_id]['status'] = 'running'
        subprocess.check_call(cmd)
        JOBS[job_id]['status'] = 'done'
    except Exception as e:
        JOBS[job_id]['status'] = 'error'
        JOBS[job_id]['error'] = str(e)


@app.post('/process_bbox')
def process_bbox(bbox: BBox):
    # enqueue job and run in background
    job_id = str(uuid.uuid4())
    JOBS[job_id] = {'status': 'queued', 'bbox': bbox.dict()}
    thread = threading.Thread(target=_run_pipeline, args=(job_id, bbox.dict()), daemon=True)
    thread.start()
    return {'job_id': job_id}


@app.get('/jobs/{job_id}')
def get_job(job_id: str):
    job = JOBS.get(job_id)
    if not job:
        return {'error': 'job not found'}
    # if done and scored geojson exists, return path
    job_dir = os.path.join(os.path.dirname(__file__), '..', 'data', 'jobs', job_id)
    scored = os.path.join(job_dir, 'scored_zones.geojson')
    if job.get('status') == 'done' and os.path.exists(scored):
        try:
            with open(scored) as f:
                data = json.load(f)
        except Exception:
            data = None
        return {'status': job['status'], 'result': data}
    return {'status': job['status']}