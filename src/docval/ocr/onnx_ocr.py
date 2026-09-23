"""PP-OCR (v5/v6) text detection + recognition with onnxruntime.

Pre/post-processing is implemented here (not taken from PaddleOCR) because the
browser port needs exactly this logic; the PaddleOCR Python pipeline is only a
reference in the report. Models: official ONNX exports from Hugging Face
(PaddlePaddle/<name>_onnx: inference.onnx + inference.yml with the dictionary).
"""

from __future__ import annotations

import math
from pathlib import Path

import cv2
import numpy as np
import yaml
from PIL import Image

from ..zones.synthetic import to_rgb


def _session(path: Path):
    import onnxruntime as ort

    so = ort.SessionOptions()
    so.log_severity_level = 3
    return ort.InferenceSession(str(path), so, providers=["CPUExecutionProvider"])


def pil_to_bgr(im: Image.Image) -> np.ndarray:
    return np.asarray(to_rgb(im))[:, :, ::-1].copy()


class Recognizer:
    """CTC text recognition. Input: list of BGR crops (one text line each)."""

    def __init__(self, model_dir: Path, max_width: int = 3200):
        model_dir = Path(model_dir)
        meta = yaml.safe_load(open(model_dir / "inference.yml", encoding="utf-8"))
        chars = meta["PostProcess"]["character_dict"]
        # vocabulary: blank + dict + space
        self.vocab = ["<blank>"] + [str(c) for c in chars] + [" "]
        shape = meta["PreProcess"]["transform_ops"]
        self.h, self.min_w = 48, 320
        for op in shape:
            if "RecResizeImg" in op:
                _, self.h, self.min_w = op["RecResizeImg"]["image_shape"]
        self.max_width = max_width
        self.sess = _session(model_dir / "inference.onnx")
        self.input = self.sess.get_inputs()[0].name
        self.name = meta.get("Global", {}).get("model_name", model_dir.name)

    def _prep(self, bgr: np.ndarray, target_w: int) -> np.ndarray:
        h, w = bgr.shape[:2]
        rw = min(target_w, int(math.ceil(self.h * w / max(1, h))))
        r = cv2.resize(bgr, (max(1, rw), self.h)).astype(np.float32)
        r = (r / 255.0 - 0.5) / 0.5
        out = np.zeros((3, self.h, target_w), dtype=np.float32)
        out[:, :, :rw] = r.transpose(2, 0, 1)
        return out

    def __call__(self, crops: list[np.ndarray]) -> list[tuple[str, float]]:
        results = []
        for bgr in crops:  # batch 1: widths differ a lot, keeps it simple and exact
            h, w = bgr.shape[:2]
            target_w = min(self.max_width, int(self.h * max(self.min_w / self.h, w / max(1, h))))
            x = self._prep(bgr, target_w)[None]
            prob = self.sess.run(None, {self.input: x})[0][0]  # (T, C), softmaxed
            idx = prob.argmax(1)
            conf = prob.max(1)
            text, scores, prev = [], [], -1
            for t, k in enumerate(idx):
                if k != prev and k != 0:
                    text.append(self.vocab[k] if k < len(self.vocab) else "")
                    scores.append(float(conf[t]))
                prev = k
            results.append(("".join(text), float(np.mean(scores)) if scores else 0.0))
        return results


