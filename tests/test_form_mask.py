from PIL import Image, ImageDraw

from docval.zones.form_mask import center_in_any, mask_fields

CFG = {"search_y": [0.6, 1.0], "cell_min_w": 0.18, "cell_max_w": 0.5, "cell_min_h": 0.04,
       "min_cells": 3, "mask_fields": [0, 1], "border_px": 4, "line_min_frac": 0.08, "fill": "white"}


def form_page(shift=0):
    W, H = 620, 877
    im = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(im)
    y1, y2 = 630 + shift, 850 + shift
    xs = [20 + shift, 215 + shift, 410 + shift, 600]
    d.rectangle([xs[0], y1, xs[3], y2], outline="black", width=2)
    for x in xs[1:3]:
        d.line([(x, y1), (x, y2)], fill="black", width=2)
    for k in range(3):  # framed stamp + ink inside every field
        d.rectangle([xs[k] + 15, y1 + 20, xs[k] + 150, y1 + 90], outline=(40, 60, 200), width=3)
        d.line([(xs[k] + 20, y1 + 150), (xs[k] + 160, y1 + 170)], fill=(20, 20, 120), width=3)
    return im, xs


def test_finds_row_and_masks_22_23_with_border():
    for shift in (0, 12):  # scan offset
        im, xs = form_page(shift)
        out, info = mask_fields(im, CFG)
        assert info["found"] and len(info["cells"]) == 3, info["reason"]
        assert info["cells"][0][0] < info["cells"][1][0] < info["cells"][2][0]
        # fields 22/23 blank incl. frame line, field 24 untouched
        assert out.getpixel((xs[0] + 40, 630 + shift + 30)) == (255, 255, 255)
        assert out.getpixel((xs[1], 700 + shift)) == (255, 255, 255)
        assert out.getpixel((xs[2] + 15, 630 + shift + 50)) != (255, 255, 255)
        assert center_in_any([0.1, 0.8, 0.2, 0.85], info["masked"])
        assert not center_in_any([0.75, 0.8, 0.85, 0.85], info["masked"])


def test_no_row_found_leaves_page_unchanged():
    im = Image.new("RGB", (620, 877), "white")
    out, info = mask_fields(im, CFG)
    assert not info["found"] and list(out.getdata()) == list(im.getdata())
