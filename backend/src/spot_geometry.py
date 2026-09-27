"""
Step 4 — Geometric reconstruction of the parking-spot boundary.

No model can reliably output "here is the empty parking spot polygon" when
there's no painted line — that's a spatial-reasoning problem, not a
perception one. So we reconstruct it from what the models DID find:

  - left/right edges  -> midline between the target car and its nearest
                          left/right neighbor car (from YOLO masks)
  - back edge         -> nearest curb/fence/wall evidence behind the car
  - front edge        -> nearest pavement-edge/curb evidence in front,
                          or a bounded fallback margin

Each edge is treated as an infinite line defining a half-plane; the spot
polygon is the intersection of all four half-planes (clipped to the image
bounds so it stays finite).

v2 change: back/front edges now use a three-tier fallback instead of
"one Hough line, no confidence check, or nothing":
  1. Semantic evidence from Grounding DINO + SAM (curb/fence/wall/
     pavement-edge masks) when a big-enough mask exists nearby — this was
     computed by boundary_detection.py in main.py but never actually
     reached this function before; it's wired in now.
  2. A confidence-gated classical Hough line (see line_detection.py) —
     only accepted if enough aligned, collinear evidence backs it, with
     semantic masks (tier 1) as a scoring boost rather than a hard gate.
  3. A bounded fixed-margin fallback (fraction of car size) instead of
     leaving that edge unconstrained out to the old 2x-car-size window —
     that's what used to make the reconstructed polygon balloon into a
     long diagonal sliver whenever no boundary was found.
"""

import numpy as np
import cv2
from shapely.geometry import Polygon, Point
from shapely.ops import unary_union, nearest_points
from src.line_detection import find_boundary_line

BIG = 1e5  # "infinite" half-plane extent, clipped later to image bounds
MIN_MASK_PIXELS = 800
MAX_ANGLE_FROM_HORIZONTAL = 15  # degrees

# Which Grounding DINO labels count as evidence for which edge. Behind the
# car we expect a hard boundary (curb/fence/wall); in front we expect an
# open-lane style boundary (pavement edge) but a curb is also valid.
BEHIND_LABELS = ("curb", "fence", "wall")
FRONT_LABELS = ("pavement edge", "curb")

# Fallback margin used when NEITHER semantic masks NOR a confident Hough
# line are found, as a fraction of the car's own bbox height. Small and
# fixed on purpose — this used to default to 2x the car's height/width,
# which is why an unconstrained edge could balloon the polygon out into
# empty space far past where any real spot boundary would be.
FALLBACK_MARGIN_FACTOR = 0.4


def _image_bounds_polygon(image_shape) -> Polygon:
    h, w = image_shape[:2]
    return Polygon([(0, 0), (w, 0), (w, h), (0, h)])


def _halfplane_polygon(point_on_line, direction, keep_side_point) -> Polygon:
    """
    Builds a very large polygon representing the half-plane through
    `point_on_line` with the given `direction` vector, on the side that
    contains `keep_side_point`.
    """
    px, py = point_on_line
    dx, dy = direction
    norm = np.hypot(dx, dy) or 1.0
    dx, dy = dx / norm, dy / norm
    nx, ny = -dy, dx
    kx, ky = keep_side_point[0] - px, keep_side_point[1] - py
    if nx * kx + ny * ky < 0:
        nx, ny = -nx, -ny

    p1 = (px - dx * BIG, py - dy * BIG)
    p2 = (px + dx * BIG, py + dy * BIG)
    p3 = (p2[0] + nx * BIG, p2[1] + ny * BIG)
    p4 = (p1[0] + nx * BIG, p1[1] + ny * BIG)
    return Polygon([p1, p2, p3, p4])


def _mask_polygon(car):
    poly = Polygon(car["contour"].reshape(-1, 2))
    if not poly.is_valid:
        poly = poly.buffer(0)
    return poly


def _neighbor_divider(target_car, neighbor_car):
    """
    Finds the actual closest points between the target car's and neighbor
    car's masks (not centroids), and builds a divider line through their
    midpoint, perpendicular to the gap between them. This respects each
    car's real width/shape instead of collapsing them to a point.
    """
    target_poly = _mask_polygon(target_car)
    neighbor_poly = _mask_polygon(neighbor_car)

    p1, p2 = nearest_points(target_poly, neighbor_poly)
    mx, my = (p1.x + p2.x) / 2, (p1.y + p2.y) / 2

    gap_dx, gap_dy = p2.x - p1.x, p2.y - p1.y
    divider_dir = (-gap_dy, gap_dx)  # perpendicular to the gap vector

    return (mx, my), divider_dir


