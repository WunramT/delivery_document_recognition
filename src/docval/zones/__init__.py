"""Target zones for signature/stamp and the rule-based position check.

All coordinates are normalized to 0..1 (x1, y1, x2, y2). No numpy, plain
loops and dicts, so this file can be ported 1:1 to JavaScript.
"""

from __future__ import annotations

OK = "ok"
MISSING = "fehlt"
WRONG_POSITION = "falsche_position"
UNCERTAIN = "unsicher"
NOT_REQUIRED = "nicht_gefordert"

# display name and negation article for the reason texts
DISPLAY = {"unterschrift": ("Unterschrift", "keine"), "stempel": ("Stempel", "kein"),
           "tour_nummer": ("Tournummer", "keine"), "cmr_count": ("CMR-Zählung", "keine")}


def _name(cls: str) -> str:
    return DISPLAY.get(cls, (cls, "kein"))[0]


def _none(cls: str) -> str:
    n, art = DISPLAY.get(cls, (cls, "kein"))
    return f"{art} {n}"


def percentile(values: list[float], p: float) -> float:
    v = sorted(values)
    if not v:
        raise ValueError("empty")
    pos = (len(v) - 1) * p / 100
    lo = int(pos)
    hi = min(lo + 1, len(v) - 1)
    return v[lo] + (v[hi] - v[lo]) * (pos - lo)


def clamp01(v: float) -> float:
    return 0.0 if v < 0 else 1.0 if v > 1 else v


def derive_zones(samples: dict, p_lo: float, p_hi: float, margin: float,
                 min_samples: int) -> dict:
    """samples: {doc_type: {cls: [norm_box, ...]}} -> {doc_type: {cls: zone}}.

    Zone = rectangle spanned by the p_lo..p_hi percentiles of the box *centers*,
    grown by `margin` (fraction of the page) plus half the median box size, so
    a typical box centered at the zone edge still lies mostly inside.
    """
    zones: dict = {}
    for doc_type, by_cls in samples.items():
        for cls, boxes in by_cls.items():
            if len(boxes) < min_samples:
                continue
            cx = [(b[0] + b[2]) / 2 for b in boxes]
            cy = [(b[1] + b[3]) / 2 for b in boxes]
            half_w = percentile([b[2] - b[0] for b in boxes], 50) / 2
            half_h = percentile([b[3] - b[1] for b in boxes], 50) / 2
            zone = [
                clamp01(percentile(cx, p_lo) - half_w - margin),
                clamp01(percentile(cy, p_lo) - half_h - margin),
                clamp01(percentile(cx, p_hi) + half_w + margin),
                clamp01(percentile(cy, p_hi) + half_h + margin),
            ]
            zones.setdefault(doc_type, {})[cls] = {
                "box": [round(z, 4) for z in zone],
                "n_samples": len(boxes),
            }
    return zones


def apply_overrides(zones: dict, overrides: dict) -> dict:
    """Manual corrections from config: {doc_type: {cls: {x1?, y1?, x2?, y2?}}}.
    Only the given edges replace the derived ones (e.g. widen CMR to fields 22-24)."""
    keys = ["x1", "y1", "x2", "y2"]
    out = {t: {c: dict(z) for c, z in zz.items()} for t, zz in zones.items()}
    for doc_type, by_cls in (overrides or {}).items():
        for cls, edges in by_cls.items():
            z = out.setdefault(doc_type, {}).setdefault(cls, {"box": [0.0, 0.0, 1.0, 1.0], "n_samples": 0})
            box = list(z["box"])
            for i, k in enumerate(keys):
                if k in edges:
                    box[i] = float(edges[k])
            z["box"] = box
            z["override"] = {k: edges[k] for k in keys if k in edges}
    return out


def _thr(t, cls: str) -> float:
    """Threshold may be a number or a {cls: number} dict."""
    return t[cls] if isinstance(t, dict) else t


