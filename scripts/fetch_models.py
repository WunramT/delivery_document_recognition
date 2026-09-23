#!/usr/bin/env python3
"""Download all model weights into paths.models (run once, then offline)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from docval.config import load_config  # noqa: E402
from docval.models import fetch_all  # noqa: E402

if __name__ == "__main__":
    fetch_all(load_config())
