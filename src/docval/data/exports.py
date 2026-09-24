"""Several label exports side by side: labels/exports/<name>/{_annotations.coco.json, images/,
page_types.csv, tour_numbers.csv?}. They are merged into artifacts/merged/ (JSON/CSV only,
images stay where they are) and the config paths are pointed at the merged dataset.

File names become "<export>/<file_name in the export>", so names never collide, and the
source PDF is prefixed with the export name, so split groups never span two exports.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from ..config import artifacts, resolve
from .coco import find_image, load_coco
from .labels import match_to_coco, read_label_table

COCO_NAMES = ("_annotations.coco.json", "annotations.json", "coco.json")


def find_exports(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    out = []
    for d in sorted(p for p in root.iterdir() if p.is_dir()):
        if any((d / n).is_file() for n in COCO_NAMES):
            out.append(d)
    return out


def _coco_file(d: Path) -> Path:
    return next(d / n for n in COCO_NAMES if (d / n).is_file())


def merge_exports(cfg: dict, exports: list[Path], out: Path) -> dict:
    classes = cfg["classes"]
    images, anns, cats = [], [], {}
    for c in classes:
        cats[c] = len(cats) + 1
    type_rows, tour_rows = [], []
    info = {"exports": [], "duplicates": []}
    seen_pages: dict = {}
    iid = aid = 1
    for d in exports:
        name = d.name
        data = load_coco(_coco_file(d))
        cat_name = {c["id"]: c["name"] for c in data["categories"]}
        for n in cat_name.values():
            if n not in cats:
                cats[n] = len(cats) + 1
        id_map, fn_map = {}, {}
        n_img = 0
        for img in data["images"]:
            p = find_image(img["file_name"], d / "images", d)
            rel = f"{name}/{img['file_name']}" if p is None else p.relative_to(d.parent).as_posix()
            id_map[img["id"]] = iid
            fn_map[img["file_name"]] = rel
            images.append({"id": iid, "file_name": rel, "width": img["width"], "height": img["height"],
                           "export": name})
            iid += 1
            n_img += 1
        n_ann = 0
        for a in data["annotations"]:
            if a.get("image_id") not in id_map:
                continue
            anns.append({**{k: v for k, v in a.items() if k not in ("id", "image_id", "category_id")},
                         "id": aid, "image_id": id_map[a["image_id"]],
                         "category_id": cats[cat_name[a["category_id"]]]})
            aid += 1
            n_ann += 1
        # doc types (+ source_pdf/source_page for grouping)
        values, tinfo = read_label_table(d / "page_types.csv")
        records = tinfo.pop("records")
        matched, stats = match_to_coco(values, list(fn_map))
        rec_by_match = {}
        for fn_csv, r in records.items():
            m, _ = match_to_coco({fn_csv: "x"}, list(fn_map))
            for coco_fn in m:
                rec_by_match[coco_fn] = r
        for coco_fn, rel in fn_map.items():
            r = rec_by_match.get(coco_fn, {})
            pdf = r.get("source_pdf") or ""
            page = r.get("source_page") or ""
            key = (pdf, page)
            if pdf and key in seen_pages:
                info["duplicates"].append(f"{rel} = {seen_pages[key]} ({pdf} Seite {page})")
            elif pdf:
                seen_pages[key] = rel
            type_rows.append([rel, matched.get(coco_fn, ""), f"{name}:{pdf}" if pdf else name, page])
        # tour numbers of this export (optional)
        tv, _ = read_label_table(d / "tour_numbers.csv", "tour_number", "file_name")
        tm, _ = match_to_coco(tv, list(fn_map))
        tour_rows += [[fn_map[k], v] for k, v in tm.items()]
        info["exports"].append({"name": name, "images": n_img, "annotations": n_ann,
                                "doc_types": len(matched), "doc_types_missing": len(stats["unmatched_coco"]),
                                "tour_numbers": len(tm)})
    out.mkdir(parents=True, exist_ok=True)
    coco = {"images": images, "annotations": anns,
            "categories": [{"id": i, "name": n, "supercategory": "none"} for n, i in cats.items()]}
    (out / "_annotations.coco.json").write_text(json.dumps(coco), encoding="utf-8")
    with open(out / "page_types.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["file_name", "doc_type", "source_pdf", "source_page"])
        w.writerows(type_rows)
    with open(out / "tour_numbers.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["file_name", "tour_number"])
        w.writerows(tour_rows)
    (out / "merge_info.json").write_text(json.dumps(info, indent=2, ensure_ascii=False), encoding="utf-8")
    return info


def apply_exports(cfg: dict, log=None) -> dict:
    """If paths.exports contains export folders: merge them and point the config at
    the merged dataset. Otherwise the config is returned unchanged (single export)."""
    root = resolve(cfg["paths"].get("exports") or "labels/exports")
    exports = find_exports(root)
    if not exports:
        return cfg
    out = artifacts(cfg, "merged")
    info = merge_exports(cfg, exports, out)
    cfg["paths"]["coco"] = str(out / "_annotations.coco.json")
    cfg["paths"]["images"] = str(root)          # file_name = "<export>/images/x.png"
    cfg["labels"]["doc_type"]["csv"] = str(out / "page_types.csv")
    cfg["labels"]["doc_type"]["csv_file_column"] = "file_name"
    cfg["labels"]["doc_type"]["csv_value_column"] = "doc_type"
    # tour numbers: the global labels/tour_numbers.csv (review page) wins, the
    # per-export files fill in what it does not contain
    cfg["labels"]["tour_number"]["export_csv"] = str(out / "tour_numbers.csv")
    cfg["_exports"] = info
    if log:
        log(f"[exports] {len(exports)} Export(s) aus {root}: " + ", ".join(
            f"{e['name']} ({e['images']} Seiten)" for e in info["exports"])
            + (f"; WARNUNG doppelte Seiten: {len(info['duplicates'])}" if info["duplicates"] else ""))
        for e in info["exports"]:
            if e["doc_types_missing"]:
                log(f"[exports] WARNUNG {e['name']}: {e['doc_types_missing']} von {e['images']} Seiten ohne "
                    "Dokumenttyp - page_types.csv fehlt oder gehört zu einem anderen Export")
    return cfg
