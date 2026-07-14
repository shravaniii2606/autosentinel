"""Land-use providers and zone-overlay utilities for the Dahisar demo area.

The rest of the application consumes a normalised GeoJSON layer.  Swap only the
provider passed to ``load_landuse`` when an authenticated ISRO Bhuvan service is
available; the scoring and output contract remain unchanged.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
import os
from typing import Iterable, Optional, Sequence

import geopandas as gpd
import pandas as pd


NORMALIZED_TYPES = {
    "Forest", "Water Body", "Agriculture", "Residential", "Industrial",
    "Commercial", "Park", "Wetland", "Open Land", "Unknown",
}

# Higher values resolve ties when different OSM features cover the same area.
LAND_USE_PRIORITY = {
    "Wetland": 100, "Water Body": 95, "Forest": 90, "Park": 85,
    "Agriculture": 80, "Industrial": 60, "Commercial": 55,
    "Residential": 50, "Open Land": 30, "Unknown": 0,
}


def empty_landuse() -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        columns=["land_type", "source", "priority", "geometry"],
        geometry="geometry", crs="EPSG:4326",
    )


def normalise_land_type(properties: dict) -> str:
    """Map OSM-style tags to the small, stable public land-use vocabulary."""
    tags = {str(k).lower(): str(v).lower() for k, v in (properties or {}).items()
            if v not in (None, "")}
    text = " ".join(tags.values())
    landuse, natural, leisure = tags.get("landuse", ""), tags.get("natural", ""), tags.get("leisure", "")
    if natural == "wetland" or "wetland" in text or tags.get("waterway") in {"river", "stream", "canal"}:
        return "Wetland"
    if natural == "water" or tags.get("water") or landuse in {"reservoir", "basin"} or "water" in text:
        return "Water Body"
    if landuse == "forest" or natural in {"wood", "tree_row"} or "forest" in text or "wood" in text:
        return "Forest"
    if leisure in {"park", "garden", "nature_reserve"} or landuse in {"recreation_ground", "village_green"}:
        return "Park"
    if landuse in {"farmland", "farmyard", "orchard", "vineyard", "greenhouse_horticulture", "meadow"} or "agricultur" in text:
        return "Agriculture"
    if landuse in {"industrial", "industrial_area"}:
        return "Industrial"
    if landuse in {"retail", "commercial"}:
        return "Commercial"
    if landuse in {"residential", "allotments"}:
        return "Residential"
    if landuse in {"grass", "brownfield", "greenfield", "quarry", "landfill", "construction"} or natural in {"scrub", "bare_rock", "sand", "heath"}:
        return "Open Land"
    return "Unknown"


class LandUseProvider(ABC):
    """Stable provider interface for a normalised WGS84 land-use layer."""

    @abstractmethod
    def load_landuse(self, bbox: Optional[Sequence[float]] = None) -> gpd.GeoDataFrame:
        raise NotImplementedError


class LocalGeoJSONProvider(LandUseProvider):
    """Load the vetted, independently generated Dahisar OSM land-use extract."""

    def __init__(self, path: str):
        self.path = path

    def load_landuse(self, bbox: Optional[Sequence[float]] = None) -> gpd.GeoDataFrame:
        if not os.path.exists(self.path):
            print(f"Land-use file is missing: {self.path}. Continuing with an empty layer.")
            return empty_landuse()
        layer = gpd.read_file(self.path)
        if layer.crs is None:
            layer = layer.set_crs("EPSG:4326")
        else:
            layer = layer.to_crs("EPSG:4326")
        for column, default in (("land_type", "Unknown"), ("source", "Local GeoJSON"), ("priority", 0)):
            if column not in layer:
                layer[column] = default
        layer = layer[layer.geometry.notna() & ~layer.geometry.is_empty].copy()
        layer = layer[layer.geom_type.isin(["Polygon", "MultiPolygon"])]
        layer["land_type"] = layer["land_type"].where(layer["land_type"].isin(NORMALIZED_TYPES), "Unknown")
        layer["priority"] = pd.to_numeric(layer["priority"], errors="coerce").fillna(0).astype(int)
        if bbox and not layer.empty:
            from shapely.geometry import box
            layer = layer[layer.intersects(box(*bbox))]
        return layer[["land_type", "source", "priority", "geometry"]]


class FutureBhuvanProvider(LandUseProvider):
    """Extension point for an official ISRO Bhuvan API/WFS client.

    Implement authentication and ``load_landuse`` here.  It must return the same
    four columns as ``LocalGeoJSONProvider``; no downstream code needs changing.
    """

    def load_landuse(self, bbox: Optional[Sequence[float]] = None) -> gpd.GeoDataFrame:
        raise NotImplementedError("Configure the official ISRO Bhuvan API client before selecting this provider.")


def confidence_for_overlap(percent: float) -> str:
    if percent > 80:
        return "High"
    if percent >= 50:
        return "Medium"
    if percent >= 20:
        return "Low"
    return "Unknown"


def annotate_zones(zones: gpd.GeoDataFrame, landuse: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Assign the dominant intersecting land-use polygon by true projected area."""
    result = zones.copy()
    if result.crs is None:
        result = result.set_crs("EPSG:4326")
    else:
        result = result.to_crs("EPSG:4326")
    result["bhuvan_land_type"] = "Unknown"
    result["bhuvan_confidence"] = "Low"
    result["bhuvan_overlap_percent"] = 0.0
    result["bhuvan_source"] = "No land-use polygon intersected"
    if landuse.empty or result.empty:
        return result

    metric_zones = result.to_crs("EPSG:32643")
    metric_landuse = landuse.to_crs("EPSG:32643")
    index = metric_landuse.sindex
    for zone_index, zone in metric_zones.iterrows():
        if zone.geometry is None or zone.geometry.is_empty or zone.geometry.area <= 0:
            continue
        matches = []
        for candidate in index.query(zone.geometry, predicate="intersects"):
            feature = metric_landuse.iloc[candidate]
            overlap = zone.geometry.intersection(feature.geometry).area
            if overlap > 0:
                matches.append((overlap, int(feature["priority"]), feature))
        if not matches:
            continue
        # Dominant overlap wins; priority makes exact ties deterministic.
        overlap, _, feature = max(matches, key=lambda item: (item[0], item[1]))
        percent = round(min(100.0, overlap / zone.geometry.area * 100), 1)
        result.at[zone_index, "bhuvan_land_type"] = feature["land_type"]
        result.at[zone_index, "bhuvan_confidence"] = confidence_for_overlap(percent)
        result.at[zone_index, "bhuvan_overlap_percent"] = percent
        result.at[zone_index, "bhuvan_source"] = feature["source"]
    return result
