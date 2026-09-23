"""Optional whole-page doc type classifier (timm, Apache-2.0), exported to ONNX.

Training uses PyTorch; evaluation uses the ONNX model (same as the browser).
"""

from __future__ import annotations

import json
import random
import time
from pathlib import Path

import numpy as np
from PIL import Image

from ..zones.synthetic import to_rgb

MEAN = (0.485, 0.456, 0.406)
STD = (0.229, 0.224, 0.225)


def preprocess(im: Image.Image, size: int) -> np.ndarray:
    """Grayscale-ish page -> letterboxed square, CHW float32 (ImageNet norm)."""
    im = to_rgb(im)
    w, h = im.size
    s = size / max(w, h)
    r = im.resize((max(1, round(w * s)), max(1, round(h * s))), Image.BILINEAR)
    canvas = Image.new("RGB", (size, size), (255, 255, 255))
    canvas.paste(r, ((size - r.width) // 2, (size - r.height) // 2))
    a = np.asarray(canvas, dtype=np.float32) / 255.0
    a = (a - np.array(MEAN, dtype=np.float32)) / np.array(STD, dtype=np.float32)
    return a.transpose(2, 0, 1)


def train(pages_train, pages_valid, classes: list[str], cfg: dict, out_dir: Path,
          pretrained: bool = True, log=print) -> dict:
    import timm
    import torch

    torch.manual_seed(cfg.get("seed", 42))
    random.seed(cfg.get("seed", 42))
    size = cfg["img_size"]
    idx = {c: i for i, c in enumerate(classes)}
    model = timm.create_model(cfg["model"], pretrained=pretrained, num_classes=len(classes))
    opt = torch.optim.AdamW(model.parameters(), lr=cfg["lr"])
    loss_fn = torch.nn.CrossEntropyLoss()

    def load(pages, augment):
        xs, ys = [], []
        for p in pages:
            if p.doc_type not in idx or p.path is None:
                continue
            im = Image.open(p.path)
            if augment:
                im = to_rgb(im).rotate(random.uniform(-2, 2), fillcolor=(255, 255, 255))
            xs.append(preprocess(im, size))
            ys.append(idx[p.doc_type])
        return xs, ys

    xv, yv = load(pages_valid, False)
    best, best_state, history = -1.0, None, []
    t0 = time.time()
    for epoch in range(cfg["epochs"]):
        model.train()
        xt, yt = load(pages_train, True)
        order = list(range(len(xt)))
        random.shuffle(order)
        total = 0.0
        for i in range(0, len(order), cfg["batch_size"]):
            b = order[i:i + cfg["batch_size"]]
            x = torch.from_numpy(np.stack([xt[j] for j in b]))
            y = torch.tensor([yt[j] for j in b])
            opt.zero_grad()
            loss = loss_fn(model(x), y)
            loss.backward()
            opt.step()
            total += float(loss.detach()) * len(b)
        acc = None
        if xv:
            model.eval()
            with torch.no_grad():
                pred = model(torch.from_numpy(np.stack(xv))).argmax(1).tolist()
            acc = sum(int(p == y) for p, y in zip(pred, yv)) / len(yv)
        history.append({"epoch": epoch + 1, "loss": total / max(1, len(xt)), "valid_acc": acc})
        log(f"[doctype] epoch {epoch + 1}: loss {history[-1]['loss']:.4f} valid_acc {acc}")
        score = acc if acc is not None else -history[-1]["loss"]
        if score >= best:
            best = score
            best_state = {k: v.clone() for k, v in model.state_dict().items()}
    if best_state is not None:
        model.load_state_dict(best_state)
    model.eval()
    out_dir.mkdir(parents=True, exist_ok=True)
    onnx_path = out_dir / "doctype.onnx"
    torch.onnx.export(model, torch.zeros(1, 3, size, size), str(onnx_path),
                      input_names=["input"], output_names=["logits"],
                      dynamic_axes={"input": {0: "batch"}, "logits": {0: "batch"}},
                      opset_version=17, dynamo=False)
    meta = {"classes": classes, "img_size": size, "model": cfg["model"],
            "history": history, "train_seconds": round(time.time() - t0, 1)}
    (out_dir / "doctype.json").write_text(json.dumps(meta, indent=2))
    with open(out_dir / "doctype_train_log.csv", "w", encoding="utf-8") as f:
        f.write("epoch,loss,valid_acc\n")
        for h in history:
            f.write(f"{h['epoch']},{h['loss']:.6f},{'' if h['valid_acc'] is None else h['valid_acc']}\n")
    return meta


class OnnxDocTypeClassifier:
    def __init__(self, model_dir: Path):
        import onnxruntime as ort

        meta = json.loads((model_dir / "doctype.json").read_text())
        self.classes = meta["classes"]
        self.size = meta["img_size"]
        self.sess = ort.InferenceSession(str(model_dir / "doctype.onnx"), providers=["CPUExecutionProvider"])

    def predict(self, im: Image.Image) -> tuple[str, float, dict]:
        x = preprocess(im, self.size)[None]
        logits = self.sess.run(None, {"input": x})[0][0]
        e = np.exp(logits - logits.max())
        p = e / e.sum()
        k = int(p.argmax())
        return self.classes[k], float(p[k]), {c: float(v) for c, v in zip(self.classes, p)}
