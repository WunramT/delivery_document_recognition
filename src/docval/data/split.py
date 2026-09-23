"""Grouped, doc-type-stratified train/valid/test split.

Groups prevent pages of the same document/shipment from landing in different
splits. Plain loops only, so the logic ports 1:1 to JS.
"""

from __future__ import annotations

import random


def segment_ids(pages, start_types: list[str], own_segment_types: list[str]) -> list[str]:
    """Shipment segments inside a scan batch (pages must be in page order).

    A new segment starts
      - when source_pdf changes,
      - at the first page of a block of `start_types` (e.g. cmr) that follows other pages,
      - when entering or leaving a block of `own_segment_types` (e.g. loading_list).
    """
    out = []
    seg = -1
    prev_pdf = object()
    prev_type = None
    for p in pages:
        t = p.doc_type
        new = False
        if p.source_pdf != prev_pdf:
            new = True
        elif t in start_types and prev_type not in start_types:
            new = True
        elif (t in own_segment_types) != (prev_type in own_segment_types):
            new = True
        if new:
            seg += 1
        out.append(f"{p.source_pdf or 'nopdf'}#{seg:03d}")
        prev_pdf, prev_type = p.source_pdf, t
    return out


def assign_groups(pages, cfg_split: dict) -> dict:
    """Set page.group according to split.group_by. Returns info for the report."""
    mode = cfg_split.get("group_by", "segment")
    ungroup = set(cfg_split.get("ungroup_doc_types", []))
    if mode == "segment":
        ids = segment_ids(pages, cfg_split.get("segment_start_types", ["cmr"]),
                          cfg_split.get("own_segment_types", ["loading_list"]))
    elif mode == "source_pdf":
        ids = [p.source_pdf or p.file_name for p in pages]
    elif mode == "tour_number":
        # pages without a tour number inherit the previous page's group (same shipment)
        ids, last = [], None
        for p in pages:
            if p.tour_number and p.tour_number != "?":
                last = "tour:" + p.tour_number
            ids.append(last or p.file_name)
    elif mode == "none":
        ids = [p.file_name for p in pages]
    else:
        raise ValueError(f"unknown split.group_by: {mode}")
    ungrouped = 0
    for p, g in zip(pages, ids):
        if p.doc_type in ungroup:
            p.group = "page:" + p.file_name
            ungrouped += 1
        else:
            p.group = g
    return {"mode": mode, "n_groups": len({p.group for p in pages}),
            "ungrouped_pages": ungrouped, "ungrouped_doc_types": sorted(ungroup)}


def grouped_stratified_split(pages, ratios: dict[str, float], seed: int) -> dict[str, str]:
    """Return {file_name: split}. Greedy: largest groups first, each group goes to
    the split with the largest remaining deficit for the group's doc types."""
    names = list(ratios.keys())
    groups: dict[str, list] = {}
    for p in pages:
        groups.setdefault(p.group or p.file_name, []).append(p)
    types = sorted({p.doc_type or "?" for p in pages})
    total = {t: 0 for t in types}
    for p in pages:
        total[p.doc_type or "?"] += 1
    target = {s: {t: total[t] * ratios[s] for t in types} for s in names}
    current = {s: {t: 0 for t in types} for s in names}
    size = {s: 0.0 for s in names}

    keys = sorted(groups.keys())
    rng = random.Random(seed)
    rng.shuffle(keys)
    keys.sort(key=lambda k: -len(groups[k]))  # stable: shuffled order breaks ties

    assign: dict[str, str] = {}
    n_total = len(pages)
    for k in keys:
        comp = {t: 0 for t in types}
        for p in groups[k]:
            comp[p.doc_type or "?"] += 1
        best, best_score = None, None
        for s in names:
            # deficit on the group's doc types, minus overshoot of the overall size
            score = 0.0
            for t in types:
                if comp[t]:
                    score += min(comp[t], target[s][t] - current[s][t])
            over = size[s] + len(groups[k]) - n_total * ratios[s]
            if over > 0:
                score -= over
            if best_score is None or score > best_score:
                best, best_score = s, score
        for t in types:
            current[best][t] += comp[t]
        size[best] += len(groups[k])
        for p in groups[k]:
            assign[p.file_name] = best
    return assign


def split_summary(pages, assign: dict[str, str]) -> dict:
    out: dict = {}
    for p in pages:
        s = assign[p.file_name]
        d = out.setdefault(s, {"pages": 0, "groups": set(), "by_type": {}})
        d["pages"] += 1
        d["groups"].add(p.group)
        d["by_type"][p.doc_type or "?"] = d["by_type"].get(p.doc_type or "?", 0) + 1
    for d in out.values():
        d["groups"] = len(d["groups"])
    # leakage check: a group in more than one split
    where: dict = {}
    for p in pages:
        where.setdefault(p.group, set()).add(assign[p.file_name])
    out["_leaking_groups"] = sorted(g for g, s in where.items() if len(s) > 1)
    return out
