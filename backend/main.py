from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import subprocess
import sys
import os
import json
import os

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