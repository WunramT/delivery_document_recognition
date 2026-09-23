"""CSV label sources (doc type, tour number) that complement the COCO file."""

from __future__ import annotations

import csv
import re
from pathlib import Path, PurePosixPath

DOC_TYPES_HEADER = ["file_name", "doc_type"]
TOUR_NUMBERS_HEADER = ["file_name", "tour_number"]

FILE_COL_NAMES = ["file_name", "filename", "file", "image", "image_name", "img",
                  "name", "datei", "dateiname", "bild"]
DOC_TYPE_COL_HINT = re.compile(r"(doc|page|type|typ|class|label|kategor|art)", re.I)
# Roboflow export suffix: "<orig>_jpg.rf.<hash>.jpg"
RF_SUFFIX = re.compile(r"_(jpe?g|png|tiff?|bmp|pdf|webp)\.rf\.[0-9a-f]{16,}(\.\w+)?$", re.I)


def base_stem(file_name: str) -> str:
    """Filename without folders, extension and Roboflow hash suffix, lowercased."""
    name = PurePosixPath(file_name.replace("\\", "/")).name
    stem = RF_SUFFIX.sub("", name)
    if stem == name:
        stem = PurePosixPath(name).stem
    return stem.lower()


def _read_text(p: Path) -> str:
    raw = p.read_bytes()
    for enc in ("utf-8-sig", "cp1252"):  # Excel on Windows writes either
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1")


def read_label_table(path: str | Path, value_col: str | None = None,
                     file_col: str | None = None, value_hint=DOC_TYPE_COL_HINT) -> tuple[dict, dict]:
    """Read a 2+ column label CSV with unknown delimiter/column names.

    Returns ({file_name: value}, info). Columns are auto-detected unless given.
    """
    p = Path(path)
    info = {"path": str(p), "exists": p.is_file(), "columns": [], "file_col": None,
            "value_col": None, "delimiter": None, "rows": 0, "empty_values": 0,
            "records": {}}  # file_name -> full row (all columns)
    if not p.is_file():
        return {}, info
    text = _read_text(p)
    first = text.splitlines()[0] if text else ""
    delim = max([",", ";", "\t", "|"], key=first.count)
    info["delimiter"] = delim
    reader = csv.DictReader(text.splitlines(), delimiter=delim)
    cols = [c.strip() for c in (reader.fieldnames or [])]
    reader.fieldnames = cols
    info["columns"] = cols
    low = {c.lower(): c for c in cols}
    fc = file_col or next((low[n] for n in FILE_COL_NAMES if n in low), cols[0] if cols else None)
    others = [c for c in cols if c != fc]
    vc = value_col or next((c for c in others if value_hint.search(c)), others[0] if others else None)
    info["file_col"], info["value_col"] = fc, vc
    out: dict[str, str] = {}
    for row in reader:
        fn = (row.get(fc) or "").strip()
        if not fn:
            continue
        info["rows"] += 1
        info["records"][fn] = {k: (v or "").strip() for k, v in row.items() if k is not None}
        val = (row.get(vc) or "").strip()
        if val:
            out[fn] = val
        else:
            info["empty_values"] += 1
    return out, info


def match_to_coco(values: dict[str, str], coco_file_names: list[str]) -> tuple[dict, dict]:
    """Map label rows onto COCO file names: exact name first, then by base stem
    (handles folders, other extensions and Roboflow-renamed files)."""
    by_stem: dict[str, list[str]] = {}
    for fn in values:
        by_stem.setdefault(base_stem(fn), []).append(fn)
    out: dict[str, str] = {}
    stats = {"exact": 0, "by_stem": 0, "stem_conflict": 0, "unmatched_coco": [], "unmatched_csv": []}
    used: set[str] = set()
    for fn in coco_file_names:
        if fn in values:
            out[fn] = values[fn]
            used.add(fn)
            stats["exact"] += 1
            continue
        cands = by_stem.get(base_stem(fn), [])
        vals = {values[c] for c in cands}
        if len(vals) == 1:
            out[fn] = vals.pop()
            used.update(cands)
            stats["by_stem"] += 1
        elif len(vals) > 1:
            stats["stem_conflict"] += 1
            stats["unmatched_coco"].append(fn)
        else:
            stats["unmatched_coco"].append(fn)
    stats["unmatched_csv"] = [fn for fn in values if fn not in used]
    return out, stats


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
