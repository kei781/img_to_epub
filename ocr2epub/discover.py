import os
import zipfile
from dataclasses import dataclass

IMG_EXT = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
IGNORE_DIRS = {"_epub_output", "_ocr_cache", "docs", ".venv", ".git", "ocr2epub"}


@dataclass
class Volume:
    title: str
    source_paths: list
    source_type: str
    target_epub: str
    skip_reason: str | None = None


def _target(root, folder_rel, title):
    return os.path.join(root, "_epub_output", folder_rel, title + ".epub")


def existing_epub_titles(root):
    out = set()
    for dirpath, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
        for f in files:
            if f.lower().endswith(".epub"):
                out.add((os.path.relpath(dirpath, root), os.path.splitext(f)[0]))
    return out


def _zip_kind(path):
    try:
        with zipfile.ZipFile(path) as z:
            names = [n for n in z.namelist() if not n.endswith("/")]
    except Exception:
        return None, []
    pdfs = [n for n in names if n.lower().endswith(".pdf")]
    imgs = [n for n in names if os.path.splitext(n)[1].lower() in IMG_EXT]
    if pdfs:
        return "pdf-zip", pdfs
    if imgs:
        return "image-zip", imgs
    return None, []


def discover(root):
    existing = existing_epub_titles(root)
    vols = []
    for dirpath, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
        rel = os.path.relpath(dirpath, root)
        standalone_pdf_titles = {
            os.path.splitext(f)[0] for f in files if f.lower().endswith(".pdf")
        }
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            full = os.path.join(dirpath, f)
            if ext == ".pdf":
                title = os.path.splitext(f)[0]
                skip = "epub-exists" if (rel, title) in existing else None
                vols.append(Volume(title, [full], "pdf", _target(root, rel, title), skip))
            elif ext == ".zip":
                kind, inner = _zip_kind(full)
                if kind == "image-zip":
                    title = os.path.splitext(f)[0]
                    skip = "epub-exists" if (rel, title) in existing else None
                    vols.append(
                        Volume(title, [full], "image-zip", _target(root, rel, title), skip)
                    )
                elif kind == "pdf-zip":
                    for pdfname in inner:
                        title = os.path.splitext(os.path.basename(pdfname))[0]
                        skip = None
                        if title in standalone_pdf_titles:
                            skip = "dup-of-standalone-pdf"
                        elif (rel, title) in existing:
                            skip = "epub-exists"
                        vols.append(
                            Volume(
                                title,
                                [full + "::" + pdfname],
                                "pdf-zip",
                                _target(root, rel, title),
                                skip,
                            )
                        )
            elif ext == ".rar":
                title = os.path.splitext(f)[0]
                skip = "epub-exists" if (rel, title) in existing else None
                vols.append(Volume(title, [full], "rar", _target(root, rel, title), skip))
    return vols
