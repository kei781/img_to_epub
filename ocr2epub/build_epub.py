import os
import html
from ebooklib import epub

PAGES_PER_SECTION = 20


def _section_html(page_paragraphs):
    parts = []
    for paras in page_paragraphs:
        for p in paras:
            parts.append(f"<p>{html.escape(p)}</p>")
    return "<html><body>" + "\n".join(parts) + "</body></html>"


def build_epub(title, page_paragraphs, out_path):
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    book = epub.EpubBook()
    book.set_identifier("ocr-" + title)
    book.set_title(title)
    book.set_language("ko")
    chapters = []
    for start in range(0, len(page_paragraphs), PAGES_PER_SECTION):
        chunk = page_paragraphs[start:start + PAGES_PER_SECTION]
        n = start // PAGES_PER_SECTION + 1
        c = epub.EpubHtml(title=f"{n}", file_name=f"sec{n:03d}.xhtml", lang="ko")
        c.content = _section_html(chunk)
        book.add_item(c)
        chapters.append(c)
    if not chapters:  # 빈 입력 방어
        c = epub.EpubHtml(title="1", file_name="sec001.xhtml", lang="ko")
        c.content = "<html><body><p></p></body></html>"
        book.add_item(c)
        chapters.append(c)
    book.toc = tuple(chapters)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ["nav"] + chapters
    epub.write_epub(out_path, book)
