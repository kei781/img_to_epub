import os
import zipfile
from ocr2epub.extract import natural_key, _images_from_zip, _is_real_text


def test_is_real_text_accepts_korean_prose():
    assert _is_real_text("그날 아침, 벨은 던전으로 향했다. 릴리가 뒤를 따랐다.")


def test_is_real_text_accepts_english_prose():
    assert _is_real_text("It was a bright cold day in April, and the clocks were.")


def test_is_real_text_rejects_short_text():
    # too little to trust as a real text layer -> should render + OCR
    assert not _is_real_text("Lv.3")


def test_is_real_text_rejects_broken_cid_font_garbage():
    # a page whose embedded font has no CID->Unicode map: get_text returns
    # hundreds of junk glyph codes that pass a length check but are unreadable.
    garbage = "\x00\x0f\x00\x04\n\x00\xe2\x00a\x00\xd3\x00$\x00\x04\n\x00\xd4\x00\x04" * 8
    assert len(garbage) >= 20
    assert not _is_real_text(garbage)


def test_natural_sort_orders_numbers_correctly():
    names = ["a10.jpg", "a2.jpg", "a1.jpg"]
    assert sorted(names, key=natural_key) == ["a1.jpg", "a2.jpg", "a10.jpg"]


def test_image_zip_skips_macosx_junk_and_orders_naturally(tmp_path):
    zp = str(tmp_path / "vol.zip")
    with zipfile.ZipFile(zp, "w") as z:
        # deliberately out of order + a mac AppleDouble sidecar that must be dropped
        z.writestr("p10.jpg", b"a")
        z.writestr("p2.jpg", b"b")
        z.writestr("__MACOSX/._p2.jpg", b"junk")
        z.writestr("p1.jpg", b"c")

    class V:
        source_type = "image-zip"
    work = str(tmp_path / "work")
    os.makedirs(work, exist_ok=True)
    pages = _images_from_zip(zp, work)
    # 3 real images, sidecar excluded, natural order 1,2,10
    assert len(pages) == 3
    contents = [open(p.image_path, "rb").read() for p in pages]
    assert contents == [b"c", b"b", b"a"]
