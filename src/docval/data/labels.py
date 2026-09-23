"""CSV label sources (doc type, tour number) that complement the COCO file."""

from __future__ import annotations

import csv
from pathlib import Path

DOC_TYPES_HEADER = ["file_name", "doc_type"]
TOUR_NUMBERS_HEADER = ["file_name", "tour_number"]


def read_label_csv(path: str | Path, value_col: str) -> dict[str, str]:
    """Return {file_name: value} for all rows with a non-empty value."""
    out: dict[str, str] = {}
    p = Path(path)
    if not p.is_file():
        return out
    with open(p, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            val = (row.get(value_col) or "").strip()
            if val:
                out[row["file_name"]] = val
    return out


def write_template(path: str | Path, header: list[str], file_names: list[str],
                   prefill: dict[str, str] | None = None) -> str:
    """Create a template with one row per file name (values from `prefill`,
    e.g. partial ground truth already present in the COCO file). An existing file is never overwritten:
    new file names are appended instead, so manual work is preserved.

    Returns "created", "extended" or "unchanged".
    """
    prefill = prefill or {}
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    if not p.exists():
        with open(p, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(header)
            for fn in file_names:
                w.writerow([fn, prefill.get(fn, "")])
        return "created"
    with open(p, newline="", encoding="utf-8") as f:
        existing = {row[header[0]] for row in csv.DictReader(f)}
    missing = [fn for fn in file_names if fn not in existing]
    if not missing:
        return "unchanged"
    with open(p, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        for fn in missing:
            w.writerow([fn, prefill.get(fn, "")])
    return "extended"