def overlap_fraction(box: list[float], zone: list[float]) -> float:
    """Share of `box` area that lies inside `zone`."""
    ix = max(0.0, min(box[2], zone[2]) - max(box[0], zone[0]))
    iy = max(0.0, min(box[3], zone[3]) - max(box[1], zone[1]))
    area = (box[2] - box[0]) * (box[3] - box[1])
    return (ix * iy) / area if area > 0 else 0.0


def check_requirement(cls: str, zone: list[float] | None, detections: list[dict],
                      min_overlap: float, score_accept, score_uncertain, optional: bool = False,
                      review_zones: dict | None = None) -> dict:
    """detections: [{"cls", "box" (normalized), "score"}]. Returns status + reason.

    optional=True: the object is not required, but if it is present it must be in
    the zone (absent -> ok, only outside -> falsche_position).
    review_zones: {name: {"box": [...], "action": "review" | "ok"}} - allowed secondary
    places (e.g. CMR field 13). An object found only there -> "unsicher" (a person
    checks) or "ok", instead of "falsche_position".
    """
    score_accept, score_uncertain = _thr(score_accept, cls), _thr(score_uncertain, cls)
    if zone is None and optional:
        return {"cls": cls, "status": OK, "reason": f"{_name(cls)} optional, keine Zone definiert"}
    if zone is None:
        return {"cls": cls, "status": UNCERTAIN, "reason": f"keine Zone für {_name(cls)} definiert"}
    strong_in, weak_in, strong_out = [], [], []
    for d in detections:
        if d["cls"] != cls or d["score"] < score_uncertain:
            continue
        inside = overlap_fraction(d["box"], zone) >= min_overlap
        if d["score"] >= score_accept:
            (strong_in if inside else strong_out).append(d)
        elif inside:
            weak_in.append(d)
    if strong_in:
        best = max(d["score"] for d in strong_in)
        return {"cls": cls, "status": OK, "reason": f"{_name(cls)} in Soll-Zone (Score {best:.2f})"}
    if weak_in:
        best = max(d["score"] for d in weak_in)
        return {"cls": cls, "status": UNCERTAIN,
                "reason": f"{_name(cls)} in Soll-Zone nur mit niedrigem Score {best:.2f}"}
    for name, rz in (review_zones or {}).items():
        hits = [d for d in strong_out if overlap_fraction(d["box"], rz["box"]) >= min_overlap]
        if hits:
            best = max(d["score"] for d in hits)
            if rz.get("action", "review") == "ok":
                return {"cls": cls, "status": OK, "review": name,
                        "reason": f"{_name(cls)} in {name} (zugelassen, Score {best:.2f})"}
            return {"cls": cls, "status": UNCERTAIN, "review": name,
                    "reason": f"{_name(cls)} in {name} (zugelassen, Prüfung durch Person, Score {best:.2f})"}
    if strong_out:
        d = max(strong_out, key=lambda x: x["score"])
        c = [(d["box"][0] + d["box"][2]) / 2, (d["box"][1] + d["box"][3]) / 2]
        return {"cls": cls, "status": WRONG_POSITION,
                "reason": f"{_name(cls)} erkannt, aber außerhalb der Soll-Zone (Zentrum {c[0]:.2f}/{c[1]:.2f})"}
    if optional:
        return {"cls": cls, "status": OK, "reason": f"{_none(cls)} erkannt (nicht gefordert)"}
    return {"cls": cls, "status": MISSING, "reason": f"{_none(cls)} erkannt"}


def box_center_in(box: list[float], zone: list[float]) -> bool:
    cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    return zone[0] <= cx <= zone[2] and zone[1] <= cy <= zone[3]


