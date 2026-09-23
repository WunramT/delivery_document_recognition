from docval.data.coco import normalize_xywh, validate_coco, xywh_to_xyxy, box_center, load_coco


def test_validation_finds_all_defects(tiny_coco):
    path, img_dir = tiny_coco
    data = load_coco(path)
    counts = validate_coco(data, img_dir, expected_classes=["unterschrift", "stempel"]).count_by_kind()
    assert counts["bbox_out_of_image"] == 1
    assert counts["zero_area_bbox"] == 1
    assert counts["unknown_category"] == 1
    assert counts["duplicate_annotation_id"] == 1
    assert counts["duplicate_image_id"] == 1
    assert counts["missing_image_file"] == 2
    assert "expected_class_missing" not in counts


def test_validation_does_not_modify_input(tiny_coco):
    import copy
    path, img_dir = tiny_coco
    data = load_coco(path)
    before = copy.deepcopy(data)
    validate_coco(data, img_dir)
    assert data == before


def test_box_helpers():
    assert xywh_to_xyxy([10, 20, 30, 40]) == [10, 20, 40, 60]
    assert normalize_xywh([10, 20, 30, 40], 100, 200) == [0.1, 0.1, 0.4, 0.3]
    assert box_center([0.0, 0.0, 0.5, 1.0]) == [0.25, 0.5]
