import argparse
import os
import tempfile
import shutil
import traceback

from .discover import discover
from .extract import extract_pages
from .ocr import OcrEngine
from .vision_ocr import VisionOcrEngine
from .postprocess import merge_paragraphs, is_body_text
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
        # low-quality scans (zip/rar) get levels cleanup for EasyOCR; PDF renders
        # are already crisp and are left untouched. Vision reads raw scans cleanly
        # and opts out via PREPROCESS_SCANS. "|pp2" tag keeps the caches distinct.
        pp = vol.source_type in ("image-zip", "rar") and getattr(engine, "PREPROCESS_SCANS", True)
        page_paras = []
        dropped = 0
        for pg in pages:
            key = f"{vol.title}|{pg.index}|{vol.source_paths}|dpi{dpi}" + ("|pp2" if pp else "")
            text = engine.page_text(pg, key, preprocess=pp)
            raw_lines = text.split("\n")
            if is_body_text(raw_lines):
                page_paras.append(merge_paragraphs(raw_lines))
            else:
                dropped += 1  # cover/illustration page -> keep only real body text
        if not page_paras:
            raise RuntimeError(f"no body pages for {vol.title}")
        build_epub(vol.title, page_paras, vol.target_epub)
        print(f"  done: {vol.target_epub} ({len(page_paras)} body pages, {dropped} non-body dropped)")
        return vol.target_epub
    finally:
        shutil.rmtree(work, ignore_errors=True)


def make_engine(name, root, key_path):
    if name == "vision":
        try:
            key = open(key_path, encoding="utf-8-sig").read().strip() if key_path else ""
        except OSError:
            key = ""
        if not key:
            raise SystemExit(
                f"no Vision API key at {key_path!r}. Create {os.path.join(root, '.vision_key')!r}, "
                f"pass --key <file>, or use --engine easyocr."
            )
        return VisionOcrEngine(os.path.join(root, "_vision_cache"), key_path)
    if name == "easyocr":
        return OcrEngine(os.path.join(root, "_ocr_cache"))
    raise ValueError(f"unknown engine: {name}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--only", default=None)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--dpi", type=int, default=350)
    ap.add_argument("--maxpages", type=int, default=None,
                    help="OCR only the first N pages per volume (pilot/sampling)")
    ap.add_argument("--types", default=None,
                    help="comma-separated source_types to include, e.g. 'pdf,pdf-zip'")
    ap.add_argument("--engine", default="vision", choices=["vision", "easyocr"])
    ap.add_argument("--key", default=None,
                    help="Vision API key file (default <root>/.vision_key); "
                         "used only with --engine vision")
    a = ap.parse_args()
    if a.engine == "easyocr" and a.key:
        print("warning: --key is ignored for --engine easyocr")
    vols = [v for v in discover(a.root) if v.skip_reason is None]
    if a.types:
        allowed = {t.strip() for t in a.types.split(",")}
        vols = [v for v in vols if v.source_type in allowed]
    if a.only:
        vols = [v for v in vols if a.only in v.title]
    if a.limit is not None:
        vols = vols[:a.limit]
    print(f"processing {len(vols)} volumes")
    key_path = a.key or os.path.join(a.root, ".vision_key")
    engine = make_engine(a.engine, a.root, key_path)
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
