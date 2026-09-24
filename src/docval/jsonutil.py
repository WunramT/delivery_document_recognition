"""JSON helpers: numpy scalars/arrays and Paths are written as plain values."""

from __future__ import annotations

import json
from pathlib import Path


def to_plain(o):
    """`default=` hook for json.dumps."""
    if hasattr(o, "item") and callable(o.item) and getattr(o, "shape", None) == ():
        return o.item()          # numpy scalar (float32, int64, bool_)
    if hasattr(o, "tolist"):
        return o.tolist()        # numpy array
    if isinstance(o, (Path, set, tuple)):
        return str(o) if isinstance(o, Path) else list(o)
    return str(o)


def dumps(obj, **kw) -> str:
    kw.setdefault("indent", 2)
    kw.setdefault("ensure_ascii", False)
    return json.dumps(obj, default=to_plain, **kw)
