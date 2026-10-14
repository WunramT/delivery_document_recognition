"""Organisational checks of one tour - automatic, before a person looks at the stamps.

Input: one record per scanned page (built by run.py, corrected by the person's decision
in finalize.py). Only the fields used here matter:

    {"n": 7,                                   # page number in the scan batch (1-based)
     "doc_type": "cmr" | "lieferschein" | "loading_list" | "unsicher",
     "tour": {"text": "503/01.09.2026/4000", "accepted": True} | None,
     "cmr_count": {"parsed": [3, 13]} | None,
     "ta": [{"ta": "12283251", "excluded": False}, ...],
     "proposal": {"unterschrift": "ja" | "nein" | "unsicher", ...}, "scores": {cls: float},
     "decision": {"unterschrift": bool, ...},  # optional, from the person
     "archive": bool}                          # optional, set by the person (duplicates)

What it does (process steps 1 and 3 of the sales department):
- doc type of every page known?
- tour number: pages of another tour (additional load) and unreadable ones
- CMR: duplicates (same "CMR i/n" twice -> keep the better copy), stack complete 1..n,
  sort order by i
- Lieferscheine: duplicates (same TA numbers -> keep the copy with stamp/signature)
- TA numbers (loading list -> CMR + Lieferschein per loaded TA), as a hint until validated

Plain dicts and loops (portable to JS like the rest of the pipeline).
"""

from __future__ import annotations

from ..ocr.postprocess import stack_complete

REVIEW_TYPES = ("cmr", "lieferschein")
KNOWN_TYPES = ("cmr", "lieferschein", "loading_list", "bestaetigung")
OK, ERROR, HINT = "ok", "fehler", "hinweis"


def majority_tour(pages: list[dict]) -> str | None:
    """Most frequent accepted tour number on CMR/Lieferschein pages (ties: first seen)."""
    votes: dict[str, int] = {}
    for p in pages:
        t = p.get("tour") or {}
        if p.get("doc_type") in REVIEW_TYPES and t.get("accepted") and t.get("text"):
            votes[t["text"]] = votes.get(t["text"], 0) + 1
    best = None
    for text, n in votes.items():
        if best is None or n > votes[best]:
            best = text
    return best


def class_value(p: dict, cls: str) -> bool | None:
    """Is the object there? The person's decision wins; else the model's proposal
    (None = the model is unsure)."""
    d = p.get("decision") or {}
    if cls in d and d[cls] is not None:
        return bool(d[cls])
    s = (p.get("proposal") or {}).get(cls)
    return None if s in (None, "unsicher") else s == "ja"


def page_valid(p: dict, rule: dict) -> bool | None:
    """Signature/stamp rule of the doc type: mode all (CMR: stamp and signature) or any
    (Lieferschein: stamp or signature). None = undecided."""
    req = rule.get("require") or []
    if not req:
        return True
    vals = [class_value(p, c) for c in req]
    if rule.get("mode", "all") == "any":
        if any(v is True for v in vals):
            return True
        return None if any(v is None for v in vals) else False
    if any(v is False for v in vals):
        return False
    return None if any(v is None for v in vals) else True


def rank(p: dict, rule: dict) -> tuple:
    """Which copy of a duplicate to keep: valid first, then more objects found, then score."""
    v = page_valid(p, rule)
    found = sum(1 for c in rule.get("require") or [] if class_value(p, c) is True)
    score = sum((p.get("scores") or {}).get(c, 0.0) for c in rule.get("require") or [])
    return (1 if v is True else 0 if v is None else -1, found, score, -p["n"])


def dedupe(group: list[dict], rule: dict) -> tuple[list[dict], list[dict]]:
    """(kept, dropped) for pages that are copies of the same document (or one page). A
    person's explicit archive flag wins; otherwise the best-ranked copy is kept."""
    if any("archive" in p for p in group):
        kept = [p for p in group if p.get("archive", True)]
        return kept, [p for p in group if p not in kept]
    if len(group) == 1:
        return group, []
    best = max(group, key=lambda p: rank(p, rule))
    return [best], [p for p in group if p is not best]


def ta_numbers(p: dict, excluded: bool = False) -> list[str]:
    return [t["ta"] for t in p.get("ta") or [] if bool(t.get("excluded")) == excluded]


