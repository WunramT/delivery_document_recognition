from docval.eval.label_review import classify_page

THR = {"cmr_count": 0.4, "stempel": 0.4, "unterschrift": 0.4}


def cats(findings):
    return sorted((f["cls"], f["category"]) for f in findings)


def test_matching_box_gives_no_finding():
    g = {"cmr_count": [[0.30, 0.60, 0.40, 0.63]]}
    p = [{"cls": "cmr_count", "box": [0.30, 0.60, 0.40, 0.63], "score": 0.9}]
    assert classify_page(g, p, THR, 0.5) == []


def test_box_drawn_differently_is_one_finding_not_fn_plus_fp():
    # GT only around "3/9", model around "CMR 3/9": overlap, IoU < 0.5
    g = {"cmr_count": [[0.36, 0.60, 0.40, 0.63]]}
    p = [{"cls": "cmr_count", "box": [0.30, 0.60, 0.40, 0.63], "score": 0.8}]
    f = classify_page(g, p, THR, 0.5)
    assert cats(f) == [("cmr_count", "abweichende_box")]
    assert 0.3 < f[0]["iou"] < 0.5


def test_confident_prediction_without_gt_is_missing_label():
    p = [{"cls": "stempel", "box": [0.7, 0.8, 0.9, 0.9], "score": 0.95},
         {"cls": "stempel", "box": [0.1, 0.1, 0.2, 0.2], "score": 0.2}]   # below threshold -> ignored
    assert cats(classify_page({"stempel": []}, p, THR, 0.5)) == [("stempel", "label_fehlt")]


def test_other_class_and_not_found_and_duplicate():
    g = {"unterschrift": [[0.7, 0.8, 0.9, 0.9]],
         "stempel": [[0.1, 0.8, 0.3, 0.9], [0.1, 0.8, 0.3, 0.905]]}      # stamp labeled twice
    p = [{"cls": "stempel", "box": [0.7, 0.8, 0.9, 0.9], "score": 0.7},   # on the signature
         {"cls": "stempel", "box": [0.1, 0.8, 0.3, 0.9], "score": 0.9}]
    f = classify_page(g, p, THR, 0.5)
    assert cats(f) == [("stempel", "andere_klasse"), ("stempel", "doppeltes_label"),
                       ("unterschrift", "nicht_erkannt")]
    assert next(x for x in f if x["category"] == "andere_klasse")["gt_cls"] == "unterschrift"
