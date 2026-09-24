import pytest

from docval.config import deep_merge
from docval.detect.onnx_detector import nms_per_class, postprocess
from docval.eval.metrics import average_precision, match, ratio, wilson


def test_match_greedy_by_score():
    gts = [[0, 0, 1, 1], [2, 2, 3, 3]]
    preds = [{"box": [0, 0, 1, 1], "score": 0.9}, {"box": [0, 0, 1, 0.9], "score": 0.8},
             {"box": [5, 5, 6, 6], "score": 0.7}]
    tp, idx = match(gts, preds, 0.5)
    assert tp == [True, False, False] and idx == [0, -1, -1]


def test_average_precision():
    assert average_precision([(0.9, True), (0.8, True)], 2) == pytest.approx(1.0)
    assert average_precision([(0.9, False), (0.8, True)], 1) == pytest.approx(0.5)
    assert average_precision([], 0) is None
    assert average_precision([(0.9, True)], 2) == pytest.approx(51 / 101)


def test_wilson_and_ratio():
    lo, hi = wilson(10, 10)
    assert hi == 1.0 and 0.65 < lo < 0.75  # 10/10 does not prove >= 95 %
    assert ratio(0, 0)["value"] is None


def test_rfdetr_postprocess_drops_background_and_converts_boxes():
    import numpy as np
    dets = np.array([[0.5, 0.5, 0.2, 0.4], [0.1, 0.1, 0.1, 0.1]], np.float32)
    logits = np.array([[5.0, -5.0, 9.0], [-5.0, 0.0, -9.0]], np.float32)  # last = background slot
    out = postprocess(dets, logits, num_classes=2, threshold=0.4)
    assert [(d["cls_id"], round(d["score"], 3)) for d in out] == [(0, 0.993), (1, 0.5)]
    assert out[0]["box"] == pytest.approx([0.4, 0.3, 0.6, 0.7])
    dup = nms_per_class([{"cls_id": 0, "score": 0.9, "box": [0, 0, 1, 1]},
                         {"cls_id": 0, "score": 0.8, "box": [0, 0, 1, 0.95]},
                         {"cls_id": 1, "score": 0.7, "box": [0, 0, 1, 1]}])
    assert len(dup) == 2


def test_config_deep_merge():
    assert deep_merge({"a": {"b": 1, "c": 2}, "d": 1}, {"a": {"c": 3}}) == {"a": {"b": 1, "c": 3}, "d": 1}


def test_json_handles_numpy_scalars():
    import json

    import numpy as np

    from docval.jsonutil import dumps
    d = json.loads(dumps({"a": np.float32(0.5), "b": np.int64(3), "c": np.array([1, 2]), "d": np.bool_(True)}))
    assert d == {"a": 0.5, "b": 3, "c": [1, 2], "d": True}
