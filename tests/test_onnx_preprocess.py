"""Detector preprocessing: the resize must match the training (PIL BILINEAR with antialiasing)."""

import numpy as np
from PIL import Image

from docval.detect.onnx_detector import MEAN, STD, preprocess, resize_bilinear


def _page(levels: int, seed: int = 0) -> np.ndarray:
    """A4-like page 1241 x 1755: thin text-like strokes; levels=5 like scans saved with few grey levels."""
    rng = np.random.default_rng(seed)
    a = np.full((1755, 1241, 3), 245, np.uint8)
    for _ in range(400):
        y, x = rng.integers(0, 1740), rng.integers(0, 1200)
        a[y:y + rng.integers(1, 3), x:x + rng.integers(5, 40)] = rng.integers(0, 120)
    a = a.astype(np.float32) + rng.normal(0, 6, a.shape)
    q = 255 / (levels - 1)
    return np.clip(np.round(a / q) * q, 0, 255).astype(np.uint8)


def test_resize_matches_pil():
    for levels in (256, 5):
        a = _page(levels)
        for size in ((640, 640), (320, 448), (1241, 900), (2000, 2500)):
            ref = np.asarray(Image.fromarray(a).resize(size, Image.BILINEAR)).astype(int)
            got = resize_bilinear(a, *size).astype(int)
            assert got.shape == ref.shape
            assert np.abs(got - ref).max() <= 1


def test_preprocess_is_training_resize():
    im = Image.fromarray(_page(5, seed=1))
    x = preprocess(im, 640)
    assert x.shape == (1, 3, 640, 640) and x.dtype == np.float32
    ref = np.asarray(im.resize((640, 640), Image.BILINEAR), np.float32) / 255.0
    ref = ((ref - MEAN) / STD).transpose(2, 0, 1)[None]
    assert np.abs(x - ref).max() <= 1.5 / 255 / STD.min()


def test_same_size_is_identity():
    a = _page(256, seed=2)[:640, :640]
    assert np.array_equal(resize_bilinear(a, 640, 640), a)
