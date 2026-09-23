"""Detection metrics (greedy IoU matching, AP50) and small-sample statistics."""

from __future__ import annotations

import math

from ..detect.onnx_detector import iou


def match(gts: list[list[float]], preds: list[dict], iou_thr: float) -> tuple[list, list]:
    """Greedy matching by descending score. preds: [{"box", "score"}].

    Returns (pred_is_tp in pred order sorted by score, matched_gt_index per pred or -1).
    """
    order = sorted(range(len(preds)), key=lambda i: -preds[i]["score"])
    used = [False] * len(gts)
    tp, idx = [False] * len(preds), [-1] * len(preds)
    for i in order:
        best, best_iou = -1, iou_thr
        for j, g in enumerate(gts):
            if used[j]:
                continue
            v = iou(preds[i]["box"], g)
            if v >= best_iou:
                best, best_iou = j, v
        if best >= 0:
            used[best] = True
            tp[i], idx[i] = True, best
    return tp, idx


def average_precision(scored: list[tuple[float, bool]], n_gt: int) -> float | None:
    """COCO-style 101-point interpolated AP from (score, is_tp) over all images."""
    if n_gt == 0:
        return None
    scored = sorted(scored, key=lambda x: -x[0])
    tp = fp = 0
    prec, rec = [], []
    for _, is_tp in scored:
        tp += int(is_tp)
        fp += int(not is_tp)
        prec.append(tp / (tp + fp))
        rec.append(tp / n_gt)
    for i in range(len(prec) - 2, -1, -1):
        prec[i] = max(prec[i], prec[i + 1])
    total = 0.0
    for t in range(101):
        r = t / 100
        p = 0.0
        for k in range(len(rec)):
            if rec[k] >= r:
                p = prec[k]
                break
        total += p
    return total / 101


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float] | None:
    """95 % Wilson interval for a proportion k/n (honest for tiny n)."""
    if n == 0:
        return None
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, c - h), min(1.0, c + h)


def ratio(k: int, n: int) -> dict:
    return {"k": k, "n": n, "value": (k / n) if n else None, "ci95": wilson(k, n)}
