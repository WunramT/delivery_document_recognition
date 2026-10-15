"""Write the split in the folder layout rfdetr expects.

artifacts/splits/detector/{train,valid,test}/_annotations.coco.json + image links.
Images are symlinked (fallback: hardlink, then copy on systems without symlinks).
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path


def link(src: Path, dst: Path) -> str:
    if dst.exists() or dst.is_symlink():
        dst.unlink()
    try:
        os.symlink(src.resolve(), dst)
        return "symlink"
    except (OSError, NotImplementedError):
        pass
    try:
        os.link(src, dst)
        return "hardlink"
    except OSError:
        shutil.copy2(src, dst)
        return "copy"


def write_rfdetr_dataset(pages, assign: dict[str, str], classes: list[str], out: Path,
                         mask_cfg: dict | None = None) -> dict:
    """classes: detector classes in label order (category ids 1..n).

    mask_cfg (config `form_mask`): pages of these doc types are written as masked
    copies (pre-printed fields blanked); GT boxes centered in a masked area are dropped.
    """
    from PIL import Image

    from ..zones.form_mask import center_in_any, mask_fields

    mask_on = bool(mask_cfg and mask_cfg.get("enabled"))
    mask_info = {"pages": 0, "found": 0, "not_found": [], "dropped_boxes": 0}
    cat_id = {c: i + 1 for i, c in enumerate(classes)}
    methods: dict[str, int] = {}
    info = {}
    for split in ("train", "valid", "test"):
        d = out / split
        if d.exists():
            shutil.rmtree(d)
        d.mkdir(parents=True)
        images, anns = [], []
        aid = 1
        for p in pages:
            if assign.get(p.file_name) != split or p.path is None:
                continue
            name = f"{p.image_id}_{Path(p.file_name).name}"
            masked = []
            if mask_on and p.doc_type in (mask_cfg.get("doc_types") or []):
                mask_info["pages"] += 1
                im, minfo = mask_fields(Image.open(p.path), mask_cfg)
                if minfo["found"]:
                    mask_info["found"] += 1
                    masked = minfo["masked"]
                else:
                    mask_info["not_found"].append(p.file_name)
                name = str(Path(name).with_suffix(".png"))
                im.save(d / name)
                m = "masked_copy"
            else:
                m = link(p.path, d / name)
            methods[m] = methods.get(m, 0) + 1
            images.append({"id": p.image_id, "file_name": name, "width": p.width, "height": p.height,
                           "orig_file_name": p.file_name, "doc_type": p.doc_type})
            for b in p.boxes:
                if b.cls not in cat_id:
                    continue
                if masked and center_in_any(b.norm(p.width, p.height), masked):
                    mask_info["dropped_boxes"] += 1
                    continue
                x1, y1, x2, y2 = b.xyxy
                anns.append({"id": aid, "image_id": p.image_id, "category_id": cat_id[b.cls],
                             "bbox": [x1, y1, x2 - x1, y2 - y1], "area": (x2 - x1) * (y2 - y1),
                             "iscrowd": 0})
                aid += 1
        coco = {"images": images, "annotations": anns,
                "categories": [{"id": cat_id[c], "name": c, "supercategory": "none"} for c in classes]}
        (d / "_annotations.coco.json").write_text(json.dumps(coco, indent=1), encoding="utf-8")
        info[split] = {"images": len(images), "annotations": len(anns)}
    (out / "classes.json").write_text(json.dumps(classes), encoding="utf-8")
    info["link_methods"] = methods
    info["form_mask"] = mask_info
    return info


def write_final_dataset(src: Path, dst: Path) -> dict:
    """Dataset for the production model (make train-final): train = train + valid + test of the
    split in src (every labeled page), valid/test stay as they are (RF-DETR needs a valid split to
    pick its checkpoint; the numbers on it are no longer independent). Images are linked."""
    if dst.exists():
        shutil.rmtree(dst)
    dst.mkdir(parents=True)
    shutil.copy2(src / "classes.json", dst / "classes.json")
    merged = {"images": [], "annotations": [], "categories": None}
    counts = {}
    for s in ("train", "valid", "test"):
        sd = src / s
        if not (sd / "_annotations.coco.json").is_file():
            continue
        coco = json.loads((sd / "_annotations.coco.json").read_text(encoding="utf-8"))
        merged["categories"] = merged["categories"] or coco["categories"]
        counts[s] = len(coco["images"])
        if s != "train":   # valid/test unchanged
            (dst / s).mkdir()
            for img in coco["images"]:
                link(sd / img["file_name"], dst / s / img["file_name"])
            (dst / s / "_annotations.coco.json").write_text(json.dumps(coco), encoding="utf-8")
        id_map = {}
        for img in coco["images"]:   # file names carry a unique page id, ids are renumbered
            id_map[img["id"]] = len(merged["images"]) + 1
            merged["images"].append(dict(img, id=id_map[img["id"]]))
        for a in coco["annotations"]:
            merged["annotations"].append(dict(a, id=len(merged["annotations"]) + 1, image_id=id_map[a["image_id"]]))
    (dst / "train").mkdir()
    for img in merged["images"]:
        for s in ("train", "valid", "test"):
            if (src / s / img["file_name"]).exists():
                link(src / s / img["file_name"], dst / "train" / img["file_name"])
                break
    (dst / "train" / "_annotations.coco.json").write_text(json.dumps(merged), encoding="utf-8")
    return {"pages": counts, "train_pages": len(merged["images"]), "train_boxes": len(merged["annotations"])}
