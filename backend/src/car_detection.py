"""
Step 1 — Car detection & segmentation with YOLOv8-seg (Ultralytics).

No training needed: yolov8n-seg.pt is pretrained on COCO, which includes
'car' and 'truck'. The weights auto-download the first time you run this
(from Ultralytics' GitHub release assets), so just make sure you have
network access on first run.

Docs: https://docs.ultralytics.com/tasks/segment/
"""

import cv2
import numpy as np
from ultralytics import YOLO

# COCO class ids we care about: 2 = car, 7 = truck (bus=5 optional)
VEHICLE_CLASS_IDS = {2, 7}


def load_yolo_model(weights: str = "yolov8n-seg.pt") -> YOLO:
    """
    Loads a pretrained YOLOv8 segmentation model.
    'n' = nano (fastest, good enough here). Swap to 'yolov8s-seg.pt' for a
    small accuracy bump if you have a few extra seconds of inference time.
    First call downloads the weights automatically into the working dir.
    """
    return YOLO(weights)


def detect_cars(image_bgr: np.ndarray, model: YOLO, conf: float = 0.35) -> list[dict]:
    """
    Runs YOLOv8-seg on an image and returns one entry per detected vehicle:
      {
        'mask': bool ndarray (H, W) - pixel mask, resized to image size
        'contour': ndarray of contour points
        'centroid': (cx, cy)
        'rect': ((cx, cy), (w, h), angle_degrees)  # cv2.minAreaRect output
        'bbox': (x1, y1, x2, y2)
        'conf': float
        'cls_id': int(cls_id)
      }
    """
    h, w = image_bgr.shape[:2]
    results = model.predict(image_bgr, conf=conf, verbose=False)[0]

    cars = []
    if results.masks is None:
        return cars

    for i, cls_id in enumerate(results.boxes.cls.tolist()):
        if int(cls_id) not in VEHICLE_CLASS_IDS:
            continue

        # mask.data is at model input resolution; resize back to original image size
        raw_mask = results.masks.data[i].cpu().numpy()
        mask = cv2.resize(raw_mask, (w, h), interpolation=cv2.INTER_NEAREST) > 0.5

        contours, _ = cv2.findContours(
            mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        if not contours:
            continue
        contour = max(contours, key=cv2.contourArea)

        rect = cv2.minAreaRect(contour)  # ((cx,cy),(w,h),angle)
        M = cv2.moments(contour)
        if M["m00"] == 0:
            continue
        cx, cy = M["m10"] / M["m00"], M["m01"] / M["m00"]

        x1, y1, x2, y2 = results.boxes.xyxy[i].tolist()

        cars.append({
            "mask": mask,
            "contour": contour,
            "centroid": (cx, cy),
            "rect": rect,
            "bbox": (x1, y1, x2, y2),
            "conf": float(results.boxes.conf[i]),
            "cls_id": int(cls_id),
        })

    return cars


if __name__ == "__main__":
    # Quick smoke test: python car_detection.py path/to/image.jpg
    import sys
    img_path = sys.argv[1] if len(sys.argv) > 1 else "test.jpg"
    img = cv2.imread(img_path)
    model = load_yolo_model()
    cars = detect_cars(img, model)
    print(f"Found {len(cars)} vehicles")
    for c in cars:
        print(f"  centroid={c['centroid']}, angle={c['rect'][2]:.1f} deg, conf={c['conf']:.2f}")
