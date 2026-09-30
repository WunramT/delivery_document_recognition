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


def test_editor_data_keeps_ids_other_categories_and_csv_mapping(tmp_path):
    from docval.eval.label_editor import editor_data, write_editor

    coco = {"info": {"x": 1},
            "images": [{"id": 7, "file_name": "images/a_png.rf.0123456789abcdef0123.png", "width": 100, "height": 50}],
            "categories": [{"id": 0, "name": "documents"}, {"id": 1, "name": "stempel"}],
            "annotations": [{"id": 1, "image_id": 7, "category_id": 1, "bbox": [10, 5, 20, 10],
                             "attributes": {"quelle": "modell", "score": 0.8}},
                            {"id": 2, "image_id": 7, "category_id": 0, "bbox": [0, 0, 1, 1]}]}
    csv = tmp_path / "page_types.csv"
    csv.write_text("file_name;doc_type;source_pdf\na.png;cmr;x.pdf\n", encoding="utf-8")
    d = editor_data("425_21.09.2026", coco, "_annotations.coco.json", {7: {"doc_type": "cmr"}},
                    ["stempel"], ["cmr"], csv)
    p = d["pages"][0]
    assert p["id"] == 7 and p["csv_key"] == "a.png" and p["doc_type"] == "cmr"
    assert p["boxes"] == [{"cls": "stempel", "x1": 10, "y1": 5, "x2": 30, "y2": 15, "source": "modell", "score": 0.8}]
    assert [a["id"] for a in d["other_annotations"]] == [2]       # unknown category kept untouched
    assert d["csv"]["delimiter"] == ";" and d["csv"]["columns"] == ["file_name", "doc_type", "source_pdf"]
    html = write_editor(tmp_path, d).read_text(encoding="utf-8")
    assert "__DATA__" not in html and '"export": "425_21.09.2026"' in html


def test_label_compare_pairs_added_removed_and_tighter_boxes():
    from docval.eval.label_compare import class_stats, pair

    old = [["cmr_count", 100, 100, 200, 120], ["stempel", 10, 10, 50, 50]]
    new = [["cmr_count", 130, 102, 180, 118], ["unterschrift", 300, 300, 400, 340]]
    prs, removed, added = pair(old, new)
    assert [p[0][0] for p in prs] == ["cmr_count"] and prs[0][2] < 0.9
    assert removed == [old[1]] and added == [new[1]]
    st = class_stats([{"w": 1000, "h": 1000, "old": old, "new": new, "pairs": prs,
                       "removed": removed, "added": added}], ["cmr_count", "stempel", "unterschrift"])
    assert st["cmr_count"]["adjusted"] == 1 and st["cmr_count"]["area_ratio"] < 0.5
    assert st["stempel"]["removed"] == 1 and st["unterschrift"]["added"] == 1
