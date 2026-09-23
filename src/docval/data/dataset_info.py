"""Dataset analysis used by scripts/inspect_dataset.py.

Answers: where does the doc type come from, is there GT text for the tour
number, can pages be grouped into documents/batches (split leakage).
"""

from __future__ import annotations

import re
from pathlib import PurePosixPath

from .coco import STANDARD_ANN_KEYS, STANDARD_IMAGE_KEYS
from .labels import RF_SUFFIX, match_to_coco, read_label_table
PAGE_SUFFIX = re.compile(
    r"^(?P<prefix>.*?)[\s_\-.]*(?:p|pg|page|seite|s|strona)?[\s_\-.]*(?<!\d)(?P<page>\d{1,3})$",
    re.I,
)
DOC_TYPE_KEY_HINT = re.compile(r"(doc|type|typ|class|klass|kategor|kind|label|art)", re.I)
GROUP_KEY_HINT = re.compile(r"(batch|stapel|stack|group|doc|document|pdf|scan|source|parent|sheet|set)", re.I)
TEXT_KEY_HINT = re.compile(r"(text|value|transcri|content|ocr|tour|number|nummer|caption|string)", re.I)


def flatten(d: dict, prefix: str = "", depth: int = 3) -> dict:
    """Flatten nested dicts to dotted keys (lists are kept as values)."""
    out = {}
    for k, v in d.items():
        key = f"{prefix}{k}"
        if isinstance(v, dict) and depth > 0:
            out.update(flatten(v, key + ".", depth - 1))
        else:
            out[key] = v
    return out


def custom_fields(records: list[dict], standard: set[str]) -> dict[str, dict]:
    """Summarize non-standard (possibly nested) fields over records."""
    stats: dict[str, dict] = {}
    for r in records:
        extra = {k: v for k, v in r.items() if k not in standard}
        for k, v in flatten(extra).items():
            s = stats.setdefault(k, {"count": 0, "values": {}})
            s["count"] += 1
            sv = v if isinstance(v, (str, int, float, bool)) or v is None else repr(v)[:60]
            s["values"][sv] = s["values"].get(sv, 0) + 1
    for s in stats.values():
        s["distinct"] = len(s["values"])
        s["top"] = sorted(s["values"].items(), key=lambda kv: -kv[1])[:10]
        del s["values"]
    return stats


def base_stem(file_name: str) -> str:
    """Filename without folders, extension and Roboflow hash suffix."""
    p = PurePosixPath(file_name.replace("\\", "/"))
    name = p.name
    stem = RF_SUFFIX.sub("", name)
    if stem == name:  # no rf suffix; drop the extension
        stem = p.stem
    return stem


def folder_of(file_name: str) -> str | None:
    parts = PurePosixPath(file_name.replace("\\", "/")).parts
    return parts[0] if len(parts) > 1 else None


def tokens(s: str) -> list[str]:
    return [t for t in re.split(r"[^0-9a-ząćęłńóśźżäöüß]+", s.lower()) if t]


def guess_doc_type_from_name(name: str, keywords: dict[str, list[str]]) -> list[str]:
    """Return all doc types whose keywords match a token or substring of `name`.

    Keywords of length <= 3 must match a whole token (avoid 'ls' in 'details').
    """
    low = name.lower()
    toks = set(tokens(low))
    hits = []
    for doc_type, kws in keywords.items():
        for kw in kws:
            kw = kw.lower()
            if (len(kw) <= 3 and kw in toks) or (len(kw) > 3 and kw in low):
                hits.append(doc_type)
                break
    return hits


def split_page_suffix(stem: str) -> tuple[str, int | None]:
    m = PAGE_SUFFIX.match(stem)
    if not m or not m.group("prefix"):
        return stem, None
    return m.group("prefix"), int(m.group("page"))


def shape_of(text: str) -> str:
    """'AB-1234' -> 'AA-9999'. Used to infer the tour number format."""
    out = []
    for ch in text:
        if ch.isdigit():
            out.append("9")
        elif ch.isalpha():
            out.append("A")
        else:
            out.append(ch)
    return "".join(out)


