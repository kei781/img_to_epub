from ocr2epub.vision_ocr import normalize_vision_text


def test_collapses_middle_dot_run():
    # U+2219 bullet-operator run (Vision renders "……" this way)
    assert normalize_vision_text("포이보스∙∙∙∙∙∙끝") == "포이보스……끝"


def test_collapses_katakana_middle_dot_run():
    assert normalize_vision_text("Lv.3・・・・・・제2급") == "Lv.3……제2급"


def test_collapses_ascii_dot_run():
    assert normalize_vision_text("말했다... 그리고") == "말했다…… 그리고"


def test_collapses_repeated_ellipsis_char():
    assert normalize_vision_text("도와준…………건가") == "도와준……건가"


def test_keeps_single_interpunct():
    # a lone middle dot (e.g. in a title) must survive
    assert normalize_vision_text("1·2권") == "1·2권"


def test_keeps_single_period():
    assert normalize_vision_text("Lv.2가 되었다.") == "Lv.2가 되었다."


def test_drops_standalone_quote_digit_lines():
    assert normalize_vision_text("첫줄\n66\n99\n둘째줄") == "첫줄\n둘째줄"


def test_keeps_66_inside_text():
    assert normalize_vision_text("66권을 읽었다") == "66권을 읽었다"
