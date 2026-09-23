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


def write_rfdetr_dataset(pages, assign: dict[str, str], classes: list[str], out: Path) -> dict:
    """classes: detector classes in label order (category ids 1..n)."""
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
            m = link(p.path, d / name)
            methods[m] = methods.get(m, 0) + 1
            images.append({"id": p.image_id, "file_name": name, "width": p.width, "height": p.height,
                           "orig_file_name": p.file_name, "doc_type": p.doc_type})
            for b in p.boxes:
                if b.cls not in cat_id:
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
    return info
