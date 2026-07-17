import os
import re
import zipfile
import subprocess
from dataclasses import dataclass

try:
    import pymupdf as fitz  # PyMuPDF (modern import name)
except ImportError:  # pragma: no cover
    import fitz  # PyMuPDF (legacy import name)

BZ = "C:/Program Files/Bandizip/bz.exe"
IMG_EXT = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


def natural_key(name):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", name)]


def _decode_zip_name(info):
    """zipfile decodes non-UTF-8 entry names as cp437; Korean archives are
    usually cp949. Recover the real name (used for sorting + output ext) when
    the UTF-8 general-purpose flag bit is not set."""
    name = info.filename
    if not (info.flag_bits & 0x800):
        try:
            name = name.encode("cp437").decode("cp949")
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass
    return name


def _is_zip_junk(name):
    base = name.rsplit("/", 1)[-1]
    return "__MACOSX" in name.split("/") or base.startswith("._")


@dataclass
class Page:
    index: int
    image_path: str | None
    text: str | None


def _is_real_text(txt):
    """Whether a PDF page's text layer is trustworthy Unicode text (use it as-is)
    or must be rendered and OCR'd instead. Some scanned volumes embed a font with
    a broken CID->Unicode map ("unknown cid font type"), so get_text returns
    hundreds of junk glyph codes (NULs, control chars, random symbols) that pass a
    length check yet are unreadable. Require BOTH enough length AND a high ratio of
    real Hangul/ASCII characters; broken-font garbage scores ~0.3, real prose ~1.0.
    """
    if len(txt) < 20:
        return False
    hangul = sum(1 for c in txt if "가" <= c <= "힣")
    good = hangul + sum(
        1 for c in txt
        if c.isascii() and (c.isalnum() or c.isspace() or c in ".,!?\"'()[]-")
    )
    # Two failure modes must both be caught, since this is a Korean corpus:
    #  - non-ASCII junk (NUL/control/symbols) -> low `good` ratio;
    #  - a broken font that dumps Latin glyphs -> high `good` ratio but no Hangul.
    # A real body page is Korean prose, so require both a clean character mix AND
    # a real Hangul presence. Latin-only pages (broken-font garbage, or the rare
    # genuine English credits page) fall through to render + OCR, which is safe.
    return good / len(txt) >= 0.5 and hangul / len(txt) >= 0.1


def _render_pdf(pdf_path, workdir, dpi, maxpages=None):
    pages = []
    doc = fitz.open(pdf_path)
    pdfium_doc = None  # opened lazily only if a broken-font page needs it
    try:
        n = len(doc)
        if maxpages is not None:
            n = min(n, maxpages)
        for i in range(n):
            pg = doc[i]
            txt = pg.get_text("text").strip()
            if _is_real_text(txt):  # 유의미한(디코딩 가능한) 텍스트 레이어 존재
                pages.append(Page(i, None, txt))
                continue
            out = os.path.join(workdir, f"p{i:05d}.png")
            if len(txt) >= 20:
                # A text layer exists but decodes to garbage: the page uses an
                # embedded font MuPDF can't map ("unknown cid font type"), and
                # MuPDF would ALSO render the wrong glyphs. PDFium maps the
                # Identity-H CIDs straight to the embedded outlines and renders
                # the real page, so OCR sees the actual text.
                if pdfium_doc is None:
                    import pypdfium2 as pdfium
                    pdfium_doc = pdfium.PdfDocument(pdf_path)
                pdfium_doc[i].render(scale=dpi / 72).to_pil().save(out)
            else:
                # No usable text layer at all = a true scan/raster page; MuPDF
                # renders these fine (matches the pilot-validated OCR path).
                pg.get_pixmap(dpi=dpi).save(out)
            pages.append(Page(i, out, None))
    finally:
        doc.close()
        if pdfium_doc is not None:
            pdfium_doc.close()
    return pages


def _pdf_from_zip(spec, workdir, dpi, maxpages=None):
    zpath, inner = spec.split("::", 1)
    tmp = os.path.join(workdir, "_inner.pdf")
    with zipfile.ZipFile(zpath) as z, open(tmp, "wb") as f:
        f.write(z.read(inner))
    return _render_pdf(tmp, workdir, dpi, maxpages)


def _images_from_zip(zpath, workdir, maxpages=None):
    with zipfile.ZipFile(zpath) as z:
        entries = []
        for info in z.infolist():
            if info.is_dir():
                continue
            name = _decode_zip_name(info)
            if _is_zip_junk(name):
                continue
            if os.path.splitext(name)[1].lower() not in IMG_EXT:
                continue
            entries.append((name, info))
        entries.sort(key=lambda e: natural_key(e[0]))
        if maxpages is not None:
            entries = entries[:maxpages]
        pages = []
        for i, (name, info) in enumerate(entries):
            ext = os.path.splitext(name)[1].lower()
            out = os.path.join(workdir, f"p{i:05d}{ext}")
            with open(out, "wb") as f:
                f.write(z.read(info))  # read by ZipInfo so the raw key still matches
            pages.append(Page(i, out, None))
    return pages


def _images_from_rar(rpath, workdir, maxpages=None):
    ex = os.path.join(workdir, "rar")
    os.makedirs(ex, exist_ok=True)
    subprocess.run([BZ, "x", "-o:" + ex, "-y", rpath], check=True)
    found = []
    for dp, _, fs in os.walk(ex):
        for f in fs:
            if os.path.splitext(f)[1].lower() in IMG_EXT and not _is_zip_junk(f):
                found.append(os.path.join(dp, f))
    found.sort(key=natural_key)
    if maxpages is not None:
        found = found[:maxpages]
    return [Page(i, p, None) for i, p in enumerate(found)]


def extract_pages(vol, workdir, dpi=350, maxpages=None):
    os.makedirs(workdir, exist_ok=True)
    st = vol.source_type
    if st == "pdf":
        return _render_pdf(vol.source_paths[0], workdir, dpi, maxpages)
    if st == "pdf-zip":
        return _pdf_from_zip(vol.source_paths[0], workdir, dpi, maxpages)
    if st == "image-zip":
        return _images_from_zip(vol.source_paths[0], workdir, maxpages)
    if st == "rar":
        return _images_from_rar(vol.source_paths[0], workdir, maxpages)
    raise ValueError(f"unknown source_type {st}")
