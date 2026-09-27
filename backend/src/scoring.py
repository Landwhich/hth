"""
Step 5 — Turn (car mask + rotated rect) + (spot polygon) into a 0-100 score.

Three signals, each 0 (bad) to 1 (perfect), combined with weights:
  - encroachment: fraction of the car mask that falls OUTSIDE the spot
  - centering:    how far the car's centroid is from the spot's centroid,
                  normalized by spot size
  - alignment:    angle difference between the car's long axis and the
                  spot's dominant axis (from its longest edge)
"""

import numpy as np
import cv2
from shapely.geometry import Polygon

WEIGHTS = {"encroachment": 0.5, "centering": 0.3, "alignment": 0.2}


def _mask_to_polygon(mask: np.ndarray) -> Polygon | None:
    contours, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    contour = max(contours, key=cv2.contourArea)
    if len(contour) < 3:
        return None
    poly = Polygon(contour.reshape(-1, 2))
    if not poly.is_valid:
        poly = poly.buffer(0)
    return poly if not poly.is_empty else None


def _spot_dominant_angle(spot: Polygon) -> float:
    """Angle (degrees) of the longest edge of the spot polygon."""
    coords = list(spot.exterior.coords)
    best_len, best_angle = -1, 0.0
    for i in range(len(coords) - 1):
        (x1, y1), (x2, y2) = coords[i], coords[i + 1]
        length = np.hypot(x2 - x1, y2 - y1)
        if length > best_len:
            best_len = length
            best_angle = np.degrees(np.arctan2(y2 - y1, x2 - x1))
    return best_angle % 180


def compute_score(target_car: dict, spot_polygon: Polygon) -> dict:
    """
    Returns:
      {
        'score': float 0-100,
        'grade': str,
        'breakdown': {'encroachment_pct': ..., 'centering_error': ..., 'angle_diff_deg': ...},
        'feedback': str
      }
    """
    car_poly = _mask_to_polygon(target_car["mask"])
    if car_poly is None or spot_polygon is None or spot_polygon.is_empty:
        return {
            "score": 0.0, "grade": "F",
            "breakdown": {}, "feedback": "Could not evaluate — detection failed.",
        }

    # --- Encroachment ---
    car_area = car_poly.area or 1.0
    inside_area = car_poly.intersection(spot_polygon).area
    encroachment_pct = max(0.0, 1.0 - inside_area / car_area)  # 0 = fully inside

    # --- Centering ---
    car_cx, car_cy = target_car["centroid"]
    spot_cx, spot_cy = spot_polygon.centroid.x, spot_polygon.centroid.y
    minx, miny, maxx, maxy = spot_polygon.bounds
    spot_scale = max(maxx - minx, maxy - miny, 1.0)
    centering_error = min(1.0, np.hypot(car_cx - spot_cx, car_cy - spot_cy) / (spot_scale / 2))

    # --- Alignment ---
    car_angle = target_car["rect"][2] % 180
    spot_angle = _spot_dominant_angle(spot_polygon)
    diff = abs(car_angle - spot_angle) % 180
    angle_diff_deg = min(diff, 180 - diff)
    alignment_error = min(1.0, angle_diff_deg / 45.0)  # 45+ deg off = fully bad

    # --- Combine ---
    
    if encroachment_pct: 
        penalty = (
            WEIGHTS["encroachment"] * encroachment_pct
            + WEIGHTS["centering"] * centering_error
            + WEIGHTS["alignment"] * alignment_error
        )
    else:
        penalty = (
            WEIGHTS["centering"] * centering_error
            + (WEIGHTS["encroachment"] + WEIGHTS["alignment"]) * alignment_error
        )
    score = round(max(0.0, 1.0 - penalty) * 100, 1)

    grade = (
        "A" if score >= 90 else
        "B" if score >= 75 else
        "C" if score >= 60 else
        "D" if score >= 40 else "F"
    )

    notes = []
    if encroachment_pct > 0.05:
        notes.append(f"{encroachment_pct*100:.0f}% of the car is outside the spot")
    if centering_error > 0.3:
        notes.append("car is off-center in the spot")
    if angle_diff_deg > 10:
        notes.append(f"parked at a {angle_diff_deg:.0f}\u00b0 angle relative to the spot")
    feedback = "Well parked." if not notes else "Issues: " + "; ".join(notes) + "."

    return {
        "score": score,
        "grade": grade,
        "breakdown": {
            "encroachment_pct": round(encroachment_pct * 100, 1),
            "centering_error": round(centering_error, 3),
            "angle_diff_deg": round(angle_diff_deg, 1),
        },
        "feedback": feedback,
    }
