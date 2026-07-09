"""Pilot quality sample: OCR a window of pages from one volume, print the text,
and build a small sample .epub. Warms the real _ocr_cache (same keys as run.py)
so an approved full run reuses these pages.

Usage: python scripts/pilot_sample.py <root> [title-match] [start] [count] [out.epub]
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ocr2epub.discover import discover
from ocr2epub.extract import extract_pages
from ocr2epub.ocr import OcrEngine
from ocr2epub.postprocess import merge_paragraphs
from ocr2epub.build_epub import build_epub

root = sys.argv[1]
match = sys.argv[2] if len(sys.argv) > 2 else "다나카"
start = int(sys.argv[3]) if len(sys.argv) > 3 else 0
count = int(sys.argv[4]) if len(sys.argv) > 4 else 30

active = [v for v in discover(root) if v.skip_reason is None]
exact = [v for v in active if v.title == match]
vols = exact or [v for v in active if match in v.title]
if not vols:
    print("no matching volume for", match)
    sys.exit(1)
v = vols[0]
print(f"PILOT [{v.source_type}] {v.title}")
print(f"paths={v.source_paths}")

work = tempfile.mkdtemp(prefix="pilot_")
pages = extract_pages(v, work, dpi=350, maxpages=start + count)
pages = pages[start:start + count]
print(f"sampling pages {start}..{start + count} -> {len(pages)} pages\n")

engine = OcrEngine(os.path.join(root, "_ocr_cache"))
page_paras = []
for pg in pages:
    key = f"{v.title}|{pg.index}|{v.source_paths}|dpi350"
    text = engine.page_text(pg, key)
    paras = merge_paragraphs(text.split("\n"))
    page_paras.append(paras)
    nchars = sum(len(p) for p in paras)
    print(f"===== page {pg.index}  ({nchars} chars, {len(paras)} paras) =====")
    for p in paras:
        print(p)
    print()

out = sys.argv[5] if len(sys.argv) > 5 else os.path.join(tempfile.gettempdir(), "pilot_sample.epub")
build_epub(v.title + " (샘플)", page_paras, out)
print(f"SAMPLE EPUB: {out}")
