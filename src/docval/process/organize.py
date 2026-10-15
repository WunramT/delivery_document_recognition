"""Organisational checks of one tour - automatic, before a person looks at the stamps.

Input: one record per scanned page (built by run.py, corrected by the person's decision
in finalize.py). Only the fields used here matter:

    {"n": 7,                                   # page number in the scan batch (1-based)
     "doc_type": "cmr" | "lieferschein" | "loading_list" | "unsicher",
     "tour": {"text": "503/01.09.2026/4000", "accepted": True} | None,
     "cmr_count": {"parsed": [3, 13]} | None,
     "ta": [{"ta": "12283251", "excluded": False}, ...],  # loading list / CMR (ta_nummer boxes)
     "ls_number": "12283251", "ls_page": [1, 2],          # Lieferschein (number = TA, "Seite 1/2")
     "page_of": [2, 6],                                   # loading list page "2/6"
     "proposal": {"unterschrift": "ja" | "nein" | "unsicher", ...}, "scores": {cls: float},
     "decision": {"unterschrift": bool, ...},  # optional, from the person
     "archive": bool}                          # optional, set by the person (duplicates)

What it does (process steps 1 and 3 of the sales department):
- doc type of every page known?
- tour number: pages of another tour (additional load) and unreadable ones
- CMR: duplicates (same "CMR i/n" twice -> keep the better copy), stack complete 1..n,
  sort order by i
- Lieferscheine: one Lieferschein per TA, its number IS the TA number ("ls_number"); a
  multi-page Lieferschein shares the number ("ls_page": [i, n]). Same number and page twice
  -> duplicate (keep the copy with stamp/signature)
- Lieferschein complete: pages 1..n of every number ("Seite i/n"); loading list: pages 1..n
- TA numbers: loaded TAs = loading list minus the ones the person struck out (excluded);
  CMR: missing TAs and TAs that are not on the loading list; Lieferschein per loaded TA by its
  number, and Lieferscheine whose number is not on the loading list. A hint until validated.

Everything that is missing is also returned as a list of items with a stable key
(missing_items), e.g. "cmr:3" or "ta_ls:12283251". The person can accept an item anyway
(with a reason, `accepted` = set of keys): it no longer counts as an error.

Plain dicts and loops (portable to JS like the rest of the pipeline).
"""

from __future__ import annotations

from ..ocr.postprocess import stack_complete

REVIEW_TYPES = ("cmr", "lieferschein")
KNOWN_TYPES = ("cmr", "lieferschein", "loading_list", "bestaetigung", "abholschein")
DISCARD_TYPES = ("abholschein",)   # recognized, not part of the check, not archived
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


def missing_pages(pages_of: list[list[int] | None]) -> list[int]:
    """Pages i of "i/n" that are not there (n = the largest total read); [] if no total read."""
    got = [x for x in pages_of if x]
    if not got:
        return []
    n = max(x[1] for x in got)
    seen = {x[0] for x in got}
    return [i for i in range(1, n + 1) if i not in seen]


