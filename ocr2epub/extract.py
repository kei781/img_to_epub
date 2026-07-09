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


@dataclass
class Page:
    index: int
    image_path: str | None
    text: str | None


def _render_pdf(pdf_path, workdir, dpi):
    pages = []
    doc = fitz.open(pdf_path)
    try:
        for i in range(len(doc)):
            pg = doc[i]
            txt = pg.get_text("text").strip()
            if len(txt) >= 20:  # 유의미한 텍스트 레이어 존재
                pages.append(Page(i, None, txt))
            else:
                out = os.path.join(workdir, f"p{i:05d}.png")
                pg.get_pixmap(dpi=dpi).save(out)
                pages.append(Page(i, out, None))
    finally:
        doc.close()
    return pages


def _pdf_from_zip(spec, workdir, dpi):
    zpath, inner = spec.split("::", 1)
    tmp = os.path.join(workdir, "_inner.pdf")
    with zipfile.ZipFile(zpath) as z, open(tmp, "wb") as f:
        f.write(z.read(inner))
    return _render_pdf(tmp, workdir, dpi)


def _images_from_zip(zpath, workdir):
    with zipfile.ZipFile(zpath) as z:
        names = [
            n
            for n in z.namelist()
            if os.path.splitext(n)[1].lower() in IMG_EXT and not n.endswith("/")
        ]
        names.sort(key=natural_key)
        pages = []
        for i, n in enumerate(names):
            out = os.path.join(workdir, f"p{i:05d}{os.path.splitext(n)[1].lower()}")
            with open(out, "wb") as f:
                f.write(z.read(n))
            pages.append(Page(i, out, None))
    return pages


def _images_from_rar(rpath, workdir):
    ex = os.path.join(workdir, "rar")
    os.makedirs(ex, exist_ok=True)
    subprocess.run([BZ, "x", "-o:" + ex, "-y", rpath], check=True)
    found = []
    for dp, _, fs in os.walk(ex):
        for f in fs:
            if os.path.splitext(f)[1].lower() in IMG_EXT:
                found.append(os.path.join(dp, f))
    found.sort(key=natural_key)
    return [Page(i, p, None) for i, p in enumerate(found)]


def extract_pages(vol, workdir, dpi=350):
    os.makedirs(workdir, exist_ok=True)
    st = vol.source_type
    if st == "pdf":
        return _render_pdf(vol.source_paths[0], workdir, dpi)
    if st == "pdf-zip":
        return _pdf_from_zip(vol.source_paths[0], workdir, dpi)
    if st == "image-zip":
        return _images_from_zip(vol.source_paths[0], workdir)
    if st == "rar":
        return _images_from_rar(vol.source_paths[0], workdir)
    raise ValueError(f"unknown source_type {st}")
