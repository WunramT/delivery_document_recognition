"""Page records: image path, doc type, group, GT boxes and GT tour number.

Everything downstream (split, zones, eval) works on these records, so the
label sources configured in config.yaml are resolved in exactly one place.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..config import resolve
from .coco import find_image, load_coco
from .dataset_info import flatten
from .labels import base_stem, match_to_coco, read_label_table


@dataclass
class Box:
    cls: str
    xyxy: list[float]          # absolute pixels, clipped to the image
    ann_id: object = None
    clipped: bool = False

    def norm(self, w: int, h: int) -> list[float]:
        return [self.xyxy[0] / w, self.xyxy[1] / h, self.xyxy[2] / w, self.xyxy[3] / h]


@dataclass
class Page:
    image_id: object
    file_name: str             # as in COCO
    path: Path | None
    width: int
    height: int
    doc_type: str | None = None
    source_pdf: str | None = None
    source_page: int | None = None
    group: str | None = None   # split group (filled by split.assign_groups)
    tour_number: str | None = None
    boxes: list[Box] = field(default_factory=list)

    def boxes_of(self, cls: str) -> list[Box]:
        return [b for b in self.boxes if b.cls == cls]


def clip_box(bbox_xywh, w, h) -> tuple[list[float], bool]:
    x, y, bw, bh = bbox_xywh
    x1, y1, x2, y2 = x, y, x + bw, y + bh
    c = [max(0.0, min(w, x1)), max(0.0, min(h, y1)), max(0.0, min(w, x2)), max(0.0, min(h, y2))]
    return c, c != [x1, y1, x2, y2]


def load_pages(cfg: dict) -> tuple[list[Page], dict]:
    """Return (pages, info). Input files are only read."""
    coco_path = resolve(cfg["paths"]["coco"])
    image_dir = resolve(cfg["paths"]["images"])
    data = load_coco(coco_path)
    cats = {c["id"]: c["name"] for c in data["categories"]}
    classes = cfg["classes"]
    info = {"coco": str(coco_path), "clipped_boxes": 0, "dropped_boxes": 0,
            "classes_in_coco": [c for c in classes if c in cats.values()],
            "classes_missing": [c for c in classes if c not in cats.values()]}

    pages: dict = {}
    for img in data["images"]:
        pages[img["id"]] = Page(img["id"], img["file_name"],
                                find_image(img["file_name"], image_dir, coco_path.parent),
                                img["width"], img["height"])
    for a in data["annotations"]:
        p = pages.get(a.get("image_id"))
        name = cats.get(a.get("category_id"))
        if p is None or name not in classes:
            continue
        xyxy, clipped = clip_box(a["bbox"], p.width, p.height)
        if xyxy[2] - xyxy[0] < 1 or xyxy[3] - xyxy[1] < 1:
            info["dropped_boxes"] += 1
            continue
        info["clipped_boxes"] += int(clipped)
        p.boxes.append(Box(name, xyxy, a.get("id"), clipped))

    file_names = [p.file_name for p in pages.values()]
    by_fn = {p.file_name: p for p in pages.values()}

    # doc type
    dcfg = cfg["labels"]["doc_type"]
    src = dcfg.get("source", "csv")
    if src == "csv":
        values, tinfo = read_label_table(resolve(dcfg["csv"]), dcfg.get("csv_value_column"),
                                         dcfg.get("csv_file_column"))
        matched, stats = match_to_coco(values, file_names)
        records = tinfo.pop("records")
        # extra columns (source_pdf/source_page) for grouping
        stem_rec = {}
        for fn, r in records.items():
            stem_rec[base_stem(fn)] = r
        for fn, p in by_fn.items():
            p.doc_type = matched.get(fn)
            r = records.get(fn) or stem_rec.get(base_stem(fn)) or {}
            p.source_pdf = r.get("source_pdf") or None
            sp = r.get("source_page") or ""
            p.source_page = int(sp) if sp.isdigit() else None
        info["doc_type_unmatched"] = len(stats["unmatched_coco"])
    elif src == "coco_attribute":
        key = dcfg["coco_attribute"]
        for img in data["images"]:
            v = flatten(img).get(key)
            pages[img["id"]].doc_type = str(v) if v not in (None, "") else None
    else:
        raise ValueError(f"unsupported labels.doc_type.source: {src}")

    # tour number GT
    tcfg = cfg["labels"]["tour_number"]
    if tcfg.get("source", "csv") == "csv":
        values, _ = read_label_table(resolve(tcfg["csv"]), "tour_number", "file_name")
        # with several exports the file names repeat -> the global CSV only matches exactly
        # (a stem match would put the tour numbers of export A onto the pages of export B)
        matched, _ = match_to_coco(values, file_names, by_stem=not cfg.get("_exports"))
        if tcfg.get("export_csv"):  # per-export tour_numbers.csv fill in what the main CSV lacks
            ev, _ = read_label_table(resolve(tcfg["export_csv"]), "tour_number", "file_name")
            em, _ = match_to_coco(ev, file_names)
            matched = {**em, **matched}
        for fn, v in matched.items():
            by_fn[fn].tour_number = v
    else:
        key = tcfg["coco_attribute"]
        tour_ids = {cid for cid, n in cats.items() if n == "tour_nummer"}
        for a in data["annotations"]:
            if a.get("category_id") in tour_ids:
                v = flatten(a).get(key)
                if isinstance(v, str) and v.strip():
                    pages[a["image_id"]].tour_number = v.strip()
    # "?" = unreadable in GT: kept, an auto-accepted OCR result there counts as error

    out = sorted(pages.values(), key=lambda p: (p.source_pdf or "", p.source_page or 0, p.file_name))
    return out, info
