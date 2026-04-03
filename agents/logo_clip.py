"""
Local CLIP (ViT) scoring for header/nav logo candidates — no remote LLM API.

Used by input_processor when LOGO_CLIP_ENABLED is true. Model:
openai/clip-vit-base-patch32
"""

from __future__ import annotations

import io
import logging
import threading

from PIL import Image

logger = logging.getLogger(__name__)

_clip_lock = threading.Lock()
_model = None
_processor = None

try:
    from transformers import CLIPModel, CLIPProcessor

    _TRANSFORMERS_OK = True
except ImportError:
    _TRANSFORMERS_OK = False


def clip_dependencies_available() -> bool:
    return _TRANSFORMERS_OK


def _device() -> str:
    import torch as t

    return "cuda" if t.cuda.is_available() else "cpu"


def _load_clip():
    global _model, _processor
    with _clip_lock:
        if _model is not None and _processor is not None:
            return _model, _processor
        model_id = "openai/clip-vit-base-patch32"
        _processor = CLIPProcessor.from_pretrained(model_id)
        _model = CLIPModel.from_pretrained(model_id)
        _model.eval()
        dev = _device()
        _model = _model.to(dev)
        logger.info("logo_clip: loaded %s on %s", model_id, dev)
        return _model, _processor


def pick_best_logo_candidate(
    png_bytes_list: list[bytes],
    product_name: str,
) -> tuple[bytes, float] | None:
    """
    Score PNG screenshots against "{product_name} official company logo".
    Returns (best_png_bytes, softmax_probability_among_candidates) or None.
    """
    if not _TRANSFORMERS_OK or not png_bytes_list:
        return None

    paired: list[tuple[bytes, Image.Image]] = []
    for b in png_bytes_list:
        try:
            paired.append((b, Image.open(io.BytesIO(b)).convert("RGB")))
        except Exception as exc:
            logger.debug("logo_clip: skip invalid screenshot bytes: %s", exc)
    if not paired:
        return None
    if len(paired) == 1:
        return paired[0][0], 1.0

    import torch

    from config import settings

    images = [p[1] for p in paired]
    pngs = [p[0] for p in paired]

    model, processor = _load_clip()
    dev = next(model.parameters()).device
    name = (product_name or "").strip() or "company"
    text = f"{name} official company logo"

    text_inputs = processor(text=[text], return_tensors="pt", padding=True)
    image_inputs = processor(images=images, return_tensors="pt", padding=True)
    text_inputs = {k: v.to(dev) for k, v in text_inputs.items()}
    image_inputs = {k: v.to(dev) for k, v in image_inputs.items()}

    with torch.no_grad():
        text_feat = model.get_text_features(**text_inputs)
        text_feat = text_feat / text_feat.norm(dim=-1, keepdim=True)
        image_feat = model.get_image_features(**image_inputs)
        image_feat = image_feat / image_feat.norm(dim=-1, keepdim=True)
        logits = (image_feat @ text_feat.T).squeeze(-1).clone()

    if settings.LOGO_OCR_ENABLED and name != "company":
        try:
            from agents import logo_ocr

            if logo_ocr.ocr_dependencies_available():
                bonus = float(settings.LOGO_OCR_LOGIT_BONUS)
                for i, b in enumerate(pngs):
                    ocr_raw = logo_ocr.extract_text_png(b)
                    m = logo_ocr.name_match_score(name, ocr_raw)
                    if m > 0:
                        logits[i] = logits[i] + bonus * m
        except Exception as exc:
            logger.debug("logo_clip: OCR bonus skipped: %s", exc)

    probs = logits.softmax(dim=0)
    best_idx = int(probs.argmax().item())

    return pngs[best_idx], float(probs[best_idx].item())
