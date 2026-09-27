"""
Classical edge/line detection as a boundary-orientation source, replacing
noisy semantic ('curb'/'line') detections that can't distinguish the right
line from any line in frame.

Pipeline: Canny -> probabilistic Hough transform -> keep only segments
whose direction matches a reference direction (dot-product similarity)
-> CLUSTER those into candidate real-world lines by perpendicular offset
-> score each cluster by total supporting length (+ optional semantic
mask overlap) -> only accept a cluster if it clears a confidence
threshold -> return the closest confident cluster, or None.

v2 change: the old version took the single Hough segment closest to the
car and returned it unconditionally, with no confidence check. That's
what let a brick joint, a shadow, or a stray Canny edge get treated as a
"parking line" whenever no real one existed in frame. Now a boundary is
only reported when enough aligned, roughly-collinear evidence backs it —
otherwise the caller gets None and should fall back gracefully rather
than trust a line that isn't really there.
"""

import numpy as np
import cv2


def extract_line_segments(image_bgr, window, canny_low=50, canny_high=150,
    hough_threshold=40, min_line_length=40, max_line_gap=15):
    """Canny + HoughLinesP inside `window` (x1,y1,x2,y2). Returns segments
    in FULL-IMAGE coordinates."""
    x1, y1, x2, y2 = window
    crop = image_bgr[y1:y2, x1:x2]
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(gray, canny_low, canny_high)

    lines = cv2.HoughLinesP(edges, rho=1, theta=np.pi / 180, threshold=hough_threshold,
    minLineLength=min_line_length, maxLineGap=max_line_gap)
    if lines is None:
        return []
    return [(lx1 + x1, ly1 + y1, lx2 + x1, ly2 + y1) for lx1, ly1, lx2, ly2 in lines]


def _unit_direction(seg):
    x1, y1, x2, y2 = seg
    dx, dy = x2 - x1, y2 - y1
    norm = np.hypot(dx, dy) or 1.0
    return dx / norm, dy / norm


def _midpoint(seg):
    x1, y1, x2, y2 = seg
    return (x1 + x2) / 2, (y1 + y2) / 2


def _length(seg):
    x1, y1, x2, y2 = seg
    return float(np.hypot(x2 - x1, y2 - y1))


def group_by_direction(segments, reference_dir, angle_tol_deg=15):
    """Keeps segments whose direction is within angle_tol_deg of
    reference_dir (dot product similarity; abs() so 180-degree-flipped
    lines still count as aligned, since a line has no inherent 'forward')."""
    rx, ry = reference_dir
    r_norm = np.hypot(rx, ry) or 1.0
    rx, ry = rx / r_norm, ry / r_norm
    cos_tol = np.cos(np.radians(angle_tol_deg))
    return [s for s in segments if abs(_unit_direction(s)[0]*rx + _unit_direction(s)[1]*ry) >= cos_tol]


def _perp_distance(seg, ref_point, ref_dir):
    """Signed perpendicular distance from ref_point to the infinite line
    running through seg's midpoint, along ref_dir."""
    rx, ry = ref_dir
    norm = np.hypot(rx, ry) or 1.0
    rx, ry = rx / norm, ry / norm
    nx, ny = -ry, rx
    mx, my = _midpoint(seg)
    return (mx - ref_point[0]) * nx + (my - ref_point[1]) * ny


def cluster_collinear_segments(segments, ref_point, ref_dir, offset_tol_px=10):
    """
    Groups direction-aligned segments (caller already filtered for shared
    orientation via group_by_direction) into clusters that plausibly trace
    the *same* physical line: a similar perpendicular offset from
    ref_point, within offset_tol_px.

    This is what separates "a real curb" (Hough usually breaks a long
    real edge into several roughly-collinear fragments) from "one stray
    edge from a brick joint or shadow" (a single short segment with no
    supporting neighbours at the same offset).

    Returns clusters sorted by total supporting length, descending:
      [{'segments': [...], 'total_length': float,
        'point': (x,y), 'direction': (dx,dy)}, ...]
    """
    if not segments:
        return []

    scored = sorted(((_perp_distance(s, ref_point, ref_dir), s) for s in segments),
                     key=lambda t: t[0])

    clusters = []
    current = [scored[0]]
    for offset, seg in scored[1:]:
        if offset - current[-1][0] <= offset_tol_px:
            current.append((offset, seg))
        else:
            clusters.append(current)
            current = [(offset, seg)]
    clusters.append(current)

    out = []
    for cluster in clusters:
        segs = [s for _, s in cluster]
        weights = np.array([_length(s) for s in segs])
        total_length = float(weights.sum())

        pts = np.array([_midpoint(s) for s in segs])
        avg_point = tuple((pts * weights[:, None]).sum(axis=0) / weights.sum())

        dirs = np.array([_unit_direction(s) for s in segs])
        ref = dirs[0]
        # flip anti-parallel directions before averaging (a line has no
        # inherent forward, but the average needs a consistent sign)
        dirs = np.array([d if np.dot(d, ref) >= 0 else -d for d in dirs])
        avg_dir = tuple((dirs * weights[:, None]).sum(axis=0) / weights.sum())

        out.append({"segments": segs, "total_length": total_length,
                     "point": avg_point, "direction": avg_dir})

    out.sort(key=lambda c: c["total_length"], reverse=True)
    return out