def check_fields(fields: dict, detections: list[dict], score_accept, score_uncertain) -> list[dict]:
    """Form fields (e.g. CMR 22/23/24), each with required classes.

    fields: {name: {"box": [x1, y1, x2, y2], "require": [cls, ...]}}
    A detection belongs to the field that contains its box center (so one
    signature cannot count for two neighbouring fields). Every field must have
    each required class; returns one detail per (field, class).
    """
    details = []
    for name, f in fields.items():
        for cls in f.get("require") or []:
            a, u = _thr(score_accept, cls), _thr(score_uncertain, cls)
            inside = [d for d in detections if d["cls"] == cls and d["score"] >= u
                      and box_center_in(d["box"], f["box"])]
            strong = [d for d in inside if d["score"] >= a]
            if strong:
                best = max(d["score"] for d in strong)
                details.append({"cls": cls, "field": name, "status": OK,
                                "reason": f"Feld {name}: {_name(cls)} (Score {best:.2f})"})
            elif inside:
                best = max(d["score"] for d in inside)
                details.append({"cls": cls, "field": name, "status": UNCERTAIN,
                                "reason": f"Feld {name}: {_name(cls)} nur mit niedrigem Score {best:.2f}"})
            else:
                details.append({"cls": cls, "field": name, "status": MISSING,
                                "reason": f"Feld {name}: {_none(cls)}"})
    return details


# severity order when combining several requirements with mode "all"
_SEVERITY = {OK: 0, UNCERTAIN: 1, WRONG_POSITION: 2, MISSING: 3}


def check_page(doc_type: str | None, detections: list[dict], zones: dict, rules: dict,
               min_overlap: float, score_accept: float, score_uncertain: float) -> dict:
    """Position check for one page.

    rules: {doc_type: {"require": [cls, ...], "mode": "all" | "any", "optional": [cls, ...],
                       "fields": {name: {"box": [...], "require": [cls, ...]}}}}
    score_accept / score_uncertain: number or {cls: number}.
    With "fields" the page is only ok if every field has all its required classes.
    """
    if doc_type is None or doc_type == UNCERTAIN:
        return {"status": UNCERTAIN, "reason": "Dokumenttyp unsicher", "details": []}
    rule = rules.get(doc_type) or {}
    if rule.get("fields"):
        details = check_fields(rule["fields"], detections, score_accept, score_uncertain)
        status = OK
        for d in details:
            if _SEVERITY[d["status"]] > _SEVERITY[status]:
                status = d["status"]
        missing = [d for d in details if d["status"] != OK]
        reason = "; ".join(d["reason"] for d in (missing or details))
        return {"status": status, "reason": reason, "details": details}
    required = rule.get("require") or []
    optional = rule.get("optional") or []
    if not required and not optional:
        return {"status": NOT_REQUIRED, "reason": f"für {doc_type} nichts gefordert", "details": []}
    dz = zones.get(doc_type, {})
    details = []
    review = rule.get("review_zones") or {}
    for cls in required:
        z = dz.get(cls)
        rz = {n: r for n, r in review.items() if cls in (r.get("classes") or [cls])}
        details.append(check_requirement(cls, z["box"] if z else None, detections,
                                         min_overlap, score_accept, score_uncertain, review_zones=rz))
    opt_details = []
    for cls in optional:
        z = dz.get(cls)
        opt_details.append(check_requirement(cls, z["box"] if z else None, detections,
                                             min_overlap, score_accept, score_uncertain, optional=True))
    if not required:
        status = OK
        for d in opt_details:
            if _SEVERITY[d["status"]] > _SEVERITY[status]:
                status = d["status"]
        return {"status": status, "reason": "; ".join(d["reason"] for d in opt_details),
                "details": opt_details}
    mode = rule.get("mode", "all")
    if mode == "any":
        statuses = [d["status"] for d in details]
        if OK in statuses:
            status = OK
        elif UNCERTAIN in statuses:
            status = UNCERTAIN
        elif WRONG_POSITION in statuses:
            status = WRONG_POSITION
        else:
            status = MISSING
    else:
        status = OK
        for d in details:
            if _SEVERITY[d["status"]] > _SEVERITY[status]:
                status = d["status"]
    # an optional object in the wrong place still counts as wrong position
    for d in opt_details:
        if d["status"] == WRONG_POSITION and _SEVERITY[WRONG_POSITION] > _SEVERITY[status]:
            status = WRONG_POSITION
    details = details + opt_details
    reason = "; ".join(d["reason"] for d in details)
    return {"status": status, "reason": reason, "details": details}
