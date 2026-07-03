import argparse
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ZONES_PATH = ROOT / "data" / "flagged_zones.json"
DEFAULT_IMAGES_DIR = ROOT / "data" / "images"
DEFAULT_MODEL_PATH = ROOT / "models" / "construction_detector.pt"

TARGET_CLASSES = ("building", "crane", "container")
CLASS_ALIASES = {
    "building": "building",
    "buildings": "building",
    "house": "building",
    "residential building": "building",
    "crane": "crane",
    "tower crane": "crane",
    "construction crane": "crane",
    "container": "container",
    "containers": "container",
    "shipping container": "container",
}


def vision_defaults() -> Dict[str, Any]:
    return {
        "construction_detected": False,
        "objects_found": [],
        "vision_confidence": 0.0,
        "crane_present": False,
        "building_present": False,
        "container_present": False,
    }


def canonical_class_name(name: str) -> Optional[str]:
    normalized = name.strip().lower().replace("_", " ").replace("-", " ")
    normalized = " ".join(normalized.split())

    if normalized in CLASS_ALIASES:
        return CLASS_ALIASES[normalized]

    for target in TARGET_CLASSES:
        if target in normalized:
            return target

    return None


def load_detector(model_path: Path):
    if not model_path.exists():
        # TODO: Train or fine-tune a YOLOv8/YOLOv11 detector on satellite crops
        # for building, crane, and container classes.
        # TODO: Save the trained weights to models/construction_detector.pt.
        print(f"YOLO model not found at {model_path}. Writing placeholder vision fields.")
        return None

    try:
        from ultralytics import YOLO
    except ImportError as exc:
        raise RuntimeError(
            "Ultralytics is required when a detector model is present. "
            "Install it with: pip install ultralytics"
        ) from exc

    return YOLO(str(model_path))


def after_image_path(images_dir: Path, zone_id: Any) -> Path:
    safe_id = str(zone_id).replace("/", "_").replace("\\", "_")
    return images_dir / f"zone_{safe_id}_after.png"


def extract_detections(result: Any, confidence_threshold: float) -> Dict[str, Any]:
    found: Dict[str, float] = {}
    names = getattr(result, "names", {}) or {}
    boxes = getattr(result, "boxes", None)

    if boxes is None:
        return vision_defaults()

    classes: Iterable[Any] = getattr(boxes, "cls", [])
    confidences: Iterable[Any] = getattr(boxes, "conf", [])

    if classes is None or confidences is None:
        return vision_defaults()

    try:
        classes = classes.tolist()
    except AttributeError:
        pass

    try:
        confidences = confidences.tolist()
    except AttributeError:
        pass

    for cls_idx, confidence in zip(classes, confidences):
        confidence = float(confidence)
        if confidence < confidence_threshold:
            continue

        raw_name = names.get(int(cls_idx), str(cls_idx)) if isinstance(names, dict) else str(cls_idx)
        class_name = canonical_class_name(raw_name)
        if class_name is None:
            continue

        found[class_name] = max(found.get(class_name, 0.0), confidence)

    objects_found = [name for name in TARGET_CLASSES if name in found]
    highest_confidence = max(found.values(), default=0.0)

    return {
        "construction_detected": bool(objects_found),
        "objects_found": objects_found,
        "vision_confidence": round(highest_confidence, 2),
        "crane_present": "crane" in found,
        "building_present": "building" in found,
        "container_present": "container" in found,
    }


def validate_zone(model: Any, image_path: Path, confidence_threshold: float) -> Dict[str, Any]:
    if model is None or not image_path.exists():
        return vision_defaults()

    results = model.predict(source=str(image_path), conf=confidence_threshold, verbose=False)
    if not results:
        return vision_defaults()

    return extract_detections(results[0], confidence_threshold)


def apply_risk_boost(zone: Dict[str, Any], vision: Dict[str, Any]) -> None:
    if "pre_vision_risk_score" not in zone:
        zone["pre_vision_risk_score"] = float(zone.get("risk_score", 0.0) or 0.0)

    base_score = float(zone.get("pre_vision_risk_score", zone.get("risk_score", 0.0)) or 0.0)
    boost = 0.0
    if vision.get("crane_present"):
        boost += 10.0
    if vision.get("building_present"):
        boost += 5.0

    zone["vision_risk_boost"] = boost
    zone["risk_score"] = round(min(100.0, base_score + boost), 1)


def enrich_zones(
    zones: List[Dict[str, Any]],
    images_dir: Path,
    model_path: Path,
    confidence_threshold: float,
) -> List[Dict[str, Any]]:
    model = load_detector(model_path)
    enriched = []

    for zone in zones:
        zone_id = zone.get("id")
        vision = validate_zone(model, after_image_path(images_dir, zone_id), confidence_threshold)
        zone.update(vision)
        apply_risk_boost(zone, vision)
        enriched.append(zone)

    enriched.sort(key=lambda item: float(item.get("risk_score", 0.0) or 0.0), reverse=True)
    return enriched


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate suspicious construction zones with a YOLO detector."
    )
    parser.add_argument("--zones-path", type=Path, default=DEFAULT_ZONES_PATH)
    parser.add_argument("--images-dir", type=Path, default=DEFAULT_IMAGES_DIR)
    parser.add_argument("--model-path", type=Path, default=DEFAULT_MODEL_PATH)
    parser.add_argument("--confidence", type=float, default=0.25)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    with args.zones_path.open("r", encoding="utf-8") as f:
        zones = json.load(f)

    enriched = enrich_zones(zones, args.images_dir, args.model_path, args.confidence)

    detected_count = sum(1 for zone in enriched if zone.get("construction_detected"))
    crane_count = sum(1 for zone in enriched if zone.get("crane_present"))
    print(
        f"Vision validation complete: {detected_count}/{len(enriched)} zones verified, "
        f"{crane_count} with cranes."
    )

    if args.dry_run:
        return

    with args.zones_path.open("w", encoding="utf-8") as f:
        json.dump(enriched, f, indent=2)
        f.write("\n")

    print(f"Updated {args.zones_path}")


if __name__ == "__main__":
    main()
