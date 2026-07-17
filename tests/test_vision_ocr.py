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


def test_call_vision_retries_inbody_error_then_succeeds(tmp_path, monkeypatch):
    # Vision intermittently returns a transient in-body error (observed: code 3
    # "Bad image data" on valid pages that succeed on an identical retry). It must
    # be retried within the bounded loop, not raised immediately (which would
    # abort the whole volume for one glitch).
    eng = VisionOcrEngine(str(tmp_path / "c"), _key(tmp_path))
    monkeypatch.setattr("ocr2epub.vision_ocr.time.sleep", lambda s: None)
    seq = [
        _fake_resp({"responses": [{"error": {"code": 3, "message": "Bad image data."}}]}),
        _fake_resp({"responses": [{"fullTextAnnotation": {"text": "복구된본문"}}]}),
    ]

    def fake_urlopen(req, timeout=0):
        return seq.pop(0)

    monkeypatch.setattr("ocr2epub.vision_ocr.urllib.request.urlopen", fake_urlopen)
    assert eng._call_vision(_png(tmp_path), False) == "복구된본문"


def test_call_vision_persistent_inbody_error_raises(tmp_path, monkeypatch):
    # A genuinely bad image keeps erroring; after exhausting attempts it must
    # raise (so run.main counts it FAIL and moves on) and stay uncached. The
    # call-count assertion guards the fix: raise-on-first-error would call once.
    cache = tmp_path / "c"
    eng = VisionOcrEngine(str(cache), _key(tmp_path))
    monkeypatch.setattr("ocr2epub.vision_ocr.time.sleep", lambda s: None)
    calls = []

    def fake_urlopen(req, timeout=0):
        calls.append(1)
        return _fake_resp({"responses": [{"error": {"code": 3, "message": "Bad image data."}}]})

    monkeypatch.setattr("ocr2epub.vision_ocr.urllib.request.urlopen", fake_urlopen)
    page = Page(9, _png(tmp_path), None)
    with pytest.raises(RuntimeError):
        eng.page_text(page, "k9")
    assert len(calls) == 5                     # retried the full bounded loop
    assert list(cache.glob("*.json")) == []    # nothing cached on failure


def test_call_vision_permanent_inbody_error_fails_fast(tmp_path, monkeypatch):
    # A permanent in-body code (e.g. 7 PERMISSION_DENIED) must raise on the first
    # response, not burn the whole backoff loop on every page of a systemic fault.
    eng = VisionOcrEngine(str(tmp_path / "c"), _key(tmp_path))
    monkeypatch.setattr("ocr2epub.vision_ocr.time.sleep", lambda s: None)
    calls = []

    def fake_urlopen(req, timeout=0):
        calls.append(1)
        return _fake_resp({"responses": [{"error": {"code": 7, "message": "denied"}}]})

    monkeypatch.setattr("ocr2epub.vision_ocr.urllib.request.urlopen", fake_urlopen)
    with pytest.raises(RuntimeError):
        eng._call_vision(_png(tmp_path), False)
    assert len(calls) == 1                      # no retry on a permanent code


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


def test_make_engine_vision(tmp_path):
    from ocr2epub.run import make_engine
    (tmp_path / ".vision_key").write_text("K", encoding="utf-8")
    eng = make_engine("vision", str(tmp_path), str(tmp_path / ".vision_key"))
    assert isinstance(eng, VisionOcrEngine)
    assert eng.cache_dir == os.path.join(str(tmp_path), "_vision_cache")


def test_make_engine_unknown_raises(tmp_path):
    from ocr2epub.run import make_engine
    with pytest.raises(ValueError):
        make_engine("bogus", str(tmp_path), "x")


def test_make_engine_vision_missing_key_exits(tmp_path):
    from ocr2epub.run import make_engine
    with pytest.raises(SystemExit):
        make_engine("vision", str(tmp_path), str(tmp_path / ".vision_key"))  # no key file


def test_make_engine_vision_empty_key_exits(tmp_path):
    from ocr2epub.run import make_engine
    (tmp_path / ".vision_key").write_text("   \n", encoding="utf-8")  # whitespace-only
    with pytest.raises(SystemExit):
        make_engine("vision", str(tmp_path), str(tmp_path / ".vision_key"))


