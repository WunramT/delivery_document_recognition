"""Which classes are labeled on how many pages, per export and doc type.

Reads the merged dataset (artifacts/merged, written by every split/train/eval run) and prints
e.g. "425_21.09.2026 lieferschein 40 Seiten | ls_nummer 22 | seitenzahl 38": a class that is
on only part of the pages of a doc type where it should always be means unlabeled boxes - the
model then learns "sometimes no box" and loses recall there. Pages without the class are listed.

    python scripts/label_coverage.py [--merged artifacts/merged] [--class ls_nummer --type lieferschein]
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--merged", default="artifacts/merged")
    ap.add_argument("--class", dest="cls", help="list the pages of --type without this class")
    ap.add_argument("--type", help="doc type for --class")
    a = ap.parse_args()
    d = Path(a.merged)
    coco = json.loads((d / "_annotations.coco.json").read_text(encoding="utf-8"))
    with open(d / "page_types.csv", encoding="utf-8") as f:
        types = {r["file_name"]: r["doc_type"] for r in csv.DictReader(f, delimiter=";")}
    cat = {c["id"]: c["name"] for c in coco["categories"]}
    classes = [c["name"] for c in coco["categories"]]
    has = defaultdict(set)
    for an in coco["annotations"]:
        has[an["image_id"]].add(cat[an["category_id"]])
    table = defaultdict(lambda: {"n": 0, **{c: 0 for c in classes}})
    missing = []
    for img in coco["images"]:
        fn = img["file_name"]
        exp = fn.split("/")[0] if "/" in fn else "-"
        t = types.get(fn, "") or "?"
        row = table[(exp, t)]
        row["n"] += 1
        for c in has[img["id"]]:
            row[c] += 1
        if a.cls and t == a.type and a.cls not in has[img["id"]]:
            missing.append(fn)
    for (exp, t), row in sorted(table.items()):
        cells = " | ".join(f"{c} {row[c]}" for c in classes if row[c])
        print(f"{exp:16s} {t:13s} {row['n']:3d} Seiten | {cells or '-'}")
    if a.cls:
        print(f"\n{a.type}-Seiten ohne {a.cls}: {len(missing)}")
        for fn in missing:
            print("  " + fn)


if __name__ == "__main__":
    main()
