"""Config loading. Values like "${DOCVAL_DATA:-labels}/x" are expanded from env."""

from __future__ import annotations

import os
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
_ENV = re.compile(r"\$\{(\w+)(?::-([^}]*))?\}")


def _expand(v):
    if isinstance(v, str):
        return _ENV.sub(lambda m: os.environ.get(m.group(1), m.group(2) or ""), v)
    if isinstance(v, dict):
        return {k: _expand(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_expand(x) for x in v]
    return v


def deep_merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config(path: str | Path | None = None) -> dict:
    """Load YAML config. A config may say `extends: other.yaml` (relative to
    itself) and only override some keys (used by configs/smoke.yaml)."""
    path = Path(path or os.environ.get("DOCVAL_CONFIG") or ROOT / "config.yaml")
    if not path.is_absolute():
        path = ROOT / path
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    if "extends" in raw:
        base = load_config(path.parent / raw.pop("extends"))
        base.pop("_path", None)
        raw = deep_merge(base, raw)
    cfg = _expand(raw)
    cfg["_path"] = str(path)
    return cfg


def resolve(p: str | Path) -> Path:
    p = Path(p)
    return p if p.is_absolute() else ROOT / p


def artifacts(cfg: dict, *parts: str) -> Path:
    return resolve(cfg["paths"]["artifacts"]).joinpath(*parts)