def organize(pages: list[dict], tour: str | None, rules: dict, ta_validated: bool = False,
             accepted=()) -> dict:
    """Run all organisational checks. Returns checks (code, level, params) and the result:
    cmr_order / ls_order (page numbers to archive, in archive order), duplicates
    {page: kept page}, other_tour {page: tour}, missing_cmr, unclear pages per kind and
    missing_items [{key, code, params, level, accepted}]."""
    checks: list[dict] = []
    items: list[dict] = []
    accepted = set(accepted or ())

    def add(code, level, hint=False, **params):
        checks.append({"code": code, "level": level, "params": params, "hint": hint})

    def item(key, code, level, **params):
        items.append({"key": key, "code": code, "level": level, "params": params, "accepted": key in accepted})
        return key not in accepted

    by_type: dict[str, list[dict]] = {}
    for p in pages:
        by_type.setdefault(p.get("doc_type") if p.get("doc_type") in KNOWN_TYPES else "unsicher", []).append(p)
    unclear_dt = [p["n"] for p in by_type.get("unsicher", [])]
    if unclear_dt:
        add("doctype_unclear", ERROR, pages=unclear_dt)
    else:
        add("doctype_ok", OK, n=len(pages), cmr=len(by_type.get("cmr", [])),
            ls=len(by_type.get("lieferschein", [])), ll=len(by_type.get("loading_list", [])))
    discarded = [p["n"] for t in DISCARD_TYPES for p in by_type.get(t, [])]
    if discarded:
        add("discarded", HINT, pages=sorted(discarded))

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
                open_cmr = [i for i in missing_cmr if item(f"cmr:{i}", "item_cmr", ERROR, i=i, total=total)]
                if open_cmr:
                    add("cmr_missing", ERROR, missing=open_cmr, total=total)
                if len(open_cmr) < len(missing_cmr):
                    add("cmr_missing_accepted", HINT, missing=[i for i in missing_cmr if i not in open_cmr])
                if not missing_cmr and st["complete"] and not unread_count:
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
        num, pg = p.get("ls_number"), p.get("ls_page")
        key = (num, pg[0]) if num and pg else ("page", p["n"])   # copies: same number, same page
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
    # archive order: Lieferscheine in scan order of their first page, pages of one number 1..n
    first: dict[str, int] = {}
    for p in sorted(kept_ls, key=lambda p: p["n"]):
        if p.get("ls_number"):
            first.setdefault(p["ls_number"], p["n"])
    ls_order = [p["n"] for p in sorted(kept_ls, key=lambda p: (
        first.get(p.get("ls_number"), p["n"]), (p.get("ls_page") or [0])[0] if p.get("ls_number") else 0, p["n"]))]
    ls_numbers = sorted({p["ls_number"] for p in kept_ls if p.get("ls_number")})
    ls_unread = [p["n"] for p in kept_ls if not p.get("ls_number")]
    if lss:
        add("ls_count", OK, n=len(ls_numbers) or len(ls_order))
    else:
        add("ls_none", HINT)
    if ls_unread:
        add("ls_unread", HINT, pages=ls_unread)
    if ls_dups:
        add("ls_dup", HINT, items=ls_dups)
    ls_incomplete = []
    for num in ls_numbers:
        miss = missing_pages([p.get("ls_page") for p in kept_ls if p.get("ls_number") == num])
        n_of = max((p.get("ls_page") or [0, 0])[1] for p in kept_ls if p.get("ls_number") == num)
        open_ = [i for i in miss if item(f"ls:{num}:{i}", "item_ls_page", ERROR, number=num, i=i, total=n_of)]
        if open_:
            ls_incomplete.append({"number": num, "missing": open_, "total": n_of})
    for x in ls_incomplete:
        add("ls_incomplete", ERROR, number=x["number"], missing=x["missing"], total=x["total"])

    # ---------------------------------------------------------------- TA numbers
    ta = None
    lists = by_type.get("loading_list", [])
    ta_level = ERROR if ta_validated else HINT
    hint = not ta_validated
    if lists:
        ll_total = max([(p.get("page_of") or [0, 0])[1] for p in lists])
        ll_open = [i for i in missing_pages([p.get("page_of") for p in lists])
                   if item(f"ll:{i}", "item_ll_page", ERROR, i=i, total=ll_total)]
        if ll_open:
            add("ll_incomplete", ERROR, missing=ll_open, total=ll_total)
    ta_unread = [p["n"] for p in lists + kept_cmr + unread_count if p.get("ta_unread")]
    if ta_unread:
        add("ta_unread", HINT, hint=hint, pages=sorted(ta_unread))
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
            cmr_tas = []
            for p in kept_cmr + unread_count:
                cmr_tas += [t for t in ta_numbers(p) if t not in cmr_tas]
            cmr_missing = [t for t in loaded if t not in cmr_tas
                           and item(f"ta_cmr:{t}", "item_ta_cmr", ta_level, ta=t)]
            cmr_extra = [t for t in cmr_tas if t not in loaded and t not in excluded
                         and item(f"ta_cmr_extra:{t}", "item_ta_cmr_extra", ta_level, ta=t)]
            ls_missing = [t for t in loaded if t not in ls_numbers
                          and item(f"ta_ls:{t}", "item_ta_ls", ta_level, ta=t)]
            ls_extra = [t for t in ls_numbers if t not in loaded and t not in excluded
                        and item(f"ta_ls_extra:{t}", "item_ta_ls_extra", ta_level, ta=t)]
            add("ta_list", OK, hint=hint, n=len(loaded), excluded=excluded)
            if cmr_missing:
                add("ta_cmr_missing", ta_level, hint=hint, tas=cmr_missing)
            if cmr_extra:
                add("ta_cmr_extra", ta_level, hint=hint, tas=cmr_extra)
            if ls_missing:
                add("ta_ls_missing", ta_level, hint=hint, tas=ls_missing)
            if ls_extra:
                add("ta_ls_extra", ta_level, hint=hint, tas=ls_extra)
            if not (cmr_missing or cmr_extra or ls_missing or ls_extra):
                add("ta_ok", OK, hint=hint)
            n_acc = sum(1 for x in items if x["accepted"] and x["code"].startswith("item_ta"))
            if n_acc:
                add("ta_accepted", HINT, n=n_acc)
            ta = {"loaded": loaded, "excluded": excluded, "cmr_missing": cmr_missing, "cmr_extra": cmr_extra,
                  "ls_missing": ls_missing, "ls_extra": ls_extra}

    n_acc = sum(1 for x in items if x["accepted"] and x["code"] in ("item_ls_page", "item_ll_page"))
    if n_acc:
        add("accepted", HINT, n=n_acc)
    return {
        "tour": tour, "checks": checks, "complete": not any(c["level"] == ERROR for c in checks),
        "missing_items": items, "ls_incomplete": ls_incomplete,
        "cmr_order": cmr_order, "ls_order": ls_order, "cmr_total": total, "missing_cmr": missing_cmr,
        "duplicates": duplicates, "not_archived": sorted(not_archived), "discarded": sorted(discarded), "other_tour": other_tour, "ta": ta,
        "unclear": {"doc_type": unclear_dt, "tour": unread_tour, "cmr_count": [p["n"] for p in unread_count],
                    "ls_number": ls_unread, "ta": sorted(ta_unread)},
    }
