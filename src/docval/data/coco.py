"""COCO loading, validation and box helpers.

Kept free of numpy/Python-specific tricks so the box logic can be ported to JS.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

# Standard COCO image keys; anything else is a candidate custom attribute.
STANDARD_IMAGE_KEYS = {
    "id", "file_name", "width", "height", "license",
    "flickr_url", "coco_url", "date_captured",
}
STANDARD_ANN_KEYS = {
    "id", "image_id", "category_id", "bbox", "area",
    "segmentation", "iscrowd",
}


@dataclass
class Issue:
    kind: str
    message: str
    image_id: object = None
    ann_id: object = None
    file_name: str | None = None


@dataclass
class ValidationResult:
    issues: list[Issue] = field(default_factory=list)

    def add(self, kind, message, **kw):
        self.issues.append(Issue(kind, message, **kw))

    def count_by_kind(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for i in self.issues:
            counts[i.kind] = counts.get(i.kind, 0) + 1
        return counts


def load_coco(path: str | Path) -> dict:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    for key in ("images", "annotations", "categories"):
        if key not in data or not isinstance(data[key], list):
            raise ValueError(f"COCO file lacks list '{key}'")
    return data


def xywh_to_xyxy(bbox):
    x, y, w, h = bbox
    return [x, y, x + w, y + h]


def normalize_xywh(bbox, width, height):
    """Return bbox as normalized [x1, y1, x2, y2] in 0..1 (not clipped)."""
    x, y, w, h = bbox
    return [x / width, y / height, (x + w) / width, (y + h) / height]


def clip01(v):
    if v < 0:
        return 0.0
    if v > 1:
        return 1.0
    return v


def box_center(xyxy):
    return [(xyxy[0] + xyxy[2]) / 2, (xyxy[1] + xyxy[3]) / 2]


def validate_coco(data: dict, image_dir: str | Path | None = None,
                  tolerance_px: float = 1.0,
                  expected_classes: list[str] | None = None) -> ValidationResult:
    """Structural and geometric checks. Never modifies `data`."""
    res = ValidationResult()

    # duplicate ids / file names
    seen_img: dict = {}
    seen_fn: dict = {}
    for img in data["images"]:
        iid = img.get("id")
        if iid in seen_img:
            res.add("duplicate_image_id", f"image id {iid} occurs more than once",
                    image_id=iid, file_name=img.get("file_name"))
        seen_img[iid] = img
        fn = img.get("file_name")
        if fn in seen_fn:
            res.add("duplicate_file_name", f"file_name {fn} occurs more than once",
                    image_id=iid, file_name=fn)
        seen_fn[fn] = img
        if not img.get("width") or not img.get("height"):
            res.add("missing_image_size", "width/height missing or 0",
                    image_id=iid, file_name=fn)
        if image_dir is not None and fn is not None:
            if not (Path(image_dir) / fn).is_file():
                res.add("missing_image_file", f"{fn} not found in image dir",
                        image_id=iid, file_name=fn)

    seen_cat: dict = {}
    for cat in data["categories"]:
        cid = cat.get("id")
        if cid in seen_cat:
            res.add("duplicate_category_id", f"category id {cid} occurs more than once")
        seen_cat[cid] = cat
    if expected_classes is not None:
        names = [c.get("name") for c in data["categories"]]
        for name in expected_classes:
            if name not in names:
                res.add("expected_class_missing", f"class '{name}' not in categories")

    seen_ann: set = set()
    for ann in data["annotations"]:
        aid = ann.get("id")
        iid = ann.get("image_id")
        if aid in seen_ann:
            res.add("duplicate_annotation_id", f"annotation id {aid} occurs more than once",
                    ann_id=aid, image_id=iid)
        seen_ann.add(aid)
        img = seen_img.get(iid)
        fn = img.get("file_name") if img else None
        if ann.get("category_id") not in seen_cat:
            res.add("unknown_category", f"category_id {ann.get('category_id')} unknown",
                    ann_id=aid, image_id=iid, file_name=fn)
        if img is None:
            res.add("unknown_image", f"image_id {iid} unknown", ann_id=aid, image_id=iid)
        bbox = ann.get("bbox")
        if not isinstance(bbox, list) or len(bbox) != 4:
            res.add("malformed_bbox", f"bbox {bbox!r} is not [x,y,w,h]",
                    ann_id=aid, image_id=iid, file_name=fn)
            continue
        x, y, w, h = bbox
        if w <= 0 or h <= 0:
            res.add("zero_area_bbox", f"bbox {bbox} has w or h <= 0",
                    ann_id=aid, image_id=iid, file_name=fn)
        if img is not None and img.get("width") and img.get("height"):
            W, H = img["width"], img["height"]
            t = tolerance_px
            if x < -t or y < -t or x + w > W + t or y + h > H + t:
                res.add("bbox_out_of_image",
                        f"bbox {bbox} exceeds image {W}x{H}",
                        ann_id=aid, image_id=iid, file_name=fn)
    return res
