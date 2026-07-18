"""Supabase persistence for AutoSentinel zones.

Env vars required (add to .env / your deploy environment):
  SUPABASE_URL          - e.g. https://xxxxxxxx.supabase.co
  SUPABASE_SERVICE_KEY  - the *service_role* key (Project Settings > API)
                          NOT the anon key — this backend needs write access
                          and bypasses RLS.

Never commit the service key. It belongs server-side only.
"""

from __future__ import annotations

import os
import threading
from typing import Iterable

_client = None
_client_lock = threading.Lock()


def get_supabase_client():
    """Lazily create a single shared Supabase client."""
    global _client
    if _client is not None:
        return _client

    with _client_lock:
        if _client is not None:
            return _client

        from supabase import create_client  # import here so app can boot without the package during local dev

        url = os.getenv("SUPABASE_URL", "").strip()
        key = os.getenv("SUPABASE_SERVICE_KEY", "").strip()

        if not url or not key:
            raise RuntimeError(
                "Supabase is not configured. Set SUPABASE_URL and "
                "SUPABASE_SERVICE_KEY environment variables."
            )

        _client = create_client(url, key)
        return _client


# Columns that actually exist on the zones table — anything else on a zone
# dict gets dropped before insert so a stray field doesn't crash the upsert.
_ZONE_COLUMNS = {
    "id", "source", "lat", "lon", "area_sqm", "severity", "risk_score",
    "action", "violation_type", "bhuvan_land_type", "bhuvan_confidence",
    "bhuvan_overlap_percent", "bhuvan_source", "osm_flags", "legal_flags",
    "risk_boost_total", "legal_explanation", "microsoft_confirmed",
    "construction_detected", "vision_confidence", "objects_found",
    "crane_present", "building_present", "container_present",
    "area_label", "period_label",
}


def _to_row(zone: dict, source: str) -> dict:
    row = {k: v for k, v in zone.items() if k in _ZONE_COLUMNS}
    row["id"] = str(zone.get("id"))
    row["source"] = source
    return row


def upsert_zones(zones: Iterable[dict], source: str = "live", batch_size: int = 500) -> int:
    """Upsert zones into Supabase. Returns number of rows written.

    Safe to call repeatedly — conflicts on `id` overwrite the existing row
    (so re-running a scan updates rather than duplicates).
    """
    client = get_supabase_client()
    rows = [_to_row(z, source) for z in zones]

    written = 0
    for i in range(0, len(rows), batch_size):
        batch = rows[i : i + batch_size]
        client.table("zones").upsert(batch, on_conflict="id").execute()
        written += len(batch)
    return written


def fetch_zones(source: str | None = None, limit: int = 5000) -> list[dict]:
    client = get_supabase_client()
    query = client.table("zones").select("*").limit(limit)
    if source:
        query = query.eq("source", source)
    result = query.execute()
    return result.data or []


def delete_zone(zone_id: str) -> None:
    client = get_supabase_client()
    client.table("zones").delete().eq("id", str(zone_id)).execute()