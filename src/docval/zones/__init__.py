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


def overlap_fraction(box: list[float], zone: list[float]) -> float:
    """Share of `box` area that lies inside `zone`."""
    ix = max(0.0, min(box[2], zone[2]) - max(box[0], zone[0]))
    iy = max(0.0, min(box[3], zone[3]) - max(box[1], zone[1]))
    area = (box[2] - box[0]) * (box[3] - box[1])
    return (ix * iy) / area if area > 0 else 0.0


def check_requirement(cls: str, zone: list[float] | None, detections: list[dict],
                      min_overlap: float, score_accept: float, score_uncertain: float) -> dict:
    """detections: [{"cls", "box" (normalized), "score"}]. Returns status + reason."""
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
    if strong_out:
        d = max(strong_out, key=lambda x: x["score"])
        c = [(d["box"][0] + d["box"][2]) / 2, (d["box"][1] + d["box"][3]) / 2]
        return {"cls": cls, "status": WRONG_POSITION,
                "reason": f"{_name(cls)} erkannt, aber außerhalb der Soll-Zone (Zentrum {c[0]:.2f}/{c[1]:.2f})"}
    return {"cls": cls, "status": MISSING, "reason": f"{_none(cls)} erkannt"}


# severity order when combining several requirements with mode "all"
_SEVERITY = {OK: 0, UNCERTAIN: 1, WRONG_POSITION: 2, MISSING: 3}


def check_page(doc_type: str | None, detections: list[dict], zones: dict, rules: dict,
               min_overlap: float, score_accept: float, score_uncertain: float) -> dict:
    """Position check for one page.

    rules: {doc_type: {"require": [cls, ...], "mode": "all" | "any"}}
    """
    if doc_type is None or doc_type == UNCERTAIN:
        return {"status": UNCERTAIN, "reason": "Dokumenttyp unsicher", "details": []}
    rule = rules.get(doc_type)
    if not rule or not rule.get("require"):
        return {"status": NOT_REQUIRED, "reason": f"für {doc_type} nichts gefordert", "details": []}
    dz = zones.get(doc_type, {})
    details = []
    for cls in rule["require"]:
        z = dz.get(cls)
        details.append(check_requirement(cls, z["box"] if z else None, detections,
                                         min_overlap, score_accept, score_uncertain))
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
    reason = "; ".join(d["reason"] for d in details)
    return {"status": status, "reason": reason, "details": details}
