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


def test_propose_replaces_rough_box_adds_missing_drops_duplicate():
    from docval.eval.relabel import propose

    g = {"cmr_count": [[0.36, 0.60, 0.40, 0.63]],                       # rough label
         "stempel": [[0.1, 0.8, 0.3, 0.9], [0.1, 0.8, 0.3, 0.905]],        # labeled twice
         "unterschrift": [[0.7, 0.8, 0.9, 0.9]]}
    p = [{"cls": "cmr_count", "box": [0.30, 0.60, 0.40, 0.63], "score": 0.8},
         {"cls": "stempel", "box": [0.1, 0.8, 0.3, 0.9], "score": 0.9},
         {"cls": "stempel", "box": [0.5, 0.1, 0.6, 0.2], "score": 0.85},      # label missing
         {"cls": "stempel", "box": [0.7, 0.8, 0.9, 0.9], "score": 0.7}]       # on the signature
    boxes, changes = propose(g, p, THR, 0.5, {})
    assert sorted(c["action"] for c in changes) == ["entfernt_doppelt", "ersetzt", "hinzugefügt"]
    by = {}
    for b in boxes:
        by.setdefault(b["cls"], []).append(b["box"])
    assert by["cmr_count"] == [[0.30, 0.60, 0.40, 0.63]]
    assert sorted(by["stempel"]) == [[0.1, 0.8, 0.3, 0.9], [0.5, 0.1, 0.6, 0.2]]
    assert by["unterschrift"] == [[0.7, 0.8, 0.9, 0.9]]
    # conservative: keep every label, only add
    _, ch = propose(g, p, THR, 0.5, {"different_box": "gt", "drop_duplicates": False})
    assert [c["action"] for c in ch] == ["hinzugefügt"]
