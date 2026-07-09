import argparse
import os
import tempfile
import shutil
import traceback

from .discover import discover
from .extract import extract_pages
from .ocr import OcrEngine
from .postprocess import merge_paragraphs
from .build_epub import build_epub


def process_volume(vol, engine, root, dpi=350, maxpages=None):
    if os.path.exists(vol.target_epub):
        print(f"  skip (exists): {vol.title}")
        return vol.target_epub
    work = tempfile.mkdtemp(prefix="o2e_")
    try:
        pages = extract_pages(vol, work, dpi=dpi, maxpages=maxpages)
        if not pages:
            # 0 pages -> do NOT write a placeholder epub (it would be treated as
            # done forever). Raise so main() counts it FAIL and it is retried.
            raise RuntimeError(f"no pages extracted for {vol.title}")
        page_paras = []
        for pg in pages:
            key = f"{vol.title}|{pg.index}|{vol.source_paths}|dpi{dpi}"
            text = engine.page_text(pg, key)
            page_paras.append(merge_paragraphs(text.split("\n")))
        build_epub(vol.title, page_paras, vol.target_epub)
        print(f"  done: {vol.target_epub} ({len(pages)} pages)")
        return vol.target_epub
    finally:
        shutil.rmtree(work, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--only", default=None)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--dpi", type=int, default=350)
    ap.add_argument("--maxpages", type=int, default=None,
                    help="OCR only the first N pages per volume (pilot/sampling)")
    a = ap.parse_args()
    vols = [v for v in discover(a.root) if v.skip_reason is None]
    if a.only:
        vols = [v for v in vols if a.only in v.title]
    if a.limit is not None:
        vols = vols[:a.limit]
    print(f"processing {len(vols)} volumes")
    engine = OcrEngine(os.path.join(a.root, "_ocr_cache"))
    ok = fail = 0
    for v in vols:
        print(f"[{v.source_type}] {v.title}")
        try:
            process_volume(v, engine, a.root, dpi=a.dpi, maxpages=a.maxpages)
            ok += 1
        except Exception:
            fail += 1
            traceback.print_exc()
    print(f"OK={ok} FAIL={fail}")


if __name__ == "__main__":
    main()
