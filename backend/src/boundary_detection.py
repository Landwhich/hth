"""
Step 2 — Grounding DINO: zero-shot, text-prompted detection of boundary
elements (curb, fence, parking line, pavement edge). Works on any scene,
anywhere, no training or annotation.

Step 3 — SAM: turns those boxes into pixel masks.

Both loaded via `transformers` so there's no custom repo/CUDA-op setup.
First run downloads weights from HuggingFace.

Docs:
  https://huggingface.co/docs/transformers/model_doc/grounding-dino
  https://huggingface.co/docs/transformers/model_doc/sam
"""

from PIL import Image
import numpy as np
import torch
from transformers import (
    AutoProcessor,
    AutoModelForZeroShotObjectDetection,
    SamModel,
    SamProcessor,
)

# One phrase per concept, lowercase, each ending in a period — Grounding DINO
# parses prompts by splitting on periods, so don't combine concepts with "and".
DEFAULT_PROMPT = "curb. fence. parking line. pavement edge. wall."

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"


def load_boundary_models():
    """
    Loads Grounding DINO (tiny — fastest variant, plenty for this task) and
    SAM (base — same reasoning: speed over marginal accuracy under time
    pressure). Returns a dict of the four objects the other functions need.
    """
    gdino_id = "IDEA-Research/grounding-dino-tiny"
    gdino_processor = AutoProcessor.from_pretrained(gdino_id)
    gdino_model = AutoModelForZeroShotObjectDetection.from_pretrained(gdino_id).to(DEVICE)

    sam_id = "facebook/sam-vit-base"
    sam_processor = SamProcessor.from_pretrained(sam_id)
    sam_model = SamModel.from_pretrained(sam_id).to(DEVICE)

    return {
        "gdino_processor": gdino_processor,
        "gdino_model": gdino_model,
        "sam_processor": sam_processor,
        "sam_model": sam_model,
    }

def detect_boundaries_in_window(image_pil, window, models, text_prompt=DEFAULT_PROMPT,
    box_threshold=0.3, text_threshold=0.25):
    """
    Runs Grounding DINO only on the cropped `window` region, then translates
    the resulting boxes back into full-image coordinates.
    """
    x1, y1, x2, y2 = window
    crop = image_pil.crop((x1, y1, x2, y2))

    boundaries = detect_boundaries(crop, models, text_prompt, box_threshold, text_threshold)

    # translate box coords from crop-space back to full-image-space
    for b in boundaries:
        bx1, by1, bx2, by2 = b["box"]
        b["box"] = [bx1 + x1, by1 + y1, bx2 + x1, by2 + y1]

    return boundaries, crop


def segment_boundaries_in_window(crop, boundaries, window, image_shape, models):
    """
    Runs SAM on the crop, then pastes each resulting mask into a full-size
    zero canvas at the correct offset — so downstream code (which expects
    full-image-sized masks) doesn't need to know cropping happened.
    """
    x1, y1, x2, y2 = window

    # boxes need to be back in crop-local coords for SAM
    crop_local_boundaries = []
    for b in boundaries:
        bx1, by1, bx2, by2 = b["box"]
        crop_local_boundaries.append({**b, "box": [bx1 - x1, by1 - y1, bx2 - x1, by2 - y1]})

    crop_masks = segment_boundaries(crop, crop_local_boundaries, models)

    H, W = image_shape[:2]
    full_masks = []
    for m in crop_masks:
        full = np.zeros((H, W), dtype=bool)
        full[y1:y2, x1:x2] = m
        full_masks.append(full)

    return full_masks


def detect_boundaries(
    image_pil: Image.Image,
    models: dict,
    text_prompt: str = DEFAULT_PROMPT,
    box_threshold: float = 0.3,
    text_threshold: float = 0.25,
) -> list[dict]:
    """
    Runs Grounding DINO. Returns [{'box': [x1,y1,x2,y2], 'label': str, 'score': float}, ...]

    If you get zero detections, first try lowering box_threshold/text_threshold
    to ~0.2 before assuming the prompt is wrong — GDINO is conservative by default.
    """
    processor = models["gdino_processor"]
    model = models["gdino_model"]

    inputs = processor(images=image_pil, text=text_prompt, return_tensors="pt").to(DEVICE)
    with torch.no_grad():
        outputs = model(**inputs)

    results = processor.post_process_grounded_object_detection(
        outputs,
        inputs.input_ids,
        threshold=box_threshold,
        text_threshold=text_threshold,
        target_sizes=[image_pil.size[::-1]],  # (height, width)
    )[0]

    boundaries = []
    for box, label, score in zip(results["boxes"], results["labels"], results["scores"]):
        boundaries.append({
            "box": box.tolist(),
            "label": label,
            "score": float(score),
        })
    return boundaries


def segment_boundaries(
    image_pil: Image.Image,
    boundaries: list[dict],
    models: dict,
) -> list[np.ndarray]:
    """
    Step 3 — feeds each Grounding DINO box into SAM to get a pixel mask.
    Returns a list of bool ndarrays (H, W), one per input box, same order
    as `boundaries`.
    """
    if not boundaries:
        return []

    processor = models["sam_processor"]
    model = models["sam_model"]

    boxes = [[b["box"] for b in boundaries]]  # SAM expects a batch of box-lists
    inputs = processor(image_pil, input_boxes=boxes, return_tensors="pt").to(DEVICE)
    with torch.no_grad():
        outputs = model(**inputs)

    masks = processor.image_processor.post_process_masks(
        outputs.pred_masks.cpu(),
        inputs["original_sizes"].cpu(),
        inputs["reshaped_input_sizes"].cpu(),
    )[0]  # tensor shape: (num_boxes, num_pred_masks, H, W)

    # SAM returns 3 mask candidates per box (multimask_output default); take
    # the first — it's typically the best single-object guess for a box prompt.
    final_masks = [m[0].numpy().astype(bool) for m in masks]
    return final_masks


if __name__ == "__main__":
    import sys
    img_path = sys.argv[1] if len(sys.argv) > 1 else "test.jpg"
    image = Image.open(img_path).convert("RGB")
    models = load_boundary_models()
    boundaries = detect_boundaries(image, models)
    print(f"Found {len(boundaries)} boundary elements:")
    for b in boundaries:
        print(f"  {b['label']}: score={b['score']:.2f}, box={b['box']}")
    masks = segment_boundaries(image, boundaries, models)
    print(f"Generated {len(masks)} masks")
