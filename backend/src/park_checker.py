"""
End-to-end pipeline:
  1. YOLOv8-seg          -> detect all cars, get masks + rotated rects
  2. Grounding DINO      -> zero-shot boxes for curb/fence/line/pavement
  3. SAM                 -> turn those boxes into masks
  4. Geometric reconstruction -> approximate parking-spot polygon
  5. Scoring             -> 0-100 score + feedback

Usage:
    python main.py path/to/image.jpg [--target x,y] [--out overlay.jpg]

If --target isn't given, the car whose bounding box is closest to the
image's horizontal center is scored (a reasonable default for "the car
the photo is about").
"""

import argparse
import cv2
import numpy as np
from PIL import Image

from src.car_detection import load_yolo_model, detect_cars
from src.boundary_detection import (
    load_boundary_models, 
    detect_boundaries, 
    segment_boundaries,
    detect_boundaries_in_window, 
    segment_boundaries_in_window
)
from src.scoring import compute_score
from src.spot_geometry import compute_car_search_window, build_spot_polygon


def pick_target_car(cars: list[dict], image_shape, target_xy=None) -> dict:
    if target_xy is not None:
        tx, ty = target_xy
        return min(cars, key=lambda c: np.hypot(c["centroid"][0] - tx, c["centroid"][1] - ty))
    h, w = image_shape[:2]
    center_x = w / 2
    return min(cars, key=lambda c: abs(c["centroid"][0] - center_x))


def visualize(image_bgr, target_car, other_cars, spot_polygon, result, out_path):
    vis = image_bgr.copy()

    # other cars in gray
    for c in other_cars:
        cv2.drawContours(vis, [c["contour"]], -1, (150, 150, 150), 2)

    # target car in green
    cv2.drawContours(vis, [target_car["contour"]], -1, (0, 220, 0), 3)

    # spot polygon in yellow
    if spot_polygon is not None and not spot_polygon.is_empty:
        pts = np.array(spot_polygon.exterior.coords, dtype=np.int32)
        cv2.polylines(vis, [pts], isClosed=True, color=(0, 220, 255), thickness=2)

    label = f"Score: {result['score']}  Grade: {result['grade']}"
    cv2.putText(vis, label, (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 4, cv2.LINE_AA)
    cv2.putText(vis, label, (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2, cv2.LINE_AA)
    cv2.imwrite(out_path, vis)


def draw_boundaries_debug(image_bgr, boundaries, boundary_masks, out_path="boundaries_debug.jpg"):
    vis = image_bgr.copy()
    colors = [(255,0,255), (255,255,0), (0,255,255), (255,128,0)]
    for i, (b, mask) in enumerate(zip(boundaries, boundary_masks)):
        color = colors[i % len(colors)]
        x1, y1, x2, y2 = map(int, b["box"])
        cv2.rectangle(vis, (x1, y1), (x2, y2), color, 2)
        cv2.putText(vis, f"{b['label']} {b['score']:.2f}", (x1, max(y1 - 6, 0)),
            cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1, cv2.LINE_AA)
        overlay = np.zeros_like(vis)
        overlay[mask] = color
        vis = cv2.addWeighted(vis, 1.0, overlay, 0.4, 0)
    cv2.imwrite(out_path, vis)

def run_park_check(image_path: str, target_xy=None, out_path: str = "overlay.jpg"):
    image_bgr = cv2.imread(image_path)
    if image_bgr is None:
        raise FileNotFoundError(f"Could not read image: {image_path}")
    image_rgb_pil = Image.open(image_path).convert("RGB")

    # --- Step 1: cars ---
    print("[1/5] Loading YOLO and detecting cars...")
    yolo_model = load_yolo_model()
    cars = detect_cars(image_bgr, yolo_model)
    if not cars:
        raise RuntimeError("No cars detected — try lowering conf in detect_cars().")
    print(f"      found {len(cars)} car(s)")

    target_car = pick_target_car(cars, image_bgr.shape, target_xy)
    other_cars = [c for c in cars if c is not target_car]

    # --- Steps 2-3: boundaries, restricted to a window around the target car ---
    print("[2/5] Loading Grounding DINO + SAM and detecting boundaries near the car...")
    boundary_models = load_boundary_models()
    window = compute_car_search_window(target_car, image_bgr.shape)
    boundaries, crop = detect_boundaries_in_window(image_rgb_pil, window, boundary_models)
    print(f"      found {len(boundaries)} boundary element(s) in window {window}: "
    f"{[b['label'] for b in boundaries]}")

    print("[3/5] Segmenting boundary boxes with SAM...")
    boundary_masks = segment_boundaries_in_window(
        crop, 
        boundaries, 
        window, 
        image_bgr.shape, 
        boundary_models)
    masks_with_labels = list(zip(boundary_masks, [b["label"] for b in boundaries]))
    draw_boundaries_debug(image_bgr, boundaries, boundary_masks)

    # --- Step 4: geometry ---
    print("[4/5] Reconstructing spot polygon...")
    spot_polygon = build_spot_polygon(
        target_car, cars, image_bgr, image_bgr.shape,
        boundary_masks_with_labels=masks_with_labels,
    )

    # --- Step 5: score ---
    print("[5/5] Scoring...")
    result = compute_score(target_car, spot_polygon)
    print(f"      Score: {result['score']}  Grade: {result['grade']}")
    print(f"      Breakdown: {result['breakdown']}")
    print(f"      Feedback: {result['feedback']}")

    visualize(image_bgr, target_car, other_cars, spot_polygon, result, out_path)
    print(f"Overlay saved to {out_path}")
    return result

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("image", help="Path to the input image")
    parser.add_argument("--target", help="x,y pixel coords of the car to grade (default: most central)")
    parser.add_argument("--out", default="overlay.jpg", help="Output overlay image path")
    args = parser.parse_args()

    target_xy = None
    if args.target:
        x_str, y_str = args.target.split(",")
        target_xy = (float(x_str), float(y_str))

    run_park_check(args.image, target_xy, args.out)
