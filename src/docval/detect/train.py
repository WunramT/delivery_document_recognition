"""Train RF-DETR (N/S/M, Apache-2.0), export to ONNX, PyTorch-vs-ONNX parity test."""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

import numpy as np
from PIL import Image

from ..models import RFDETR_CLASSES, setup_cache
from .onnx_detector import OnnxDetector, iou, postprocess, preprocess, sigmoid


def _device(cfg_dev: str) -> str:
    if cfg_dev != "auto":
        return cfg_dev
    import torch

    return "cuda" if torch.cuda.is_available() else "cpu"


def _model_class(size: str):
    import rfdetr

    if size not in RFDETR_CLASSES:
        raise ValueError(f"detector.size must be one of {sorted(RFDETR_CLASSES)} - XL/2XL are not Apache-2.0")
    return getattr(rfdetr, RFDETR_CLASSES[size])


def train(cfg: dict, dataset_dir: Path, out_dir: Path, log=print) -> dict:
    setup_cache(cfg)
    d = cfg["detector"]
    device = _device(d.get("device", "auto"))
    kwargs = {}
    if d.get("resolution"):
        kwargs["resolution"] = d["resolution"]
    model = _model_class(d["size"])(device=device, **kwargs)
    classes = json.loads((dataset_dir / "classes.json").read_text())
    if out_dir.exists():  # never export a stale checkpoint from an earlier run
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    model.train(
        dataset_dir=str(dataset_dir), output_dir=str(out_dir), epochs=d["epochs"],
        batch_size=d["batch_size"], grad_accum_steps=d["grad_accum_steps"], lr=d["lr"],
        num_workers=d.get("num_workers", 2), early_stopping=d.get("early_stopping", False),
        early_stopping_patience=d.get("early_stopping_patience", 10), tensorboard=True,
        seed=cfg.get("seed", 42), class_names=classes, device=device,
        checkpoint_interval=max(1, d["epochs"]), progress_bar=None,
        multi_scale=d.get("multi_scale", False),
    )
    info = {"device": device, "size": d["size"], "train_seconds": round(time.time() - t0, 1),
            "classes": classes}
    (out_dir / "train_info.json").write_text(json.dumps(info, indent=2))
    log(f"[train] done in {info['train_seconds']} s on {device}")
    return info


def best_checkpoint(run_dir: Path) -> Path:
    for n in ("checkpoint_best_total.pth", "checkpoint_best_ema.pth", "checkpoint_best_regular.pth", "last_ema.pth"):
        if (run_dir / n).is_file():
            return run_dir / n
    raise FileNotFoundError(f"no checkpoint in {run_dir} - run `make train` first")


def load_trained(cfg: dict, run_dir: Path, num_classes: int | None = None):
    setup_cache(cfg)
    kwargs = {"num_classes": num_classes} if num_classes else {}
    if cfg["detector"].get("resolution"):
        kwargs["resolution"] = cfg["detector"]["resolution"]
    return _model_class(cfg["detector"]["size"])(pretrain_weights=str(best_checkpoint(run_dir)),
                                                  device="cpu", **kwargs)


def export(cfg: dict, run_dir: Path, out_dir: Path, classes: list[str], log=print) -> Path:
    model = load_trained(cfg, run_dir, len(classes))
    tmp = out_dir / "_export"
    if tmp.exists():
        shutil.rmtree(tmp)
    path = Path(model.export(output_dir=str(tmp), format="onnx",
                             opset_version=cfg["detector"].get("onnx_opset", 17), verbose=False))
    out_dir.mkdir(parents=True, exist_ok=True)
    onnx_path = out_dir / "detector.onnx"
    shutil.move(str(path), onnx_path)
    shutil.rmtree(tmp, ignore_errors=True)
    meta = {"classes": classes, "resolution": int(model.model.resolution), "size": cfg["detector"]["size"],
            "checkpoint": str(best_checkpoint(run_dir)),
            "input": "input [1,3,res,res] RGB, bilinear resize, ImageNet mean/std",
            "outputs": "dets [1,300,4] cxcywh normalized; labels [1,300,C+1] logits (sigmoid, drop last)"}
    (out_dir / "detector.json").write_text(json.dumps(meta, indent=2))
    log(f"[export] {onnx_path} ({onnx_path.stat().st_size / 1e6:.1f} MB), res {meta['resolution']}")
    return onnx_path