def percentiles(values: list[float], ps=(0, 5, 50, 95, 100)) -> dict[str, float]:
    if not values:
        return {}
    v = sorted(values)
    out = {}
    for p in ps:
        # linear interpolation, same as numpy default
        pos = (len(v) - 1) * p / 100
        lo = int(pos)
        hi = min(lo + 1, len(v) - 1)
        out[f"p{p}"] = v[lo] + (v[hi] - v[lo]) * (pos - lo)
    return out


def doc_type_from_categories(categories: list[dict], doc_types: list[str],
                             keywords: dict[str, list[str]],
                             object_classes: list[str] = ()) -> list[str]:
    """Category names that look like doc types (whole-page class labels)."""
    hits = []
    for c in categories:
        name = str(c.get("name", ""))
        if name in object_classes:
            continue
        if name.lower() in doc_types or guess_doc_type_from_name(name, keywords):
            hits.append(name)
    return hits


def analyze_doc_type_sources(data: dict, doc_types: list[str],
                             keywords: dict[str, list[str]],
                             object_classes: list[str] = ()) -> dict:
    images = data["images"]
    n = len(images)
    result: dict = {"n_images": n}

    # 1. image attributes
    fields = custom_fields(images, STANDARD_IMAGE_KEYS)
    candidates = []
    for key, s in fields.items():
        vals = [str(v).lower() for v, _ in s["top"]]
        known = sum(1 for v in vals if v in doc_types or guess_doc_type_from_name(v, keywords))
        if s["distinct"] <= 20 and (DOC_TYPE_KEY_HINT.search(key) or known):
            candidates.append({"key": key, "coverage": s["count"] / n if n else 0,
                               "distinct": s["distinct"], "top": s["top"],
                               "values_matching_doc_types": known})
    candidates.sort(key=lambda c: (-c["values_matching_doc_types"], -c["coverage"]))
    result["image_fields"] = fields
    result["attribute_candidates"] = candidates

    # 1b. category names that are doc types
    result["doc_type_categories"] = doc_type_from_categories(
        data["categories"], doc_types, keywords, object_classes)

    # 2. file name patterns
    by_type: dict[str, int] = {}
    ambiguous = 0
    unmatched_examples = []
    guesses: dict[str, str | None] = {}
    for img in images:
        hits = guess_doc_type_from_name(base_stem(img["file_name"]), keywords)
        if len(hits) == 1:
            by_type[hits[0]] = by_type.get(hits[0], 0) + 1
            guesses[img["file_name"]] = hits[0]
        else:
            guesses[img["file_name"]] = None
            if len(hits) > 1:
                ambiguous += 1
            elif len(unmatched_examples) < 10:
                unmatched_examples.append(img["file_name"])
    matched = sum(by_type.values())
    result["filename"] = {"matched": matched, "coverage": matched / n if n else 0,
                          "by_type": by_type, "ambiguous": ambiguous,
                          "unmatched_examples": unmatched_examples}
    result["filename_guesses"] = guesses

    # 3. folder structure
    folders: dict[str, int] = {}
    for img in images:
        f = folder_of(img["file_name"])
        if f is not None:
            folders[f] = folders.get(f, 0) + 1
    result["folders"] = folders
    folder_types = {f: guess_doc_type_from_name(f, keywords) for f in folders}
    result["folder_doc_types"] = folder_types

    # decision
    good = [c for c in candidates if c["coverage"] >= 0.99 and c["values_matching_doc_types"]]
    if good:
        result["source"] = {"kind": "coco_attribute", "key": good[0]["key"]}
    elif result["doc_type_categories"]:
        result["source"] = {"kind": "coco_category", "names": result["doc_type_categories"]}
    elif result["filename"]["coverage"] >= 0.99:
        result["source"] = {"kind": "filename"}
    elif folders and all(len(t) == 1 for t in folder_types.values()) and sum(folders.values()) == n:
        result["source"] = {"kind": "folder"}
    else:
        result["source"] = {"kind": "missing"}
    return result


