"""`make relabel-model`: a template model from the completely labeled tours, for suggestions
in all the others (`make relabel`).

When new classes are added (ta_nummer, ...), only the re-labeled tours have them. Training
the normal detector on all tours would learn their objects as background in the other tours.
The template model is trained on the complete tours only (all their pages, every class), in
folds: fold k is held out of model k. Each page of a template tour is then predicted by the
model that did not see it - so boxes that slipped through there show up as suggestions too.
Pages of other tours get the union of all fold models.

    artifacts/relabel_model/fold<k>/{dataset/, run/, detector.onnx, detector.json}
                           manifest.json   template tours, classes, folds, calibrated thresholds,
                                           recall/precision of the held-out predictions
"""

from __future__ import annotations

import copy
import datetime as dt
import json
import shutil

from ..config import artifacts
from ..data.coverage import complete_exports, labeled_classes, page_exports
from ..detect.onnx_detector import OnnxDetector, iou
from ..jsonutil import dumps

MERGE_IOU = 0.5


def assign_folds(pages, k: int) -> dict[str, int]:
    """{file_name: fold}. Whole groups (page.group, e.g. one shipment) stay together; the
    largest groups go first to the fold with the fewest pages (deterministic)."""
    groups: dict[str, list] = {}
    for p in pages:
        groups.setdefault(p.group or p.file_name, []).append(p)
    size = [0] * k
    out = {}
    for g in sorted(groups, key=lambda g: (-len(groups[g]), g)):
        f = min(range(k), key=lambda i: (size[i], i))
        for p in groups[g]:
            out[p.file_name] = f
        size[f] += len(groups[g])
    return out


def merge_predictions(dets: list[dict]) -> list[dict]:
    """Union of several models: per class, boxes overlapping by IoU >= 0.5 count once
    (highest score)."""
    keep: list[dict] = []
    for d in sorted(dets, key=lambda x: -x["score"]):
        if all(k["cls"] != d["cls"] or iou(k["box"], d["box"]) < MERGE_IOU for k in keep):
            keep.append(d)
    return keep


def reference_exports(cfg, coverage) -> list[str]:
    spec = ((cfg.get("relabel") or {}).get("reference") or {}).get("exports", "auto")
    if spec in (None, "auto"):
        return complete_exports(coverage, cfg["classes"])
    names = [spec] if isinstance(spec, str) else list(spec)
    return [e for e in coverage if e in names or any(e.startswith(n) for n in names)]


