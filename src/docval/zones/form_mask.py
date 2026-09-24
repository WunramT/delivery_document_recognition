"""Find the signature fields of a form (CMR 22/23/24) from its printed frame lines and
mask the pre-printed ones (22, 23) including their border.

Classical CV only (OpenCV, also available as OpenCV.js for the browser):
  binarize -> keep long horizontal/vertical lines -> cells = regions enclosed by lines
  -> bottom row with >= min_cells cells of plausible width -> sort left to right.
"""

from __future__ import annotations

import cv2
import numpy as np
from PIL import Image

from .synthetic import to_rgb


def find_field_row(gray: np.ndarray, cfg: dict) -> dict:
    """gray: full page (uint8). Returns {"cells": [[x1,y1,x2,y2] normalized, left->right],
    "found": bool, "reason": str}."""
    H, W = gray.shape
    y0, y1 = int(cfg.get("search_y", [0.6, 1.0])[0] * H), int(cfg.get("search_y", [0.6, 1.0])[1] * H)
    roi = gray[y0:y1]
    ink = cv2.adaptiveThreshold(roi, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 31, 15)
    k = max(10, int(W * cfg.get("line_min_frac", 0.08)))
    horiz = cv2.morphologyEx(ink, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (k, 1)))
    kv = max(10, int(H * cfg.get("line_min_frac", 0.08) * 0.5))
    vert = cv2.morphologyEx(ink, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1, kv)))
    grid = cv2.dilate(cv2.bitwise_or(horiz, vert), np.ones((3, 3), np.uint8), iterations=2)
    n, _, stats, _ = cv2.connectedComponentsWithStats(cv2.bitwise_not(grid), connectivity=4)
    cells = []
    for i in range(1, n):
        x, y, w, h, _area = stats[i]
        if x == 0 or x + w >= W or y == 0:
            continue  # page background or a cell cut off by the search window
        fw, fh = w / W, h / H
        if cfg.get("cell_min_w", 0.18) <= fw <= cfg.get("cell_max_w", 0.5) and fh >= cfg.get("cell_min_h", 0.04):
            cells.append([float(x / W), float((y + y0) / H), float((x + w) / W), float((y + h + y0) / H)])

    # a framed stamp inside a field is a cell too -> keep only cells not inside another one
    def inside(a, b):
        return a is not b and a[0] >= b[0] and a[1] >= b[1] and a[2] <= b[2] and a[3] <= b[3]

    cells = [c for c in cells if not any(inside(c, o) for o in cells)]
    # group into rows by vertical overlap, take the lowest row with enough cells
    rows: list[list] = []
    for c in sorted(cells, key=lambda c: c[1]):
        for r in rows:
            ov = min(r[0][3], c[3]) - max(r[0][1], c[1])
            if ov > 0.5 * min(r[0][3] - r[0][1], c[3] - c[1]):
                r.append(c)
                break
        else:
            rows.append([c])
    need = cfg.get("min_cells", 3)
    good = [sorted(r, key=lambda c: c[0]) for r in rows if len(r) >= need]
    if not good:
        return {"cells": [], "found": False,
                "reason": f"keine Zeile mit {need} Feldern gefunden ({len(cells)} Kandidaten)"}
    row = max(good, key=lambda r: r[0][3])  # lowest row
    return {"cells": row, "found": True, "reason": f"{len(row)} Felder gefunden"}


def mask_fields(im: Image.Image, cfg: dict) -> tuple[Image.Image, dict]:
    """Return (masked RGB image, info). info["masked"]: normalized boxes that were filled."""
    rgb = to_rgb(im)
    gray = np.asarray(rgb.convert("L"))
    res = find_field_row(gray, cfg)
    res["masked"] = []
    if not res["found"]:
        return rgb, res
    W, H = rgb.size
    arr = np.asarray(rgb).copy()
    b = cfg.get("border_px", 6)
    color = (255, 255, 255) if cfg.get("fill", "white") == "white" else (0, 0, 0)
    for idx in cfg.get("mask_fields", [0, 1]):
        if idx >= len(res["cells"]):
            continue
        x1, y1, x2, y2 = res["cells"][idx]
        px1, py1 = max(0, int(x1 * W) - b), max(0, int(y1 * H) - b)
        px2, py2 = min(W, int(x2 * W) + b), min(H, int(y2 * H) + b)
        arr[py1:py2, px1:px2] = color
        res["masked"].append([px1 / W, py1 / H, px2 / W, py2 / H])
    return Image.fromarray(arr), res


def applies(cfg: dict, doc_type: str | None) -> bool:
    m = cfg.get("form_mask") or {}
    return bool(m.get("enabled")) and doc_type in (m.get("doc_types") or [])


def center_in_any(box: list[float], areas: list[list[float]]) -> bool:
    cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    return any(a[0] <= cx <= a[2] and a[1] <= cy <= a[3] for a in areas)
