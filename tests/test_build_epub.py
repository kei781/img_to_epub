import os
from ebooklib import epub
from ocr2epub.build_epub import build_epub


def test_build_epub_creates_readable_file(tmp_path):
    out = str(tmp_path / "out" / "책.epub")
    build_epub("테스트책", [["첫 문단.", "둘째 문단."], ["셋째 문단."]], out)
    assert os.path.exists(out)
    book = epub.read_epub(out)
    assert book.get_metadata("DC", "title")[0][0] == "테스트책"
    docs = [i for i in book.get_items() if i.get_type() == 9]  # DOCUMENT
    assert len(docs) >= 1
    body = b"".join(d.get_content() for d in docs).decode("utf-8")
    assert "첫 문단." in body and "셋째 문단." in body