def _nearest_neighbor_car(target, other_cars, direction: str):
    """direction: 'left' or 'right' — picks nearest car centroid in that
    direction from the target, roughly on the same horizontal band."""
    tx, ty = target["centroid"]
    candidates = []
    for c in other_cars:
        cx, cy = c["centroid"]
        if direction == "left" and cx < tx:
            candidates.append((tx - cx, c))
        elif direction == "right" and cx > tx:
            candidates.append((cx - tx, c))
    if not candidates:
        return None
    candidates.sort(key=lambda t: t[0])
    return candidates[0][1]


def compute_car_search_window(target_car, image_shape, pad_x_factor=1.5, pad_y_factor=1.0):
    """
    Returns (x1, y1, x2, y2) in full-image pixel coords: the car's bbox
    padded outward, clamped to the image bounds. This is the only region
    boundary detection will search within.
    """
    x1, y1, x2, y2 = target_car["bbox"]
    w, h = x2 - x1, y2 - y1
    H, W = image_shape[:2]
    sx1 = max(0, int(x1 - pad_x_factor * w))
    sx2 = min(W, int(x2 + pad_x_factor * w))
    sy1 = max(0, int(y1 - pad_y_factor * h))
    sy2 = min(H, int(y2 + pad_y_factor * h))
    return sx1, sy1, sx2, sy2


def _nearest_boundary_mask(target, boundary_masks_with_labels, wanted_labels, side: str):
    """
    Picks the boundary mask (from Grounding DINO+SAM) closest to the target
    car on the given side ('behind' = above car in image i.e. smaller y,
    'front' = below car i.e. larger y). Returns its centroid + a line
    direction fit to its contour, or None.

    Masks below MIN_MASK_PIXELS are skipped: a tiny sliver of a "curb"
    detection is more likely a false positive than real evidence, and
    fitting a line to a handful of pixels is unreliable anyway.
    """
    tx, ty = target["centroid"]
    x1, y1, x2, y2 = target["bbox"]
    car_width = x2 - x1
    max_x_distance = car_width * 2.5  # boundary must be roughly in line with the car

    best = None
    best_dist = None
    for mask, label in boundary_masks_with_labels:
        if wanted_labels and not any(w in label for w in wanted_labels):
            continue
        if mask.sum() < MIN_MASK_PIXELS:
            continue
        ys, xs = np.where(mask)
        if len(xs) == 0:
            continue
        mcx, mcy = xs.mean(), ys.mean()

        if abs(mcx - tx) > max_x_distance:
            continue  # wrong lane/row entirely — reject regardless of y-distance

        if side == "behind" and mcy >= ty:
            continue
        if side == "front" and mcy <= ty:
            continue
        dist = abs(mcy - ty)
        if best_dist is None or dist < best_dist:
            best_dist = dist
            best = (mask, xs, ys)

    if best is None:
        return None
    mask, xs, ys = best
    pts = np.column_stack([xs, ys]).astype(np.float32)
    vx, vy, x0, y0 = cv2.fitLine(pts, cv2.DIST_L2, 0, 0.01, 0.01).flatten()
    return {"point": (float(x0), float(y0)), "direction": (float(vx), float(vy))}


def _fallback_boundary(target_car, side, direction):
    """
    Tier 3: nothing semantic and nothing confident from Hough. Rather than
    leaving the edge unconstrained (which used to default all the way out
    to the 2x-car-size search window), place it a small, fixed margin from
    the car's own bbox — enough to not clip the car, not so much that a
    missing boundary silently inflates the whole spot.
    """
    x1, y1, x2, y2 = target_car["bbox"]
    h = y2 - y1
    cx = target_car["centroid"][0]
    margin = FALLBACK_MARGIN_FACTOR * h
    if side == "behind":
        return {"point": (cx, y1 - margin), "direction": direction}
    return {"point": (cx, y2 + margin), "direction": direction}


