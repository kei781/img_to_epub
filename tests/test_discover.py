import os
import zipfile
from ocr2epub.discover import discover


def _touch(p):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "wb") as f:
        f.write(b"x")


def test_skips_folder_where_epub_exists(tmp_path):
    root = str(tmp_path)
    _touch(os.path.join(root, "A", "book 1.pdf"))
    _touch(os.path.join(root, "A", "book 1.epub"))
    vols = [v for v in discover(root) if v.skip_reason is None]
    titles = [v.title for v in vols]
    assert "book 1" not in titles


def test_pdf_zip_duplicate_of_standalone_is_skipped(tmp_path):
    root = str(tmp_path)
    _touch(os.path.join(root, "B", "vol01.pdf"))
    zp = os.path.join(root, "B", "bundle.zip")
    os.makedirs(os.path.dirname(zp), exist_ok=True)
    with zipfile.ZipFile(zp, "w") as z:
        z.writestr("vol01.pdf", b"x")
    active = [v for v in discover(root) if v.skip_reason is None]
    # zip 은 중복이므로 스킵, 낱개 pdf 만 남음
    assert any(v.title == "vol01" and v.source_type == "pdf" for v in active)
    assert not any(v.source_type == "pdf-zip" for v in active)


def test_image_zip_is_one_volume(tmp_path):
    root = str(tmp_path)
    zp = os.path.join(root, "C", "vol 3.zip")
    os.makedirs(os.path.dirname(zp), exist_ok=True)
    with zipfile.ZipFile(zp, "w") as z:
        z.writestr("a0001.jpg", b"x")
        z.writestr("a0002.jpg", b"x")
    active = [v for v in discover(root) if v.skip_reason is None]
    assert any(v.title == "vol 3" and v.source_type == "image-zip" for v in active)


def test_txt_only_folder_yields_nothing(tmp_path):
    root = str(tmp_path)
    _touch(os.path.join(root, "기타", "novel.txt"))
    active = [v for v in discover(root) if v.skip_reason is None]
    assert active == []