def organize(pages: list[dict], tour: str | None, rules: dict, ta_validated: bool = False) -> dict:
    """Run all organisational checks. Returns checks (code, level, params) and the result:
    cmr_order / ls_order (page numbers to archive, in archive order), duplicates
    {page: kept page}, other_tour {page: tour}, missing_cmr, unclear pages per kind."""
    checks: list[dict] = []

    def add(code, level, hint=False, **params):
        checks.append({"code": code, "level": level, "params": params, "hint": hint})

    by_type: dict[str, list[dict]] = {}
    for p in pages:
        by_type.setdefault(p.get("doc_type") if p.get("doc_type") in KNOWN_TYPES else "unsicher", []).append(p)
    unclear_dt = [p["n"] for p in by_type.get("unsicher", [])]
    if unclear_dt:
        add("doctype_unclear", ERROR, pages=unclear_dt)
    else:
        add("doctype_ok", OK, n=len(pages), cmr=len(by_type.get("cmr", [])),
            ls=len(by_type.get("lieferschein", [])), ll=len(by_type.get("loading_list", [])))

    # ---------------------------------------------------------------- tour number
    this_tour, other_tour, unread_tour = [], {}, []
    for p in pages:
        if p.get("doc_type") not in REVIEW_TYPES:
            continue
        t = p.get("tour") or {}
        if t.get("accepted") and tour and t.get("text") != tour:
            other_tour[p["n"]] = t["text"]
            continue
        this_tour.append(p)
        if not t.get("accepted"):
            unread_tour.append(p["n"])
    if not tour:
        add("tour_unknown", ERROR)
    if other_tour:
        add("tour_other", HINT, items=[{"page": n, "tour": t} for n, t in other_tour.items()])
    if unread_tour and tour:
        add("tour_unread", HINT, pages=unread_tour, tour=tour)
    if tour and not other_tour and not unread_tour:
        add("tour_ok", OK, tour=tour)

    duplicates: dict[int, int] = {}
    not_archived: list[int] = []   # the person unticked every copy

    # ---------------------------------------------------------------- CMR
    cmr_rule = rules.get("cmr") or {}
    cmrs = [p for p in this_tour if p["doc_type"] == "cmr"]
    by_i: dict[int, list[dict]] = {}
    unread_count = []
    for p in cmrs:
        parsed = (p.get("cmr_count") or {}).get("parsed")
        if parsed:
            by_i.setdefault(int(parsed[0]), []).append(p)
        elif p.get("archive", True):
            unread_count.append(p)
        else:
            not_archived.append(p["n"])
    kept_cmr, cmr_dups = [], []
    for i in sorted(by_i):
        kept, dropped = dedupe(by_i[i], cmr_rule)
        kept_cmr += kept
        for d in dropped:
            if kept:
                duplicates[d["n"]] = kept[0]["n"]
                cmr_dups.append({"dup": d["n"], "keep": kept[0]["n"]})
            else:
                not_archived.append(d["n"])
    missing_cmr, total = [], None
    if not cmrs:
        add("cmr_none", HINT)
    else:
        if unread_count:
            add("cmr_unread", ERROR, pages=[p["n"] for p in unread_count])
        counts = [tuple(p["cmr_count"]["parsed"]) for p in kept_cmr]
        if counts:
            st = stack_complete(counts)
            totals = sorted({y for _, y in counts})
            if len(totals) > 1:
                add("cmr_conflict", ERROR, totals=[f"/{t}" for t in totals])
            else:
                total = totals[0]
                seen = {x for x, _ in counts}
                missing_cmr = [i for i in range(1, total + 1) if i not in seen]
                if missing_cmr:
                    add("cmr_missing", ERROR, missing=missing_cmr, total=total)
                elif st["complete"] and not unread_count:
                    add("cmr_complete", OK, n=total)
        if cmr_dups:
            add("cmr_dup", HINT, items=cmr_dups)
    cmr_order = [p["n"] for p in sorted(kept_cmr, key=lambda p: (p["cmr_count"]["parsed"][0], p["n"]))]
    cmr_order += [p["n"] for p in unread_count]

    # ---------------------------------------------------------------- Lieferscheine
    ls_rule = rules.get("lieferschein") or {}
    lss = [p for p in this_tour if p["doc_type"] == "lieferschein"]
    groups: dict[tuple, list[dict]] = {}
    for p in lss:
        key = tuple(sorted(set(ta_numbers(p)))) or ("page", p["n"])
        groups.setdefault(key, []).append(p)
    kept_ls, ls_dups = [], []
    for g in groups.values():
        kept, dropped = dedupe(g, ls_rule)
        kept_ls += kept
        for d in dropped:
            if kept:
                duplicates[d["n"]] = kept[0]["n"]
                ls_dups.append({"dup": d["n"], "keep": kept[0]["n"]})
            else:
                not_archived.append(d["n"])
    ls_order = sorted(p["n"] for p in kept_ls)
    if lss:
        add("ls_count", OK, n=len(ls_order))
    else:
        add("ls_none", HINT)
    if ls_dups:
        add("ls_dup", HINT, items=ls_dups)

    # ---------------------------------------------------------------- TA numbers
    ta = None
    lists = by_type.get("loading_list", [])
    ta_level = ERROR if ta_validated else HINT
    hint = not ta_validated
    if not lists:
        add("ta_no_list", HINT)
    else:
        loaded, excluded = [], []
        for p in lists:
            for t in ta_numbers(p):
                if t not in loaded:
                    loaded.append(t)
            for t in ta_numbers(p, excluded=True):
                if t not in excluded:
                    excluded.append(t)
        excluded = [t for t in excluded if t not in loaded]
        if not loaded:
            add("ta_none", HINT, hint=hint)
        else:
            cmr_tas = {t for p in kept_cmr + unread_count for t in ta_numbers(p)}
            ls_tas = {t for p in kept_ls for t in ta_numbers(p)}
            cmr_missing = [t for t in loaded if t not in cmr_tas]
            ls_missing = [t for t in loaded if t not in ls_tas]
            add("ta_list", OK, hint=hint, n=len(loaded), excluded=excluded)
            if cmr_missing:
                add("ta_cmr_missing", ta_level, hint=hint, tas=cmr_missing)
            if ls_missing:
                add("ta_ls_missing", ta_level, hint=hint, tas=ls_missing)
            if len(ls_order) != len(loaded):
                add("ta_ls_count", ta_level, hint=hint, ls=len(ls_order), ta=len(loaded))
            if not cmr_missing and not ls_missing and len(ls_order) == len(loaded):
                add("ta_ok", OK, hint=hint)
            ta = {"loaded": loaded, "excluded": excluded, "cmr_missing": cmr_missing, "ls_missing": ls_missing}

    return {
        "tour": tour, "checks": checks, "complete": not any(c["level"] == ERROR for c in checks),
        "cmr_order": cmr_order, "ls_order": ls_order, "cmr_total": total, "missing_cmr": missing_cmr,
        "duplicates": duplicates, "not_archived": sorted(not_archived), "other_tour": other_tour, "ta": ta,
        "unclear": {"doc_type": unclear_dt, "tour": unread_tour, "cmr_count": [p["n"] for p in unread_count]},
    }
