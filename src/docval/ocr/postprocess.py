"""Tour number post-processing: normalization, format-aware correction, acceptance.

Plain string operations only (portable to JS).
"""

from __future__ import annotations

import re

DEFAULT_DIGIT_MAP = {
    "O": "0", "o": "0", "D": "0", "Q": "0",
    "I": "1", "l": "1", "i": "1", "|": "1", "!": "1",
    "S": "5", "s": "5",
    "B": "8",
    "Z": "2", "z": "2",
    "G": "6",
}
DEFAULT_SEPARATOR_MAP = {"\\": "/", "⁄": "/", "∕": "/", "|": "/"}
DEFAULT_DOT_MAP = {",": ".", "·": ".", ":": "."}


def normalize(text: str) -> str:
    """Remove whitespace and common OCR punctuation noise at the ends."""
    t = "".join(ch for ch in text if not ch.isspace())
    return t.strip(".,;:'\"`-_")


def _core(regex: str) -> str:
    """Pattern without ^/$ anchors, for searching inside a longer OCR string."""
    r = regex
    if r.startswith("^"):
        r = r[1:]
    if r.endswith("$") and not r.endswith("\\$"):
        r = r[:-1]
    return r


def _loosen(core: str, digit_map: dict, separator_map: dict, dot_map: dict) -> str:
    """Replace \\d, '/' and '\\.' in the pattern by classes that also accept OCR look-alikes."""
    def cls(chars):
        return "[" + "".join(re.escape(c) for c in chars) + "]"

    digit = cls("0123456789" + "".join(digit_map))
    slash = cls("/" + "".join(separator_map))
    dot = cls("." + "".join(dot_map))
    out, i = [], 0
    while i < len(core):
        if core.startswith("\\d", i):
            out.append(digit)
            i += 2
        elif core.startswith("\\.", i):
            out.append(dot)
            i += 2
        elif core[i] == "/":
            out.append(slash)
            i += 1
        elif core[i] == "\\" and i + 1 < len(core):
            out.append(core[i:i + 2])
            i += 2
        else:
            out.append(core[i])
            i += 1
    return "".join(out)


def correct(text: str, regex: str, digit_map: dict[str, str] | None = None,
            separator_map: dict[str, str] | None = None,
            dot_map: dict[str, str] | None = None) -> tuple[str, list[str]]:
    """Format-aware correction for any regex built from \\d, '/' and '\\.'
    (e.g. ^\\d+/\\d{2}\\.\\d{2}\\.\\d{4}/\\d+$).

    1. exact match -> unchanged
    2. the pattern occurs inside the text (label prefix "Tour", trailing noise) -> cut out
    3. a loose pattern that also accepts OCR look-alikes (O->0, l->1, \\->/, ,->.) is
       searched; only inside that span characters are mapped, position by position
       according to what the format expects there (digit, '/', '.').
    Returns (text, list of changes). A result that still does not match is rejected later.
    """
    digit_map = DEFAULT_DIGIT_MAP if digit_map is None else digit_map
    separator_map = DEFAULT_SEPARATOR_MAP if separator_map is None else separator_map
    dot_map = DEFAULT_DOT_MAP if dot_map is None else dot_map
    t = normalize(text)
    if re.fullmatch(regex, t):
        return t, []
    core = _core(regex)
    m = re.search(core, t)
    if m and re.fullmatch(regex, m.group(0)):
        cut = m.group(0)
        return cut, [f"ausgeschnitten '{cut}' aus '{t}'"]
    loose = _loosen(core, digit_map, separator_map, dot_map)
    best = None
    for lm in re.finditer(loose, t):
        span = lm.group(0)
        # try the mapping variants: an ambiguous char ('|') may be a digit or a separator
        cands = [""]
        for ch in span:
            opts = []
            if ch.isdigit() or ch in "/.":
                opts = [ch]
            else:
                if ch in digit_map:
                    opts.append(digit_map[ch])
                if ch in separator_map:
                    opts.append(separator_map[ch])
                if ch in dot_map:
                    opts.append(dot_map[ch])
                if not opts:
                    opts = [ch]
            cands = [c + o for c in cands for o in opts][:64]
        for c in cands:
            if re.fullmatch(regex, c):
                changes = [f"{a}->{b}@{i}" for i, (a, b) in enumerate(zip(span, c)) if a != b]
                if span != t:
                    changes.insert(0, f"ausgeschnitten '{span}' aus '{t}'")
                if best is None or len(changes) < len(best[1]):
                    best = (c, changes)
                break
    if best:
        return best
    return t, []


def evaluate_text(raw: str, score: float, regex: str, min_score: float,
                  digit_map=None, separator_map=None) -> dict:
    corrected, changes = correct(raw, regex, digit_map, separator_map)
    valid = re.fullmatch(regex, corrected) is not None
    accepted = valid and score >= min_score
    if not valid:
        reason = f"Format ungültig: '{corrected}'"
    elif score < min_score:
        reason = f"Konfidenz {score:.2f} < {min_score:.2f}"
    else:
        reason = "ok" + (f" (korrigiert: {', '.join(changes)})" if changes else "")
    return {"raw": raw, "text": corrected, "score": score, "valid_format": valid,
            "accepted": accepted, "corrections": changes, "reason": reason}


def parse_cmr_count(text: str) -> tuple[int, int] | None:
    """'CMR 11/12' -> (11, 12). None if not parseable."""
    t = normalize(text)
    m = re.search(r"(\d{1,3})\s*/\s*(\d{1,3})", t)
    if not m:
        fixed, _ = correct(re.sub(r"(?i)^cmr", "", t), r"^\d+/\d+$")
        m = re.fullmatch(r"(\d{1,3})/(\d{1,3})", fixed)
        if not m:
            return None
    x, y = int(m.group(1)), int(m.group(2))
    if x < 1 or y < 1 or x > y:
        return None
    return x, y


def stack_complete(counts: list[tuple[int, int]]) -> dict:
    """Is a CMR stack complete? counts: parsed (x, y) of the pages of one stack."""
    if not counts:
        return {"complete": False, "reason": "keine Seitenzählung gelesen"}
    totals = {y for _, y in counts}
    if len(totals) != 1:
        return {"complete": False, "reason": f"widersprüchliche Gesamtzahl {sorted(totals)}"}
    y = totals.pop()
    seen = sorted({x for x, _ in counts})
    missing = [i for i in range(1, y + 1) if i not in seen]
    if missing:
        return {"complete": False, "reason": f"fehlende Seiten {missing} von {y}"}
    return {"complete": True, "reason": f"{y} von {y} Seiten"}
