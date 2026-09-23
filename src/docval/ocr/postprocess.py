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
DEFAULT_SEPARATOR_MAP = {"\\": "/", "⁄": "/", "∕": "/"}
# only used as separator when no "/" is present and it occurs exactly once
DEFAULT_AMBIGUOUS_SEPARATORS = ["|"]


def normalize(text: str) -> str:
    """Remove whitespace and common OCR punctuation noise at the ends."""
    t = "".join(ch for ch in text if not ch.isspace())
    return t.strip(".,;:'\"`-_")


def correct(text: str, regex: str, digit_map: dict[str, str] | None = None,
            separator_map: dict[str, str] | None = None) -> tuple[str, list[str]]:
    """Format-aware correction for the pattern <digits>/<digits>.

    Returns (corrected, list of applied changes). Characters are only mapped
    to digits in positions where the format expects digits, i.e. everywhere
    except the single separator. If the text already matches, nothing changes.
    """
    digit_map = DEFAULT_DIGIT_MAP if digit_map is None else digit_map
    separator_map = DEFAULT_SEPARATOR_MAP if separator_map is None else separator_map
    t = normalize(text)
    if re.fullmatch(regex, t):
        return t, []
    changes = []
    chars = list(t)
    # 1. separator variants -> "/"
    for i, ch in enumerate(chars):
        if ch in separator_map:
            changes.append(f"{ch}->{separator_map[ch]}@{i}")
            chars[i] = separator_map[ch]
    # 1b. "200|01": ambiguous separator, only if no real one exists
    if "/" not in chars:
        for amb in DEFAULT_AMBIGUOUS_SEPARATORS:
            if chars.count(amb) == 1:
                i = chars.index(amb)
                changes.append(f"{amb}->/@{i}")
                chars[i] = "/"
                break
    # 2. with exactly one "/", map look-alikes on both sides to digits
    if chars.count("/") == 1:
        for i, ch in enumerate(chars):
            if ch != "/" and not ch.isdigit() and ch in digit_map:
                changes.append(f"{ch}->{digit_map[ch]}@{i}")
                chars[i] = digit_map[ch]
    return "".join(chars), changes


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