def test_fit_payload_passthrough_when_small(tmp_path):
    eng = VisionOcrEngine(str(tmp_path / "c"), _key(tmp_path))
    data = b"x" * 1000
    assert eng._fit_payload(data) is data   # under the cap -> byte-identical, no re-encode


def _noise_png(seed=0, size=400, mode="RGB"):
    import numpy as np
    ch = 3 if mode == "RGB" else 1
    shape = (size, size, ch) if mode == "RGB" else (size, size)
    arr = np.random.RandomState(seed).randint(0, 256, shape, dtype=np.uint8)
    buf = io.BytesIO()
    Image.fromarray(arr, mode).save(buf, "PNG")
    return buf.getvalue()


def test_fit_payload_downscales_oversized_below_cap(tmp_path, monkeypatch):
    eng = VisionOcrEngine(str(tmp_path / "c"), _key(tmp_path))
    monkeypatch.setattr(eng, "_MAX_RAW_BYTES", 3000)   # tiny cap forces a downscale
    big = _noise_png()
    assert len(big) > 3000                              # precondition: over the cap
    out = eng._fit_payload(big)
    assert len(out) <= 3000                             # fits the payload budget
    im = Image.open(io.BytesIO(out)); im.load()         # still a valid, smaller image
    assert im.width < 400 and im.height < 400


def test_fit_payload_downscales_grayscale(tmp_path, monkeypatch):
    # the image-zip/rar path feeds an 'L' array (via _preprocess_image); it must
    # also downscale and stay a valid PNG.
    eng = VisionOcrEngine(str(tmp_path / "c"), _key(tmp_path))
    monkeypatch.setattr(eng, "_MAX_RAW_BYTES", 3000)
    out = eng._fit_payload(_noise_png(mode="L"))
    assert len(out) <= 3000
    Image.open(io.BytesIO(out)).load()


def test_fit_payload_handles_cmyk_input(tmp_path, monkeypatch):
    # a CMYK JPEG (possible in an image-zip) is not PNG-writable; _fit_payload
    # must convert rather than raise "cannot write mode CMYK as PNG".
    import numpy as np
    eng = VisionOcrEngine(str(tmp_path / "c"), _key(tmp_path))
    monkeypatch.setattr(eng, "_MAX_RAW_BYTES", 3000)
    rs = np.random.RandomState(1)
    cmyk = Image.merge("CMYK", [Image.fromarray(rs.randint(0, 256, (400, 400), dtype=np.uint8), "L")
                                for _ in range(4)])
    buf = io.BytesIO(); cmyk.save(buf, "JPEG")
    out = eng._fit_payload(buf.getvalue())
    assert len(out) <= 3000
    Image.open(io.BytesIO(out)).load()


def test_fit_payload_scopes_and_restores_bomb_guard(tmp_path, monkeypatch):
    # opening a >2*MAX_IMAGE_PIXELS image would raise DecompressionBombError;
    # _fit_payload must lift the guard only for its own open and then restore it.
    eng = VisionOcrEngine(str(tmp_path / "c"), _key(tmp_path))
    monkeypatch.setattr(eng, "_MAX_RAW_BYTES", 3000)
    big = _noise_png()                                  # 400x400 = 160000 px
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 100) # 2x guard = 200 px -> would trip
    out = eng._fit_payload(big)                         # no DecompressionBombError
    assert len(out) <= 3000
    assert Image.MAX_IMAGE_PIXELS == 100                # restored, not leaked as None


def test_fit_payload_raises_when_cannot_fit(tmp_path, monkeypatch):
    # an impossibly small cap can't be met even at 1x1; fail loudly instead of
    # returning oversized bytes that would produce an opaque downstream HTTP 400.
    eng = VisionOcrEngine(str(tmp_path / "c"), _key(tmp_path))
    monkeypatch.setattr(eng, "_MAX_RAW_BYTES", 10)
    with pytest.raises(RuntimeError):
        eng._fit_payload(_noise_png())
