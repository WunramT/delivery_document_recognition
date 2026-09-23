"""RF-DETR inference with onnxruntime (the model that later runs in the browser).

Pre/post-processing mirrors rfdetr 1.10 (detr.py / models/postprocess.py):
  RGB -> [0,1] -> bilinear resize to res x res (no letterbox) -> ImageNet norm,
  sigmoid(logits) without background slot -> top-k over queries x classes,
  boxes cxcywh (normalized) -> xyxy.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image

MEAN = np.array([0.485, 0.456, 0.406], np.float32)
STD = np.array([0.229, 0.224, 0.225], np.float32)


def preprocess(im: Image.Image, res: int) -> np.ndarray:
    import cv2

    a = np.asarray(im.convert("RGB"), dtype=np.float32) / 255.0
    a = cv2.resize(a, (res, res), interpolation=cv2.INTER_LINEAR)
    a = (a - MEAN) / STD
    return a.transpose(2, 0, 1)[None].astype(np.float32)


def sigmoid(x):
    return 1.0 / (1.0 + np.exp(-x))


def postprocess(dets: np.ndarray, logits: np.ndarray, num_classes: int, num_select: int = 300,
                threshold: float = 0.0) -> list[dict]:
    """dets (Q,4) cxcywh normalized, logits (Q,C+1). Returns normalized xyxy boxes."""
    prob = sigmoid(logits[:, :num_classes])
    flat = prob.reshape(-1)
    k = min(num_select, flat.shape[0])
    idx = np.argsort(-flat, kind="stable")[:k]
    out = []
    for i in idx:
        s = float(flat[i])
        if s <= threshold:
            break
        q, c = divmod(int(i), num_classes)
        cx, cy, w, h = dets[q]
        box = [cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2]
        box = [min(1.0, max(0.0, float(v))) for v in box]
        out.append({"cls_id": c, "score": s, "box": box})
    return out


def nms_per_class(dets: list[dict], iou_thr: float = 0.7) -> list[dict]:
    """DETR needs no NMS in principle; top-k over classes can emit the same query
    twice for different classes, which is kept. Duplicate boxes of the same class
    are suppressed here (rare, cheap)."""
    keep = []
    for d in sorted(dets, key=lambda x: -x["score"]):
        if all(d["cls_id"] != k["cls_id"] or iou(d["box"], k["box"]) < iou_thr for k in keep):
            keep.append(d)
    return keep


def iou(a, b) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    ua = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / ua if ua > 0 else 0.0


class OnnxDetector:
    def __init__(self, model_dir: Path, min_score: float = 0.05):
        import onnxruntime as ort

        meta = json.loads((Path(model_dir) / "detector.json").read_text())
        self.classes = meta["classes"]
        self.res = meta["resolution"]
        self.min_score = min_score
        so = ort.SessionOptions()
        so.log_severity_level = 3
        self.sess = ort.InferenceSession(str(Path(model_dir) / "detector.onnx"), so,
                                         providers=["CPUExecutionProvider"])
        self.input = self.sess.get_inputs()[0].name
        self.outputs = [o.name for o in self.sess.get_outputs()]

    def raw(self, im: Image.Image):
        res = self.sess.run(None, {self.input: preprocess(im, self.res)})
        named = dict(zip(self.outputs, res))
        return named.get("dets", res[0])[0], named.get("labels", res[1])[0]

    def __call__(self, im: Image.Image) -> list[dict]:
        dets, logits = self.raw(im)
        out = nms_per_class(postprocess(dets, logits, len(self.classes), threshold=self.min_score))
        for d in out:
            d["cls"] = self.classes[d["cls_id"]]
        return out