def parity(cfg: dict, run_dir: Path, onnx_dir: Path, images: list[Path], log=print) -> dict:
    """Compare PyTorch and ONNX Runtime (CPU) on the same images.

    raw: identical input tensor -> max |diff| of normalized boxes / sigmoid scores
         over the top-k queries (same order).
    e2e: rfdetr.predict() vs. our ONNX pipeline (incl. own preprocessing),
         detections >= score_threshold matched by class + IoU.
    """
    import copy

    import torch

    model = load_trained(cfg, run_dir, len(json.loads((onnx_dir / "detector.json").read_text())["classes"]))
    # separate copy for the raw comparison: model.predict() mutates the live
    # module's state (seen at resolution 640), which would distort the raw diff
    net = copy.deepcopy(model.model.model)
    net.eval()
    onnx = OnnxDetector(onnx_dir, min_score=0.0)
    ncls = len(onnx.classes)
    thr = cfg["detector"]["score_threshold"]
    raw_box, raw_score, e2e_box, e2e_score, unmatched = 0.0, 0.0, 0.0, 0.0, 0
    per_image = []
    for p in images:
        im = Image.open(p)
        x = preprocess(im, onnx.res)
        with torch.no_grad():
            out = net(torch.from_numpy(x))
        pt_boxes = out["pred_boxes"][0].numpy()
        pt_logits = out["pred_logits"][0].numpy()
        ox_boxes, ox_logits = onnx.raw(im)
        # compare the 50 most confident PyTorch queries with their closest ONNX query.
        # Order-independent: RF-DETR selects queries by top-k over encoder proposals,
        # so near-equal proposal scores (e.g. an undertrained model) may permute slots.
        pt_s = sigmoid(pt_logits[:, :ncls])
        ox_s = sigmoid(ox_logits[:, :ncls])
        top = np.argsort(-pt_s.max(1))[:50]
        db = ds = 0.0
        same_slot = 0
        for q in top:
            d = np.abs(ox_boxes - pt_boxes[q]).max(1) + np.abs(ox_s - pt_s[q]).max(1)
            j = int(d.argmin())
            same_slot += int(j == q)
            db = max(db, float(np.abs(ox_boxes[j] - pt_boxes[q]).max()))
            ds = max(ds, float(np.abs(ox_s[j] - pt_s[q]).max()))
        slot_share = same_slot / max(1, len(top))
        raw_box, raw_score = max(raw_box, db), max(raw_score, ds)

        W, H = im.size
        det = model.predict(im.convert("RGB"), threshold=thr)
        pt = [{"cls_id": int(c), "score": float(s),
               "box": [float(b[0]) / W, float(b[1]) / H, float(b[2]) / W, float(b[3]) / H]}
              for b, c, s in zip(det.xyxy, det.class_id, det.confidence)]
        ox = [d for d in postprocess(ox_boxes, ox_logits, ncls, threshold=thr)]
        for a in pt:
            cands = [b for b in ox if b["cls_id"] == a["cls_id"]]
            best = max(cands, key=lambda b: iou(a["box"], b["box"]), default=None)
            if best is None or iou(a["box"], best["box"]) < 0.5:
                unmatched += 1
                continue
            e2e_box = max(e2e_box, float(max(abs(u - v) for u, v in zip(a["box"], best["box"]))))
            e2e_score = max(e2e_score, float(abs(a["score"] - best["score"])))
        per_image.append({"image": p.name, "raw_box": db, "raw_score": ds, "same_slot": slot_share,
                          "n_pt": len(pt), "n_onnx": len(ox)})
    pcfg = cfg["detector"]["parity"]
    res = {"n_images": len(images), "raw_max_box_diff": raw_box, "raw_max_score_diff": raw_score,
           "e2e_max_box_diff": e2e_box, "e2e_max_score_diff": e2e_score, "e2e_unmatched": unmatched,
           "passed": raw_box <= pcfg["max_box_diff"] and raw_score <= pcfg["max_score_diff"] and unmatched == 0,
           "per_image": per_image}
    log(f"[parity] raw box {raw_box:.2e} score {raw_score:.2e} | e2e box {e2e_box:.2e} "
        f"score {e2e_score:.2e} unmatched {unmatched} -> {'OK' if res['passed'] else 'FAIL'}")
    return res