def _resolve_edge(image_bgr, target_car, perp_dir, side, boundary_masks_with_labels):
    """Three-tier resolution for the back/front edge: semantic mask ->
    confidence-gated Hough line -> bounded fallback margin."""
    labels = BEHIND_LABELS if side == "behind" else FRONT_LABELS

    sem = _nearest_boundary_mask(target_car, boundary_masks_with_labels or [], labels, side)
    if sem is not None:
        return sem

    masks_only = [m for m, _ in (boundary_masks_with_labels or [])]
    hough = find_boundary_line(image_bgr, target_car, perp_dir, side=side,
                                boundary_masks=masks_only)
    if hough is not None:
        return hough

    return _fallback_boundary(target_car, side, perp_dir)


def _car_depth_direction(car):
    """Direction the car's mask points away from the camera, approximating
    the road's perspective slant at this point in the image — used instead
    of a hardcoded vertical line for side-spot edges."""
    ys, xs = np.where(car["mask"])
    top_cutoff = ys.min() + (ys.max() - ys.min()) * 0.15
    top_band = ys <= top_cutoff
    top_x = xs[top_band].mean() if top_band.any() else car["centroid"][0]
    top_y = ys[top_band].mean() if top_band.any() else ys.min()
    cx, cy = car["centroid"]
    dx, dy = top_x - cx, top_y - cy
    norm = np.hypot(dx, dy) or 1.0
    return (dx / norm, dy / norm)


def build_spot_polygon(target_car, all_cars, image_bgr, image_shape,
                        boundary_masks_with_labels=None):
    """
    Reconstructs an approximate parking-spot polygon around `target_car`.

    boundary_masks_with_labels: list of (mask_ndarray, label_str) tuples
        from boundary_detection.py's SAM step, e.g.
        zip(boundary_masks, [b['label'] for b in boundaries]). Optional —
        pass None/omit to fall back to classical-only behind/front edges.

    Falls back gracefully on any side where no evidence is found, so the
    polygon degrades instead of failing OR silently ballooning.
    """
    bounds_poly = _image_bounds_polygon(image_shape)
    x1, y1, x2, y2 = target_car["bbox"]
    w, h = x2 - x1, y2 - y1
    window = Polygon([
        (x1 - 2*w, y1 - 2*h), (x2 + 2*w, y1 - 2*h),
        (x2 + 2*w, y2 + 2*h), (x1 - 2*w, y2 + 2*h),
    ])
    spot = bounds_poly.intersection(window)
    tx, ty = target_car["centroid"]
    depth_dir = _car_depth_direction(target_car)
    perp_dir = (-depth_dir[1], depth_dir[0])  # rotate 90°
    other_cars = [c for c in all_cars if c is not target_car]

    # Left edge
    left_car = _nearest_neighbor_car(target_car, other_cars, "left")
    if left_car is not None:
        point, direction = _neighbor_divider(target_car, left_car)
        hp = _halfplane_polygon(point, direction, (tx, ty))
        spot = spot.intersection(hp)

    # Right edge
    right_car = _nearest_neighbor_car(target_car, other_cars, "right")
    if right_car is not None:
        point, direction = _neighbor_divider(target_car, right_car)
        hp = _halfplane_polygon(point, direction, (tx, ty))
        spot = spot.intersection(hp)

    # Back edge (curb / fence / wall, behind the car)
    back = _resolve_edge(image_bgr, target_car, perp_dir, "behind", boundary_masks_with_labels)
    hp = _halfplane_polygon(back["point"], back["direction"], (tx, ty))
    spot = spot.intersection(hp)

    # Front edge (pavement edge / curb, in front of the car)
    front = _resolve_edge(image_bgr, target_car, perp_dir, "front", boundary_masks_with_labels)
    hp = _halfplane_polygon(front["point"], front["direction"], (tx, ty))
    spot = spot.intersection(hp)

    if spot.is_empty:
        # Degenerate case (bad geometry from noisy detections) — fall back
        # to a generous box around the car so scoring doesn't crash.
        x1, y1, x2, y2 = target_car["bbox"]
        pad_x, pad_y = (x2 - x1) * 0.6, (y2 - y1) * 0.3
        spot = Polygon([
            (x1 - pad_x, y1 - pad_y), (x2 + pad_x, y1 - pad_y),
            (x2 + pad_x, y2 + pad_y), (x1 - pad_x, y2 + pad_y),
        ])

    return spot
