"""SigLIP relevance gate — does this image actually show what the beat says?

CPU inference, embeddings cached alongside assets in media.db so recurring
topics skip both the network AND the model.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image

log = logging.getLogger("vulcan.assets")

MODEL_ID = "google/siglip-base-patch16-224"


@lru_cache(maxsize=1)
def _load():
    import torch  # noqa: F401  (system site-packages)
    from transformers import AutoModel, AutoProcessor

    processor = AutoProcessor.from_pretrained(MODEL_ID)
    model = AutoModel.from_pretrained(MODEL_ID)
    model.eval()
    return processor, model


def image_embedding(img_path: str | Path) -> np.ndarray:
    import torch

    processor, model = _load()
    img = Image.open(img_path).convert("RGB")
    # flatten transparency onto mid-grey so the subject, not the checkerboard, is embedded
    inputs = processor(images=img, return_tensors="pt")
    with torch.no_grad():
        feat = model.get_image_features(**inputs)
    feat = feat[0].numpy().astype(np.float32)
    return feat / np.linalg.norm(feat)


def text_embedding(text: str) -> np.ndarray:
    import torch

    processor, model = _load()
    inputs = processor(text=[f"a photo of {text}"], return_tensors="pt", padding="max_length")
    with torch.no_grad():
        feat = model.get_text_features(**inputs)
    feat = feat[0].numpy().astype(np.float32)
    return feat / np.linalg.norm(feat)


def relevance(img_path: str | Path, phrase: str) -> tuple[float, np.ndarray]:
    """cosine(text, image) in SigLIP space + the image embedding for caching."""
    img_emb = image_embedding(img_path)
    txt_emb = text_embedding(phrase)
    return float(np.dot(img_emb, txt_emb)), img_emb
