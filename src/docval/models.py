"""Model weights: download once into paths.models (a docker volume), then offline.

Env vars set here so rfdetr / timm / huggingface_hub / paddlex all use the cache.
"""

from __future__ import annotations

import os
from pathlib import Path

from .config import resolve

RFDETR_CLASSES = {"nano": "RFDETRNano", "small": "RFDETRSmall", "medium": "RFDETRMedium"}


def setup_cache(cfg: dict) -> Path:
    root = resolve(cfg["paths"]["models"])
    root.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("RF_HOME", str(root / "rfdetr"))
    os.environ.setdefault("HF_HOME", str(root / "hf"))
    os.environ.setdefault("TORCH_HOME", str(root / "torch"))
    os.environ.setdefault("PADDLE_PDX_CACHE_HOME", str(root / "paddlex"))
    os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
    return root


def offline() -> None:
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"


def ocr_model_dir(cfg: dict, repo: str) -> Path:
    return setup_cache(cfg) / "ocr" / repo.split("/")[-1]


def fetch_ocr(cfg: dict, log=print) -> None:
    from huggingface_hub import hf_hub_download

    repos = set()
    for eng in cfg["ocr"]["engines"].values():
        repos.update(eng.values())
    for repo in sorted(repos):
        d = ocr_model_dir(cfg, repo)
        for fn in ("inference.onnx", "inference.yml"):
            if not (d / fn).is_file():
                hf_hub_download(repo, fn, local_dir=str(d))
        log(f"[models] {repo} -> {d}")


def fetch_rfdetr(cfg: dict, log=print) -> None:
    import rfdetr

    size = cfg["detector"]["size"]
    if size not in RFDETR_CLASSES:
        raise ValueError(f"detector.size must be one of {sorted(RFDETR_CLASSES)} (Apache-2.0)")
    getattr(rfdetr, RFDETR_CLASSES[size])(device="cpu")  # downloads into $RF_HOME
    log(f"[models] rfdetr {size} -> {os.environ['RF_HOME']}")


def fetch_timm(cfg: dict, log=print) -> None:
    import timm

    name = cfg["doctype"]["classifier"]["model"]
    timm.create_model(name, pretrained=True)
    log(f"[models] timm {name} -> {os.environ['HF_HOME']}")


def fetch_paddle_reference(cfg: dict, log=print) -> None:
    from paddleocr import TextRecognition

    for eng in cfg["ocr"]["engines"].values():
        name = eng["rec"].split("/")[-1].removesuffix("_onnx")
        TextRecognition(model_name=name)
        log(f"[models] paddle reference {name}")


def fetch_all(cfg: dict, log=print) -> None:
    setup_cache(cfg)
    fetch_ocr(cfg, log)
    fetch_rfdetr(cfg, log)
    if cfg["doctype"]["classifier"].get("enabled"):
        fetch_timm(cfg, log)
    if cfg["ocr"].get("paddle_reference"):
        try:
            fetch_paddle_reference(cfg, log)
        except Exception as e:  # reference is optional
            log(f"[models] paddle reference skipped: {e}")
