"""Doc type from header OCR keywords and combination with the image classifier.

Plain string logic (portable to JS).
"""

from __future__ import annotations

import unicodedata

UNCERTAIN = "unsicher"


def fold(text: str) -> str:
    """Lowercase, strip diacritics (ł -> l, ä -> a) and all non-alphanumerics."""
    t = text.lower().replace("ł", "l").replace("ß", "ss")
    t = unicodedata.normalize("NFKD", t)
    return "".join(ch for ch in t if ch.isalnum() and not unicodedata.combining(ch))


def levenshtein(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def fuzzy_contains(haystack: str, needle: str, max_dist: int) -> bool:
    """Does `needle` occur in `haystack` with <= max_dist edits (sliding window)?"""
    if needle in haystack:
        return True
    if max_dist == 0 or len(needle) > len(haystack) + max_dist:
        return False
    n = len(needle)
    for size in (n - 1, n, n + 1):
        if size <= 0:
            continue
        for i in range(0, len(haystack) - size + 1):
            if levenshtein(haystack[i:i + size], needle) <= max_dist:
                return True
    return False


def keyword_scores(text: str, keywords: dict[str, list[str]], fuzzy_min_len: int = 7) -> dict:
    """Return {doc_type: [matched keywords]} for OCR text of the page header.

    Keywords shorter than `fuzzy_min_len` (after folding) must match exactly
    (e.g. 'CMR'); longer ones tolerate one OCR error.
    """
    hay = fold(text)
    hits: dict[str, list[str]] = {}
    for doc_type, kws in keywords.items():
        for kw in kws:
            k = fold(kw)
            if not k:
                continue
            dist = 1 if len(k) >= fuzzy_min_len else 0
            if fuzzy_contains(hay, k, dist):
                hits.setdefault(doc_type, []).append(kw)
    return hits


def keyword_decision(hits: dict[str, list[str]], priority: list[str]) -> tuple[str | None, str]:
    """Exactly one type -> that type. Several -> first in `priority` if configured,
    else None (ambiguous)."""
    if not hits:
        return None, "kein Keyword gefunden"
    if len(hits) == 1:
        t = next(iter(hits))
        return t, f"Keyword {hits[t]}"
    for t in priority:
        if t in hits:
            return t, f"mehrere Typen {sorted(hits)}, Priorität -> {t}"
    return None, f"mehrdeutige Keywords {sorted(hits)}"


def combine(kw_type: str | None, kw_reason: str, clf_type: str | None, clf_conf: float | None,
            min_conf: float, conflict_conf: float) -> dict:
    """Keyword hit beats the classifier. Result is 'unsicher' when
    - there is no keyword hit and the classifier is missing or below `min_conf`, or
    - keyword and classifier disagree and the classifier is confident (>= conflict_conf).
    """
    if kw_type is not None:
        if clf_type is not None and clf_type != kw_type and clf_conf is not None and clf_conf >= conflict_conf:
            return {"doc_type": UNCERTAIN, "source": "konflikt",
                    "reason": f"{kw_reason}, Klassifikator sagt {clf_type} ({clf_conf:.2f})"}
        return {"doc_type": kw_type, "source": "keyword", "reason": kw_reason}
    if clf_type is None:
        return {"doc_type": UNCERTAIN, "source": "keine", "reason": kw_reason + ", kein Klassifikator"}
    if clf_conf is not None and clf_conf >= min_conf:
        return {"doc_type": clf_type, "source": "klassifikator",
                "reason": f"{kw_reason}, Klassifikator {clf_type} ({clf_conf:.2f})"}
    return {"doc_type": UNCERTAIN, "source": "klassifikator_unsicher",
            "reason": f"{kw_reason}, Klassifikator {clf_type} nur {clf_conf:.2f}"}