def _mask_support(cluster, boundary_masks, max_dist_px=12):
    """
    Optional semantic cross-check against Grounding-DINO+SAM boundary
    masks (curb / fence / pavement-edge). Returns a 0..1 coverage score:
    the fraction of the cluster's endpoints that land within max_dist_px
    of *some* boundary mask. If boundary_masks is empty (none detected,
    or the caller doesn't have them), this contributes 0 rather than
    penalizing the cluster — classical evidence still stands on its own.
    """
    if not boundary_masks:
        return 0.0

    xs, ys = [], []
    for x1, y1, x2, y2 in cluster["segments"]:
        xs.extend([x1, x2])
        ys.extend([y1, y2])
    xs, ys = np.array(xs).astype(int), np.array(ys).astype(int)

    best = 0.0
    for mask in boundary_masks:
        if not mask.any():
            continue
        dist = cv2.distanceTransform((~mask).astype(np.uint8), cv2.DIST_L2, 3)
        hits = 0
        for x, y in zip(xs, ys):
            if 0 <= y < dist.shape[0] and 0 <= x < dist.shape[1] and dist[y, x] <= max_dist_px:
                hits += 1
        best = max(best, hits / max(len(xs), 1))
    return best


def vehicle_padding_window(car, image_shape, base_pad_x=1.2, base_pad_y=0.8):
    """Search window scaled by vehicle bbox size and class — trucks/vans
    get more padding since their spot boundaries sit further from the body."""
    x1, y1, x2, y2 = car["bbox"]
    w, h = x2 - x1, y2 - y1
    size_factor = 1.4 if car.get("cls_id") == 7 else 1.0  # COCO id 7 = truck
    H, W = image_shape[:2]
    sx1 = max(0, int(x1 - base_pad_x * size_factor * w))
    sx2 = min(W, int(x2 + base_pad_x * size_factor * w))
    sy1 = max(0, int(y1 - base_pad_y * size_factor * h))
    sy2 = min(H, int(y2 + base_pad_y * size_factor * h))
    return sx1, sy1, sx2, sy2


def find_boundary_line(image_bgr, target_car, reference_dir, side, angle_tol_deg=15,
    min_confidence_px=None, boundary_masks=None):
    """
    side: 'behind' (smaller y than car) or 'front' (larger y).

    Returns {'point':, 'direction':, 'confidence': float} for the closest
    CONFIDENT cluster of aligned, collinear segments on that side, or None
    if nothing clears the confidence bar. None means "no real evidence of
    a boundary here" — callers must treat that as an abstention and fall
    back accordingly, not draw a line anyway.

    min_confidence_px: minimum total supporting segment length required
    to accept a cluster as a real boundary. Defaults to 35% of the car's
    own bbox width — a real curb or parking line generally spans a good
    fraction of the car's footprint; an isolated brick-joint or shadow
    artifact usually doesn't.

    boundary_masks: optional list of full-image bool masks (from
    boundary_detection.py's SAM step — curb/fence/pavement-edge). When
    given, a cluster overlapping one gets a confidence boost, so genuine
    boundaries are easier to accept and coincidental noise is harder to.
    """
    window = vehicle_padding_window(target_car, image_bgr.shape)
    segments = extract_line_segments(image_bgr, window)
    aligned = group_by_direction(segments, reference_dir, angle_tol_deg)

    tx, ty = target_car["centroid"]
    if side == "behind":
        aligned = [s for s in aligned if _midpoint(s)[1] < ty]
    elif side == "front":
        aligned = [s for s in aligned if _midpoint(s)[1] > ty]
    if not aligned:
        return None

    if min_confidence_px is None:
        x1, y1, x2, y2 = target_car["bbox"]
        min_confidence_px = 0.35 * (x2 - x1)

    clusters = cluster_collinear_segments(aligned, (tx, ty), reference_dir)
    if not clusters:
        return None

    # Reject anything that doesn't clear the raw evidence bar first —
    # a mask-support bonus can push a borderline cluster over the top,
    # but it should never rescue a near-empty one.
    confident = [c for c in clusters if c["total_length"] >= min_confidence_px]
    if not confident:
        return None

    # Among confident clusters, prefer the one closest to the car (most
    # plausibly *its* boundary, not some other car's or a distant curb),
    # with mask overlap used as a tiebreak-ish boost on distance ranking.
    scored = []
    for c in confident:
        dist = np.hypot(c["point"][0] - tx, c["point"][1] - ty)
        support = _mask_support(c, boundary_masks or [])
        # semantic support effectively "pulls" a cluster closer in ranking
        adjusted_dist = dist / (1.0 + support)
        scored.append((adjusted_dist, c))
    scored.sort(key=lambda t: t[0])

    best = scored[0][1]
    return {
        "point": best["point"],
        "direction": best["direction"],
        "confidence": best["total_length"],
    }
