# notebooks/sync_alchemyst_context.py
import os
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

import geopandas as gpd
from alchemyst_ai import AlchemystAI
from datetime import datetime, timezone
from geopy.geocoders import Nominatim
import time

geolocator = Nominatim(user_agent="autosentinel")
client = AlchemystAI(api_key=os.environ["ALCHEMYST_AI_API_KEY"])
zones = gpd.read_file("../data/scored_zones.geojson")

for idx, row in zones.iterrows():
    try:
        location = geolocator.reverse(f"{row['lat']}, {row['lon']}", timeout=5)
        place_name = location.address.split(',')[0] if location else "Unknown location"
    except Exception:
        place_name = "Unknown location"
    time.sleep(1) 
    content = (
        f"Zone {idx}: severity={row.get('severity')}, "
        f"risk_score={row.get('final_risk_score', row.get('risk_score'))}, "
        f"land_type={row.get('bhuvan_land_type')}, "
        f"legal_flags={row.get('legal_flags')}, "
        f"area={row.get('area_sqm')} sqm, "
        f"location={row.get('lat')},{row.get('lon')}"
    )
    file_name = f"zone_{idx}.txt"
    client.v1.context.add(
        documents=[{"content": content}],
        source="autosentinel_scored_zones",
        context_type="resource",
        scope="internal",
        metadata={
            "fileName": file_name,
            "fileType": "text/plain",
            "fileSize": len(content.encode("utf-8")),
            "lastModified": datetime.now(timezone.utc).isoformat(),
            "zone_id": str(idx),
        },
    )
    print(f"Synced zone {idx}")