def analyze_doc_type_csv(data: dict, path, doc_types: list[str],
                         file_col: str | None = None, value_col: str | None = None) -> dict:
    """Coverage and value distribution of an external doc type CSV."""
    values, info = read_label_table(path, value_col=value_col, file_col=file_col)
    records = info.pop("records")
    out = {"info": info}
    if not info["exists"]:
        return out
    out["grouping"] = csv_grouping(records, info["value_col"])
    file_names = [i["file_name"] for i in data["images"]]
    matched, stats = match_to_coco(values, file_names)
    dist: dict[str, int] = {}
    for v in matched.values():
        dist[v] = dist.get(v, 0) + 1
    n = len(file_names)
    out.update({
        "matched": len(matched),
        "coverage": len(matched) / n if n else 0,
        "match_stats": {k: (v if isinstance(v, int) else len(v)) for k, v in stats.items()},
        "unmatched_coco_examples": stats["unmatched_coco"][:10],
        "unmatched_csv_examples": stats["unmatched_csv"][:10],
        "value_distribution": dict(sorted(dist.items(), key=lambda kv: -kv[1])),
        "values_not_in_doc_types": sorted(v for v in dist if v.lower() not in doc_types),
        "matched_values": matched,
    })
    return out


PAGE_COL_HINT = re.compile(r"(page|seite|strona)", re.I)


def csv_grouping(records: dict[str, dict], type_col: str | None) -> dict:
    """Group columns (e.g. source_pdf/source_page) in a label CSV.

    Also returns the doc type sequence in page order per group, so logical
    documents inside one scanned batch can be seen (e.g. 'CCSSSS').
    """
    if not records:
        return {}
    cols = list(next(iter(records.values())).keys())
    page_col = next((c for c in cols if PAGE_COL_HINT.search(c)), None)
    group_col = next((c for c in cols if c != page_col and GROUP_KEY_HINT.search(c)
                      and c != type_col and not c.lower().startswith("file")), None)
    out = {"group_col": group_col, "page_col": page_col}
    if group_col is None:
        return out
    groups: dict[str, list] = {}
    for fn, r in records.items():
        groups.setdefault(r.get(group_col, ""), []).append(r)
    out["n_groups"] = len(groups)
    out["group_sizes"] = sorted(len(v) for v in groups.values())
    legend: dict[str, str] = {}
    for r in records.values():
        t = r.get(type_col) or "?" if type_col else "?"
        if t not in legend:
            letters = [ch.upper() for ch in t if ch.isalpha()] + list("XYZWVQ")
            legend[t] = next(ch for ch in letters if ch not in legend.values())
    out["legend"] = {v: k for k, v in legend.items()}
    seqs = {}
    for g, rows in groups.items():
        def page_key(r):
            v = r.get(page_col, "") if page_col else ""
            return int(v) if v.isdigit() else 0
        rows = sorted(rows, key=page_key)
        seqs[g] = "".join(legend[r.get(type_col) or "?" if type_col else "?"] for r in rows)
    out["type_sequence"] = seqs
    return out


def analyze_tour_text(data: dict, tour_class: str) -> dict:
    cat_ids = {c["id"] for c in data["categories"] if c.get("name") == tour_class}
    anns = [a for a in data["annotations"] if a.get("category_id") in cat_ids]
    fields = custom_fields(anns, STANDARD_ANN_KEYS)
    candidates = []
    for key, s in fields.items():
        has_str = any(isinstance(v, str) for v, _ in s["top"])
        if TEXT_KEY_HINT.search(key) and has_str:
            candidates.append({"key": key, "coverage": s["count"] / len(anns) if anns else 0,
                               "distinct": s["distinct"], "examples": [v for v, _ in s["top"][:5]]})
    candidates.sort(key=lambda c: -c["coverage"])
    per_image: dict = {}
    for a in anns:
        per_image[a["image_id"]] = per_image.get(a["image_id"], 0) + 1
    shapes: dict[str, int] = {}
    if candidates:
        key = candidates[0]["key"]
        for a in anns:
            v = flatten({k: v for k, v in a.items() if k not in STANDARD_ANN_KEYS}).get(key)
            if isinstance(v, str) and v.strip():
                sh = shape_of(v.strip())
                shapes[sh] = shapes.get(sh, 0) + 1
    multi = sum(1 for c in per_image.values() if c > 1)
    # partial GT per image (several boxes -> distinct values joined by ";")
    known: dict = {}
    if candidates:
        key = candidates[0]["key"]
        for a in anns:
            v = flatten({k: v for k, v in a.items() if k not in STANDARD_ANN_KEYS}).get(key)
            if isinstance(v, str) and v.strip() and v.strip() not in known.setdefault(a["image_id"], []):
                known[a["image_id"]].append(v.strip())
    return {
        "known_text_by_image_id": {iid: ";".join(v) for iid, v in known.items() if v},
        "n_annotations": len(anns),
        "n_images_with_box": len(per_image),
        "n_images_multiple_boxes": multi,
        "annotation_fields": fields,
        "text_candidates": candidates,
        "text_shapes": sorted(shapes.items(), key=lambda kv: -kv[1]),
        "source": ({"kind": "coco_attribute", "key": candidates[0]["key"]}
                   if candidates and candidates[0]["coverage"] >= 0.99 else {"kind": "missing"}),
    }


