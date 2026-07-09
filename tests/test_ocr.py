import numpy as np
from PIL import Image
from ocr2epub.ocr import sort_reading_order, _preprocess_image


def test_preprocess_image_upscales_small_and_kills_light(tmp_path):
    # a small grey image with a light-grey "ghost" region and dark "text"
    arr = np.full((50, 40), 200, dtype=np.uint8)  # light background/ghost
    arr[10:20, 5:35] = 30  # dark text stroke
    p = str(tmp_path / "scan.png")
    Image.fromarray(arr, mode="L").save(p)
    out = _preprocess_image(p)
    assert out.dtype == np.uint8 and out.ndim == 3 and out.shape[2] == 3
    assert out.shape[0] == 100 and out.shape[1] == 80  # upscaled 2x (< min_width)
    # light ghost (200 > white=155) pushed to white; dark stroke stays dark
    assert out.max() == 255 and out.min() == 0


def test_reading_order_top_to_bottom():
    # bbox: 4점 [ [x,y], ... ]; y 큰 것이 아래
    results = [
        ([[0, 100], [10, 100], [10, 110], [0, 110]], "second", 0.9),
        ([[0, 0], [10, 0], [10, 10], [0, 10]], "first", 0.9),
    ]
    assert sort_reading_order(results) == ["first", "second"]
