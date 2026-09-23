import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

CATEGORIES = [
    {"id": 1, "name": "unterschrift"},
    {"id": 2, "name": "stempel"},
    {"id": 3, "name": "tour_nummer"},
    {"id": 4, "name": "cmr_count"},
]


@pytest.fixture
def tiny_coco(tmp_path):
    """Small synthetic COCO dataset with deliberate defects."""
    from PIL import Image

    img_dir = tmp_path / "images"
    img_dir.mkdir()
    names = [
        "CMR_4711_p1_jpg.rf.0123456789abcdef0123456789abcdef.jpg",
        "CMR_4711_p2_jpg.rf.fedcba9876543210fedcba9876543210.jpg",
        "lieferschein_0815-1.jpg",
        "loading_list_77.jpg",
        "scan_20240501_123456.jpg",  # no doc type hint
    ]
    images = []
    for i, fn in enumerate(names, start=1):
        Image.new("RGB", (100, 200), (255, 255, 255)).save(img_dir / fn)
        images.append({"id": i, "file_name": fn, "width": 100, "height": 200})
    images.append({"id": 6, "file_name": "missing.jpg", "width": 100, "height": 200})
    images.append({"id": 6, "file_name": "dup_id.jpg", "width": 100, "height": 200})
    anns = [
        {"id": 1, "image_id": 1, "category_id": 1, "bbox": [10, 150, 30, 20]},
        {"id": 2, "image_id": 1, "category_id": 3, "bbox": [60, 10, 30, 10],
         "attributes": {"text": "1234567"}},
        {"id": 3, "image_id": 2, "category_id": 2, "bbox": [90, 190, 20, 20]},   # out of image
        {"id": 4, "image_id": 3, "category_id": 1, "bbox": [10, 10, 0, 5]},     # zero area
        {"id": 5, "image_id": 3, "category_id": 9, "bbox": [10, 10, 5, 5]},     # unknown cat
        {"id": 5, "image_id": 4, "category_id": 3, "bbox": [5, 5, 20, 10]},     # dup ann id
        {"id": 7, "image_id": 4, "category_id": 4, "bbox": [70, 5, 20, 10]},
    ]
    coco = {"images": images, "annotations": anns, "categories": CATEGORIES}
    path = tmp_path / "coco.json"
    path.write_text(json.dumps(coco))
    return path, img_dir
