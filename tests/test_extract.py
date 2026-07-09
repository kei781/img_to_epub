from ocr2epub.extract import natural_key


def test_natural_sort_orders_numbers_correctly():
    names = ["a10.jpg", "a2.jpg", "a1.jpg"]
    assert sorted(names, key=natural_key) == ["a1.jpg", "a2.jpg", "a10.jpg"]