def calibrate(pages, preds, classes, iou_thr, beta, fallback) -> tuple[dict, dict]:
    """Per class the threshold with the best F-beta (middle of the plateau) on the held-out
    predictions, and recall/precision there."""
    from .run import CALIB_GRID, pr_at, scored_matches

    b2 = float(beta) ** 2
    thr, quality = {}, {}
    for c in classes:
        n_gt, scored = scored_matches(pages, preds, c, iou_thr)
        scores = []
        for t in CALIB_GRID:
            r = pr_at(scored, n_gt, t)
            if not n_gt or r["precision"] is None:
                continue
            pr, rc = r["precision"], r["recall"]
            scores.append((t, (1 + b2) * pr * rc / (b2 * pr + rc) if rc else 0.0))
        best = max((f for _, f in scores), default=-1.0)
        plateau = [t for t, f in scores if f >= best - 1e-9]
        thr[c] = plateau[len(plateau) // 2] if plateau else fallback
        at = pr_at(scored, n_gt, thr[c])
        quality[c] = {"n_gt": n_gt, "threshold": thr[c], "recall": at["recall"], "precision": at["precision"]}
    return thr, quality


def run_reference_train(cfg, log) -> int:
    from ..data.dataset import load_pages
    from ..data.export_split import write_rfdetr_dataset
    from ..data.split import assign_groups
    from ..detect.train import export, train
    from ..models import setup_cache
    from .run import PagePrep

    setup_cache(cfg)
    rcfg = (cfg.get("relabel") or {}).get("reference") or {}
    coverage = labeled_classes(cfg)
    refs = reference_exports(cfg, coverage)
    if not refs:
        log("FEHLER: keine Tour ist für alle Klassen gelabelt (config `classes`). Eine Tour im Editor "
            "vollständig labeln und speichern, oder relabel.reference.exports angeben.")
        return 2
    classes = [c for c in cfg["classes"] if all(c in coverage[r] for r in refs)]
    k = int(rcfg.get("folds", 2))
    if k < 2:
        log("FEHLER: relabel.reference.folds muss >= 2 sein")
        return 2
    pages, _ = load_pages(cfg)
    exp_of = page_exports(cfg)
    ref_pages = [p for p in pages if exp_of.get(p.file_name) in refs and p.path is not None]
    if len(ref_pages) < 2 * k:
        log(f"FEHLER: nur {len(ref_pages)} Seiten in {refs} - zu wenig für {k} Folds")
        return 2
    assign_groups(ref_pages, cfg["split"])
    fold_of = assign_folds(ref_pages, k)
    base = artifacts(cfg, "relabel_model")
    if base.exists():
        shutil.rmtree(base)
    fcfg = copy.deepcopy(cfg)
    if rcfg.get("epochs"):
        fcfg["detector"]["epochs"] = int(rcfg["epochs"])
    log(f"[relabel-model] Vorlage: {', '.join(refs)} ({len(ref_pages)} Seiten), Klassen {classes}, {k} Folds")
    for f in range(k):
        d = base / f"fold{f}"
        ds = d / "dataset"
        assign = {p.file_name: "valid" if fold_of[p.file_name] == f else "train" for p in ref_pages}
        write_rfdetr_dataset(ref_pages, assign, classes, ds, cfg.get("form_mask"))
        shutil.rmtree(ds / "test")
        shutil.copytree(ds / "valid", ds / "test", symlinks=True)   # rfdetr wants a test split
        log(f"[relabel-model] Fold {f}: {sum(v != f for v in fold_of.values())} Seiten Training, "
            f"{sum(v == f for v in fold_of.values())} zurückgehalten")
        train(fcfg, ds, d / "run", log)
        export(fcfg, d / "run", d, classes, log)
    # held-out predictions -> thresholds and quality
    prep = PagePrep(cfg)
    dets = [OnnxDetector(base / f"fold{f}", min_score=0.01) for f in range(k)]
    preds = {}
    for p in ref_pages:
        _, im = prep(p)
        preds[p.file_name] = dets[fold_of[p.file_name]](im)
    d = cfg["detector"]
    thr, quality = calibrate(ref_pages, preds, classes, d["iou_match"], d.get("calibration_beta", 2),
                             float(d.get("score_threshold_fallback", 0.5)))
    manifest = {"created": dt.datetime.now().isoformat(timespec="seconds"), "exports": refs, "classes": classes,
                "folds": k, "fold_of": fold_of, "thresholds": thr, "quality": quality}
    (base / "manifest.json").write_text(dumps(manifest, indent=1), encoding="utf-8")
    for c, q in quality.items():
        r, pr = q["recall"], q["precision"]
        log(f"[relabel-model] {c:13s} Schwelle {q['threshold']:.2f}  Recall "
            f"{'-' if r is None else f'{r:.2f}'}  Precision {'-' if pr is None else f'{pr:.2f}'}  (n={q['n_gt']}, "
            "auf zurückgehaltenen Seiten)")
    log(f"[relabel-model] -> {base} ; weiter mit `make relabel`")
    return 0


class ReferenceModel:
    """The fold models of the last `make relabel-model`."""

    def __init__(self, cfg):
        base = artifacts(cfg, "relabel_model")
        m = json.loads((base / "manifest.json").read_text(encoding="utf-8"))
        self.exports, self.classes, self.thresholds = m["exports"], m["classes"], m["thresholds"]
        self.fold_of, self.created = m["fold_of"], m["created"]
        self.dets = [OnnxDetector(base / f"fold{f}", min_score=0.01) for f in range(m["folds"])]

    @staticmethod
    def available(cfg) -> bool:
        return artifacts(cfg, "relabel_model", "manifest.json").is_file()

    def __call__(self, file_name: str, im) -> list[dict]:
        f = self.fold_of.get(file_name)
        if f is not None:      # template page: only the model that did not see it
            return self.dets[f](im)
        return merge_predictions([d for det in self.dets for d in det(im)])


def plan_classes(labeled: set[str], is_reference: bool, main_classes: list[str],
                 ref_classes: list[str] | None) -> tuple[list[str], list[str]]:
    """Which model makes the suggestions for which class on a page of one export:
    (classes compared with the main detector, classes compared with the template model).
    Template tours: everything from the template model (held-out fold). Other tours: the
    classes they are labeled for from the main detector, missing ones from the template model."""
    if ref_classes is None:
        return list(main_classes), []
    if is_reference:
        return [], list(ref_classes)
    main = [c for c in main_classes if c in labeled]
    ref = [c for c in ref_classes if c not in main]
    return main, ref
