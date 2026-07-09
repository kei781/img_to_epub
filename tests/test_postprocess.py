from ocr2epub.postprocess import merge_paragraphs, strip_furniture, is_body_text


def test_strip_page_numbers():
    assert strip_furniture(["12", "본문입니다."]) == ["본문입니다."]


def test_merge_wrapped_lines_into_paragraph():
    lines = ["그는 천천히 걸어가며", "생각에 잠겼다.", "", "다음 날이 밝았다."]
    out = merge_paragraphs(lines)
    assert out == ["그는 천천히 걸어가며 생각에 잠겼다.", "다음 날이 밝았다."]


def test_is_body_text_keeps_prose_pages():
    body = [
        "아키히토가 노려보자 돌변하여 주먹을 불끈 쥐고 역설해",
        "왔다. 내가 내기거리 오락거리냐 놀구들 있네",
        "그니까 노트 복사한 거 주잖아 고맙지",
        "다소 죄책감이 있었던지 토모카는 마지막에 미소를 띠었다",
    ]
    assert is_body_text(body) is True


def test_is_body_text_drops_illustration_scatter():
    # scattered short tokens like an illustration/cover page OCR result
    illust = ["근", "젠쟁", "@이다! 닭", "#", "하7도", "소고기", "노래방에도", "못 갖네."]
    assert is_body_text(illust) is False
    # pure symbol garbage (no Hangul) also dropped
    assert is_body_text(["'", "'", "` '", "'"]) is False
