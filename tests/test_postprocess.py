from ocr2epub.postprocess import merge_paragraphs, strip_furniture


def test_strip_page_numbers():
    assert strip_furniture(["12", "본문입니다."]) == ["본문입니다."]


def test_merge_wrapped_lines_into_paragraph():
    lines = ["그는 천천히 걸어가며", "생각에 잠겼다.", "", "다음 날이 밝았다."]
    out = merge_paragraphs(lines)
    assert out == ["그는 천천히 걸어가며 생각에 잠겼다.", "다음 날이 밝았다."]
