from ocr2epub.ocr import sort_reading_order


def test_reading_order_top_to_bottom():
    # bbox: 4점 [ [x,y], ... ]; y 큰 것이 아래
    results = [
        ([[0, 100], [10, 100], [10, 110], [0, 110]], "second", 0.9),
        ([[0, 0], [10, 0], [10, 10], [0, 10]], "first", 0.9),
    ]
    assert sort_reading_order(results) == ["first", "second"]
