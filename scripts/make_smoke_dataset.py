#!/usr/bin/env python3
"""Generate a tiny synthetic dataset for `make smoke` (no real documents needed).

Pages mimic the real layout found in step 0: header keyword on top, tour number
at a doc-type specific position, signature + stamp in the lower right.
Output: artifacts/smoke/data/{_annotations.coco.json, images/, page_types.csv, tour_numbers.csv}
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]

W, H = 620, 877  # A4 at 75 DPI, keeps the smoke test fast
HEADERS = {"cmr": "CMR  Internationaler Frachtbrief", "lieferschein": "Lieferschein",
           "loading_list": "Loading List / List załadunkowy"}
# tour number center (x, y) per type, taken from the real data statistics
TOUR_POS = {"cmr": (0.20, 0.68), "lieferschein": (0.34, 0.34), "loading_list": (0.76, 0.10)}
SEQ = ["loading_list", "cmr", "cmr", "lieferschein", "lieferschein", "cmr", "lieferschein",
       "lieferschein", "cmr", "lieferschein", "cmr", "lieferschein"]


def font(size):
    for name in ("DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default(size)


def scribble(d: ImageDraw.ImageDraw, box, rng):
    x1, y1, x2, y2 = box
    pts = []
    for i in range(40):
        t = i / 39
        x = x1 + t * (x2 - x1)
        y = (y1 + y2) / 2 + math.sin(t * rng.uniform(8, 14)) * (y2 - y1) * 0.35
        pts.append((x, y))
    d.line(pts, fill=(20, 20, 120), width=3)


def stamp(d: ImageDraw.ImageDraw, box, rng):
    x1, y1, x2, y2 = box
    col = (rng.randint(20, 80), rng.randint(40, 90), rng.randint(150, 220))
    d.rectangle(box, outline=col, width=3)
    d.text((x1 + 8, y1 + 8), "SPEDITION\nMUSTER GmbH", fill=col, font=font(14))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "artifacts/smoke/data"))
    ap.add_argument("--n", type=int, default=12)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()
    rng = random.Random(args.seed)
    out = Path(args.out)
    (out / "images").mkdir(parents=True, exist_ok=True)
    cats = [{"id": 1, "name": "unterschrift"}, {"id": 2, "name": "stempel"},
            {"id": 3, "name": "tour_nummer"}, {"id": 4, "name": "cmr_count"}]
    images, anns, types, tours = [], [], [], []
    aid = 1
    cmr_total = SEQ[: args.n].count("cmr")
    cmr_i = 0
    for i in range(args.n):
        t = SEQ[i % len(SEQ)]
        fn = f"images/smoke_{i + 1:04d}.png"
        im = Image.new("RGB", (W, H), "white")
        d = ImageDraw.Draw(im)
        d.text((40, 30), HEADERS[t], fill="black", font=font(28))
        for k in range(12):  # body text lines
            y = 140 + k * 38
            d.line([(40, y), (40 + rng.randint(200, 520), y)], fill=(160, 160, 160), width=2)
        # real format: tour/date/number, e.g. 503/01.09.2026/4000
        tour = f"{rng.randint(100, 999)}/{rng.randint(1, 28):02d}.09.2026/{rng.randint(1000, 9999)}"
        f = font(18)
        tw = d.textlength(tour, font=f)
        cx, cy = TOUR_POS[t][0] * W, TOUR_POS[t][1] * H
        tb = [cx - tw / 2 - 4, cy - 13, cx + tw / 2 + 4, cy + 13]
        d.rectangle(tb, fill="white")
        d.text((tb[0] + 4, tb[1] + 1), tour, fill="black", font=f)
        boxes = [("tour_nummer", tb)]
        if t == "cmr":  # CMR: signatures in fields 22/23/24, one stamp
            st = [0.70 * W, 0.74 * H, 0.70 * W + 0.26 * W, 0.74 * H + 0.10 * H]
            stamp(d, st, rng)
            boxes.append(("stempel", st))
            # three signatures (fields 22/23/24), all annotated as "unterschrift"
            for x0 in (0.04, 0.37, 0.70):
                sb = [x0 * W, 0.86 * H, (x0 + 0.25) * W, 0.93 * H]
                scribble(d, sb, rng)
                boxes.append(("unterschrift", sb))
        elif t == "lieferschein":
            sx, sy = rng.uniform(0.62, 0.72) * W, rng.uniform(0.80, 0.86) * H
            sb = [sx, sy, sx + 0.25 * W, sy + 0.09 * H]
            st = [sx - 20, sy - 30, sx - 20 + 0.30 * W, sy - 30 + 0.13 * H]
            stamp(d, st, rng)
            scribble(d, sb, rng)
            boxes += [("stempel", st), ("unterschrift", sb)]
        if t == "cmr":
            cmr_i += 1
            txt = f"CMR {cmr_i}/{cmr_total}"
            d.text((0.80 * W, 0.04 * H), txt, fill="black", font=font(16))
            boxes.append(("cmr_count", [0.80 * W - 3, 0.04 * H - 2, 0.80 * W + 90, 0.04 * H + 22]))
        im.save(out / fn)
        images.append({"id": i + 1, "file_name": fn, "width": W, "height": H})
        cid = {c["name"]: c["id"] for c in cats}
        for cls, b in boxes:
            anns.append({"id": aid, "image_id": i + 1, "category_id": cid[cls],
                         "bbox": [round(b[0], 1), round(b[1], 1), round(b[2] - b[0], 1), round(b[3] - b[1], 1)],
                         "area": round((b[2] - b[0]) * (b[3] - b[1]), 1), "iscrowd": 0})
            aid += 1
        types.append((fn, t, "smoke.pdf", i + 1))
        tours.append((fn, tour))
    (out / "_annotations.coco.json").write_text(json.dumps(
        {"images": images, "annotations": anns, "categories": cats}, indent=1))
    with open(out / "page_types.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["file_name", "doc_type", "source_pdf", "source_page"])
        w.writerows(types)
    with open(out / "tour_numbers.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["file_name", "tour_number"])
        w.writerows(tours)
    print(f"{args.n} Seiten -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
