from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import json
import os

app = FastAPI()

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