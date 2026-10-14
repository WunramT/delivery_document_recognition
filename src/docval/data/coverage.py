"""Which classes is each export labeled for?

An export counts as labeled for a class when its COCO file has that category - the label
editor writes every class of config `classes`, so a tour saved after new classes were added
is labeled for them even where a page has no such object. Exports from before (without the
category) are not: an unlabeled TA number there is not "background".
"""

from __future__ import annotations

from ..config import resolve
from .coco import load_coco


def labeled_classes(cfg: dict) -> dict[str, set[str]]:
    """{export name: classes of config `classes` it is labeled for}."""
    classes = set(cfg["classes"])
    exports = (cfg.get("_exports") or {}).get("exports")
    if exports:
        return {e["name"]: set(e.get("categories") or []) & classes for e in exports}
    coco = resolve(cfg["paths"]["coco"])
    return {coco.parent.name: {c["name"] for c in load_coco(coco)["categories"]} & classes}


def page_exports(cfg: dict) -> dict[str, str]:
    """{file_name of a page (as in load_pages): export name}."""
    coco = resolve(cfg["paths"]["coco"])
    data = load_coco(coco)
    return {img["file_name"]: img.get("export", coco.parent.name) for img in data["images"]}


def partial_classes(coverage: dict[str, set[str]], classes: list[str]) -> dict[str, list[str]]:
    """{class: exports NOT labeled for it} for classes labeled in some exports only."""
    out = {}
    for c in classes:
        missing = sorted(e for e, have in coverage.items() if c not in have)
        if missing and len(missing) < len(coverage):
            out[c] = missing
    return out


def complete_exports(coverage: dict[str, set[str]], classes: list[str]) -> list[str]:
    """Exports labeled for every class."""
    return sorted(e for e, have in coverage.items() if set(classes) <= have)