def analyze_grouping(data: dict, cmr_count_class: str = "cmr_count") -> dict:
    images = data["images"]
    n = len(images)
    out: dict = {"n_images": n}

    # a) explicit group attributes
    fields = custom_fields(images, STANDARD_IMAGE_KEYS)
    out["attribute_candidates"] = [
        {"key": k, "coverage": s["count"] / n if n else 0, "distinct": s["distinct"]}
        for k, s in fields.items()
        if GROUP_KEY_HINT.search(k) and 1 < s["distinct"] < n
    ]

    # b) Roboflow: same source image exported multiple times (augmentation!)
    rf_count = sum(1 for img in images if RF_SUFFIX.search(PurePosixPath(img["file_name"]).name))
    stems: dict[str, list[str]] = {}
    for img in images:
        stems.setdefault(base_stem(img["file_name"]), []).append(img["file_name"])
    dup_stems = {s: fns for s, fns in stems.items() if len(fns) > 1}
    out["roboflow_files"] = rf_count
    out["same_source_stem"] = {"n_stems": len(dup_stems),
                               "n_images": sum(len(v) for v in dup_stems.values()),
                               "examples": list(dup_stems.items())[:5]}

    # c) prefix + page number in file name
    groups: dict[str, list[int | None]] = {}
    with_page = 0
    for img in images:
        stem = base_stem(img["file_name"])
        folder = folder_of(img["file_name"])
        prefix, page = split_page_suffix(stem)
        if page is not None:
            with_page += 1
        groups.setdefault(f"{folder}/{prefix}" if folder else prefix, []).append(page)
    sizes: dict[int, int] = {}
    for pages in groups.values():
        sizes[len(pages)] = sizes.get(len(pages), 0) + 1
    multi = {g: p for g, p in groups.items() if len(p) > 1}
    out["filename_page_groups"] = {
        "n_with_page_suffix": with_page,
        "n_groups": len(groups),
        "n_multi_page_groups": len(multi),
        "group_size_hist": dict(sorted(sizes.items())),
        "examples": [(g, sorted(x for x in p if x is not None)) for g, p in list(multi.items())[:8]],
    }

    # d) cmr_count boxes present?
    cat_ids = {c["id"] for c in data["categories"] if c.get("name") == cmr_count_class}
    out["images_with_cmr_count"] = len({a["image_id"] for a in data["annotations"]
                                        if a.get("category_id") in cat_ids})
    return out


def dhash(img, size: int = 16) -> int:
    """Difference hash of a PIL image (for near-duplicate detection)."""
    g = img.convert("L").resize((size + 1, size), 1)  # 1 = LANCZOS
    px = list(g.getdata())
    h = 0
    for row in range(size):
        for col in range(size):
            left = px[row * (size + 1) + col]
            right = px[row * (size + 1) + col + 1]
            h = (h << 1) | (1 if left > right else 0)
    return h


def hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def near_duplicates(hashes: dict[str, int], max_dist: int) -> list[tuple[str, str, int]]:
    items = list(hashes.items())
    pairs = []
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            d = hamming(items[i][1], items[j][1])
            if d <= max_dist:
                pairs.append((items[i][0], items[j][0], d))
    return pairs
