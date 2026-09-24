"""Synthetic negative pages: remove or move signature/stamp using the GT boxes.

Originals are only read; results go to artifacts/synthetic/.
"""

from __future__ import annotations

import random

from PIL import Image

from . import MISSING, WRONG_POSITION, box_center_in


def to_rgb(im: Image.Image) -> Image.Image:
    if im.mode == "RGB":
        return im
    if im.mode in ("RGBA", "LA", "P"):
        im = im.convert("RGBA")
        bg = Image.new("RGB", im.size, (255, 255, 255))
        bg.paste(im, mask=im.split()[3])
        return bg
    return im.convert("RGB")


def ring_median(im: Image.Image, box, ring: int = 12) -> tuple[int, int, int]:
    """Median color of a ring around `box` (the local background)."""
    x1, y1, x2, y2 = [int(round(v)) for v in box]
    W, H = im.size
    px = im.load()
    vals = ([], [], [])
    step = 3
    for y in range(max(0, y1 - ring), min(H, y2 + ring), step):
        for x in range(max(0, x1 - ring), min(W, x2 + ring), step):
            if x1 <= x < x2 and y1 <= y < y2:
                continue
            c = px[x, y]
            for k in range(3):
                vals[k].append(c[k])
    if not vals[0]:
        return (255, 255, 255)
    return tuple(sorted(v)[len(v) // 2] for v in vals)


def erase(im: Image.Image, box, pad: int = 4, fill: str = "median") -> None:
    x1, y1, x2, y2 = box
    b = (max(0, int(x1) - pad), max(0, int(y1) - pad),
         min(im.width, int(x2 + 0.999) + pad), min(im.height, int(y2 + 0.999) + pad))
    color = (255, 255, 255) if fill == "white" else ring_median(im, b)
    im.paste(color, b)


def erase_keep(im: Image.Image, original: Image.Image, box, keep: list, fill: str = "median") -> None:
    """Erase `box` but restore the parts that intersect `keep` boxes, so e.g. a
    signature drawn over a stamp survives when the stamp is removed. (Stamp ink
    inside the signature box remains - documented limitation.)"""
    erase(im, box, fill=fill)
    for k in keep:
        ix1, iy1 = max(box[0], k[0]), max(box[1], k[1])
        ix2, iy2 = min(box[2], k[2]), min(box[3], k[3])
        if ix2 - ix1 >= 1 and iy2 - iy1 >= 1:
            r = (int(ix1), int(iy1), int(ix2 + 0.999), int(iy2 + 0.999))
            im.paste(original.crop(r), (r[0], r[1]))


def boxes_overlap(a, b) -> bool:
    return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])


def find_wrong_place(page_w, page_h, box, zone_norm, avoid: list, rng: random.Random,
                     tries: int = 200):
    """A position for `box` (same size) whose center lies outside the zone and
    does not overlap `avoid` boxes. Prefers the upper half of the page."""
    w, h = box[2] - box[0], box[3] - box[1]
    zx1, zy1, zx2, zy2 = (zone_norm[0] * page_w, zone_norm[1] * page_h,
                          zone_norm[2] * page_w, zone_norm[3] * page_h)
    for _ in range(tries):
        x = rng.uniform(0, max(1, page_w - w))
        y = rng.uniform(0, max(1, page_h * 0.6 - h))
        cand = (x, y, x + w, y + h)
        if boxes_overlap(cand, (zx1, zy1, zx2, zy2)):
            continue
        if any(boxes_overlap(cand, a) for a in avoid):
            continue
        return cand
    return None