class Detector:
    """DB text detection. Returns quadrilaterals (4x2, pixel coords)."""

    def __init__(self, model_dir: Path, limit_side_len: int = 960, limit_type: str = "max",
                 thresh: float | None = None, box_thresh: float | None = None,
                 unclip_ratio: float | None = None):
        model_dir = Path(model_dir)
        meta = yaml.safe_load(open(model_dir / "inference.yml", encoding="utf-8"))
        pp = meta.get("PostProcess", {})
        self.thresh = thresh if thresh is not None else pp.get("thresh", 0.3)
        self.box_thresh = box_thresh if box_thresh is not None else pp.get("box_thresh", 0.6)
        self.unclip_ratio = unclip_ratio if unclip_ratio is not None else pp.get("unclip_ratio", 1.5)
        self.limit_side_len, self.limit_type = limit_side_len, limit_type
        self.sess = _session(model_dir / "inference.onnx")
        self.input = self.sess.get_inputs()[0].name
        self.name = meta.get("Global", {}).get("model_name", model_dir.name)

    def _resize(self, bgr):
        h, w = bgr.shape[:2]
        side = max(h, w) if self.limit_type == "max" else min(h, w)
        ratio = 1.0
        if (self.limit_type == "max" and side > self.limit_side_len) or \
                (self.limit_type == "min" and side < self.limit_side_len):
            ratio = self.limit_side_len / side
        nh = max(32, int(round(h * ratio / 32)) * 32)
        nw = max(32, int(round(w * ratio / 32)) * 32)
        return cv2.resize(bgr, (nw, nh)), nh / h, nw / w

    def __call__(self, bgr: np.ndarray) -> list[np.ndarray]:
        import pyclipper

        img, ry, rx = self._resize(bgr)
        x = img.astype(np.float32) / 255.0
        x = (x - np.array([0.485, 0.456, 0.406], np.float32)) / np.array([0.229, 0.224, 0.225], np.float32)
        prob = self.sess.run(None, {self.input: x.transpose(2, 0, 1)[None]})[0][0, 0]
        mask = (prob > self.thresh).astype(np.uint8)
        contours, _ = cv2.findContours(mask, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        boxes = []
        for c in contours[:3000]:
            rect = cv2.minAreaRect(c)
            if min(rect[1]) < 3:
                continue
            pts = cv2.boxPoints(rect)
            # score = mean probability inside the box
            x1, y1 = np.floor(pts.min(0)).astype(int).clip(0)
            x2, y2 = np.ceil(pts.max(0)).astype(int)
            x2, y2 = min(x2, prob.shape[1] - 1), min(y2, prob.shape[0] - 1)
            m = np.zeros((y2 - y1 + 1, x2 - x1 + 1), np.uint8)
            cv2.fillPoly(m, [(pts - [x1, y1]).astype(np.int32)], 1)
            if m.sum() == 0 or cv2.mean(prob[y1:y2 + 1, x1:x2 + 1], m)[0] < self.box_thresh:
                continue
            # unclip (expand) the shrunk DB polygon
            area, length = cv2.contourArea(pts), cv2.arcLength(pts, True)
            if length == 0:
                continue
            off = pyclipper.PyclipperOffset()
            off.AddPath(pts.astype(np.int64).tolist(), pyclipper.JT_ROUND, pyclipper.ET_CLOSEDPOLYGON)
            exp = off.Execute(area * self.unclip_ratio / length)
            if not exp:
                continue
            rect2 = cv2.minAreaRect(np.array(exp[0], np.float32))
            if min(rect2[1]) < 5:
                continue
            q = cv2.boxPoints(rect2)
            q[:, 0] = (q[:, 0] / rx).clip(0, bgr.shape[1] - 1)
            q[:, 1] = (q[:, 1] / ry).clip(0, bgr.shape[0] - 1)
            boxes.append(order_quad(q))
        # reading order: top-to-bottom, then left-to-right on the same line
        boxes.sort(key=lambda q: (round(q[:, 1].mean() / 10), q[:, 0].min()))
        return boxes


def order_quad(pts: np.ndarray) -> np.ndarray:
    s, d = pts.sum(1), np.diff(pts, axis=1).ravel()
    return np.array([pts[s.argmin()], pts[d.argmin()], pts[s.argmax()], pts[d.argmax()]], np.float32)


def crop_quad(bgr: np.ndarray, q: np.ndarray) -> np.ndarray:
    w = int(max(np.linalg.norm(q[0] - q[1]), np.linalg.norm(q[2] - q[3])))
    h = int(max(np.linalg.norm(q[0] - q[3]), np.linalg.norm(q[1] - q[2])))
    w, h = max(w, 1), max(h, 1)
    M = cv2.getPerspectiveTransform(q, np.array([[0, 0], [w, 0], [w, h], [0, h]], np.float32))
    out = cv2.warpPerspective(bgr, M, (w, h), borderMode=cv2.BORDER_REPLICATE)
    if h / w >= 1.5:  # vertical text
        out = np.rot90(out)
    return out


class OcrEngine:
    """One PP-OCR version: det + rec, both ONNX."""

    def __init__(self, name: str, det_dir: Path, rec_dir: Path, det_kwargs: dict | None = None):
        self.name = name
        self.det = Detector(det_dir, **(det_kwargs or {}))
        self.rec = Recognizer(rec_dir)

    def recognize(self, bgr: np.ndarray) -> tuple[str, float]:
        return self.rec([bgr])[0]

    def detect_recognize(self, bgr: np.ndarray) -> list[dict]:
        quads = self.det(bgr)
        if not quads:
            return []
        texts = self.rec([crop_quad(bgr, q) for q in quads])
        return [{"quad": q.tolist(), "text": t, "score": s} for q, (t, s) in zip(quads, texts)]


def pad_crop(im: Image.Image, xyxy, pad: float) -> Image.Image:
    x1, y1, x2, y2 = xyxy
    px, py = (x2 - x1) * pad, (y2 - y1) * pad
    box = (max(0, int(x1 - px)), max(0, int(y1 - py)),
           min(im.width, int(math.ceil(x2 + px))), min(im.height, int(math.ceil(y2 + py))))
    return im.crop(box)
