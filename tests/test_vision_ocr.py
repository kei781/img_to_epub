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


import io
import os
import json
import urllib.error

import pytest
from PIL import Image

from ocr2epub.vision_ocr import VisionOcrEngine
from ocr2epub.extract import Page


class _CtxBytes(io.BytesIO):
    """A BytesIO that also works as the context manager urlopen returns."""
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False


def _fake_resp(obj):
    return _CtxBytes(json.dumps(obj).encode("utf-8"))


def _key(tmp_path):
    kp = tmp_path / ".vision_key"
    kp.write_text("FAKEKEY", encoding="utf-8")
    return str(kp)


def _png(tmp_path, name="p.png"):
    p = tmp_path / name
    Image.new("RGB", (8, 8), "white").save(str(p))
    return str(p)


def test_passthrough_text_layer_makes_no_call(tmp_path):
    eng = VisionOcrEngine(str(tmp_path / "c"), _key(tmp_path))
    page = Page(0, None, "이미 텍스트")
    # page.text is set -> returns verbatim, never touches the network
    assert eng.page_text(page, "k0") == "이미 텍스트"


def test_calls_vision_then_caches_and_normalizes(tmp_path, monkeypatch):
    eng = VisionOcrEngine(str(tmp_path / "c"), _key(tmp_path))
    calls = []
    monkeypatch.setattr(
        eng, "_call_vision",
        lambda path, pp: (calls.append(path), "포이보스∙∙∙∙∙∙")[1],
    )
    page = Page(1, _png(tmp_path), None)
    assert eng.page_text(page, "k1") == "포이보스……"   # normalized on return
    assert eng.page_text(page, "k1") == "포이보스……"   # 2nd read hits cache
    assert len(calls) == 1                              # no 2nd API call


def test_call_vision_retries_transient_then_succeeds(tmp_path, monkeypatch):
    eng = VisionOcrEngine(str(tmp_path / "c"), _key(tmp_path))
    monkeypatch.setattr("ocr2epub.vision_ocr.time.sleep", lambda s: None)
    seq = [
        urllib.error.HTTPError("u", 503, "busy", {}, None),
        _fake_resp({"responses": [{"fullTextAnnotation": {"text": "OK본문"}}]}),
    ]

    def fake_urlopen(req, timeout=0):
        item = seq.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr("ocr2epub.vision_ocr.urllib.request.urlopen", fake_urlopen)
    assert eng._call_vision(_png(tmp_path), False) == "OK본문"


def test_call_vision_blank_page_returns_empty(tmp_path, monkeypatch):
    eng = VisionOcrEngine(str(tmp_path / "c"), _key(tmp_path))

    def fake_urlopen(req, timeout=0):
        return _fake_resp({"responses": [{}]})   # no fullTextAnnotation

    monkeypatch.setattr("ocr2epub.vision_ocr.urllib.request.urlopen", fake_urlopen)
    assert eng._call_vision(_png(tmp_path), False) == ""


def test_hard_error_raises_and_is_not_cached(tmp_path, monkeypatch):
    cache = tmp_path / "c"
    eng = VisionOcrEngine(str(cache), _key(tmp_path))

    def fake_urlopen(req, timeout=0):
        raise urllib.error.HTTPError("u", 403, "forbidden", {}, io.BytesIO(b"nope"))

    monkeypatch.setattr("ocr2epub.vision_ocr.urllib.request.urlopen", fake_urlopen)
    page = Page(2, _png(tmp_path), None)
    with pytest.raises(RuntimeError):
        eng.page_text(page, "k2")
    assert list(cache.glob("*.json")) == []   # nothing cached on failure
