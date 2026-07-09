import os
import zipfile
from ocr2epub.extract import natural_key, _images_from_zip


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