def make_variants(page, image: Image.Image, zones: dict, rule: dict, rng: random.Random,
                  fill: str = "median", kinds=None) -> list[dict]:
    """Return [{"kind", "image", "expected", "boxes"}] for one page whose GT
    fulfils the rule. `boxes` are the modified GT boxes (for the gallery)."""
    if rule.get("fields"):
        return make_field_variants(page, image, rule["fields"], rng, fill, kinds)
    required = rule.get("require") or []
    optional = rule.get("optional") or []
    mode = rule.get("mode", "all")
    kinds = kinds or ["remove_one", "remove_all", "move_one"]
    base = to_rgb(image)
    out = []
    dz = zones.get(page.doc_type, {})

    def remaining(removed_cls: set) -> list:
        return [b for b in page.boxes if b.cls not in removed_cls]

    for cls in required:
        if not page.boxes_of(cls):
            continue
        if "remove_one" in kinds:
            im = base.copy()
            keep = [b.xyxy for b in page.boxes if b.cls != cls]
            for b in page.boxes_of(cls):
                erase_keep(im, base, b.xyxy, keep, fill=fill)
            # with mode "any" removing one class is still ok if another remains
            exp = MISSING if mode == "all" or len(required) == 1 else None
            if exp:
                out.append({"kind": f"entfernt_{cls}", "image": im, "expected": exp,
                            "boxes": remaining({cls})})
        if "move_one" in kinds and cls in dz:
            im = base.copy()
            avoid = [b.xyxy for b in page.boxes]
            moved = []
            ok = True
            for b in page.boxes_of(cls):
                target = find_wrong_place(page.width, page.height, b.xyxy, dz[cls]["box"],
                                          avoid, rng)
                if target is None:
                    ok = False
                    break
                crop = base.crop(tuple(int(v) for v in b.xyxy))
                erase_keep(im, base, b.xyxy, [o.xyxy for o in page.boxes if o.cls != cls], fill=fill)
                im.paste(crop, (int(target[0]), int(target[1])))
                avoid.append(target)
                moved.append(type(b)(cls, list(target), b.ann_id))
            if ok and moved:
                exp = WRONG_POSITION if mode == "all" or len(required) == 1 else None
                if exp:
                    out.append({"kind": f"verschoben_{cls}", "image": im, "expected": exp,
                                "boxes": remaining({cls}) + moved})
    # optional objects: only moving them is an error (removing is fine)
    for cls in optional:
        if "move_one" not in kinds or cls not in dz or not page.boxes_of(cls):
            continue
        im = base.copy()
        avoid = [b.xyxy for b in page.boxes]
        moved, ok = [], True
        for b in page.boxes_of(cls):
            target = find_wrong_place(page.width, page.height, b.xyxy, dz[cls]["box"], avoid, rng)
            if target is None:
                ok = False
                break
            crop = base.crop(tuple(int(v) for v in b.xyxy))
            erase_keep(im, base, b.xyxy, [o.xyxy for o in page.boxes if o.cls != cls], fill=fill)
            im.paste(crop, (int(target[0]), int(target[1])))
            avoid.append(target)
            moved.append(type(b)(cls, list(target), b.ann_id))
        if ok and moved:
            out.append({"kind": f"verschoben_{cls}", "image": im, "expected": WRONG_POSITION,
                        "boxes": remaining({cls}) + moved})
    if "remove_all" in kinds and len(required) > 1:
        im = base.copy()
        for cls in required:
            for b in page.boxes_of(cls):
                erase(im, b.xyxy, fill=fill)
        out.append({"kind": "entfernt_alle", "image": im, "expected": MISSING,
                    "boxes": remaining(set(required))})
    return out


def make_field_variants(page, image: Image.Image, fields: dict, rng: random.Random,
                        fill: str = "median", kinds=None) -> list[dict]:
    """Field rules (CMR 22/23/24): remove the signature of one field, remove all,
    or move one field's signature out of all fields -> expected "fehlt" each."""
    kinds = kinds or ["remove_one", "remove_all", "move_one"]
    base = to_rgb(image)
    W, H = page.width, page.height
    out = []

    def in_field(b, f):
        return box_center_in(b.norm(W, H), f["box"])

    all_req = []
    for name, f in fields.items():
        req = f.get("require") or []
        hit = [b for b in page.boxes if b.cls in req and in_field(b, f)]
        all_req += hit
        if not hit:
            continue
        keep = [o.xyxy for o in page.boxes if o not in hit]
        if "remove_one" in kinds:
            im = base.copy()
            for b in hit:
                erase_keep(im, base, b.xyxy, keep, fill=fill)
            out.append({"kind": f"entfernt_feld_{name.split()[0]}", "image": im, "expected": MISSING,
                        "boxes": [b for b in page.boxes if b not in hit]})
        if "move_one" in kinds:
            im = base.copy()
            avoid = [b.xyxy for b in page.boxes]
            moved, ok = [], True
            union = [min(f2["box"][0] for f2 in fields.values()), min(f2["box"][1] for f2 in fields.values()),
                     max(f2["box"][2] for f2 in fields.values()), max(f2["box"][3] for f2 in fields.values())]
            for b in hit:
                target = find_wrong_place(W, H, b.xyxy, union, avoid, rng)
                if target is None:
                    ok = False
                    break
                crop = base.crop(tuple(int(v) for v in b.xyxy))
                erase_keep(im, base, b.xyxy, keep, fill=fill)
                im.paste(crop, (int(target[0]), int(target[1])))
                avoid.append(target)
                moved.append(type(b)(b.cls, list(target), b.ann_id))
            if ok and moved:
                out.append({"kind": f"verschoben_feld_{name.split()[0]}", "image": im, "expected": MISSING,
                            "boxes": [b for b in page.boxes if b not in hit] + moved})
    if "remove_all" in kinds and all_req:
        im = base.copy()
        for b in all_req:
            erase(im, b.xyxy, fill=fill)
        out.append({"kind": "entfernt_alle", "image": im, "expected": MISSING,
                    "boxes": [b for b in page.boxes if b not in all_req]})
    return out
