import os
import zipfile
from collections import defaultdict
from dataclasses import dataclass

IMG_EXT = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
IGNORE_DIRS = {"_epub_output", "_ocr_cache", "_vision_cache", "docs", ".venv", ".git", "ocr2epub"}


@dataclass
class Volume:
    title: str
    source_paths: list
    source_type: str
    target_epub: str
    skip_reason: str | None = None


def _target(root, folder_rel, title):
    return os.path.join(root, "_epub_output", folder_rel, title + ".epub")


def _is_zip_junk(name):
    base = name.rsplit("/", 1)[-1]
    return "__MACOSX" in name.split("/") or base.startswith("._")


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
            names = [
                n for n in z.namelist()
                if not n.endswith("/") and not _is_zip_junk(n)
            ]
    except Exception:
        return "error", []  # corrupt/encrypted/unreadable -> surfaced as a skip
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
        # deterministic traversal so --limit selects a reproducible subset
        dirs[:] = sorted(d for d in dirs if d not in IGNORE_DIRS)
        rel = os.path.relpath(dirpath, root)
        standalone_pdf_titles = {
            os.path.splitext(f)[0] for f in files if f.lower().endswith(".pdf")
        }
        for f in sorted(files):
            ext = os.path.splitext(f)[1].lower()
            full = os.path.join(dirpath, f)
            if ext == ".pdf":
                title = os.path.splitext(f)[0]
                skip = "epub-exists" if (rel, title) in existing else None
                vols.append(Volume(title, [full], "pdf", _target(root, rel, title), skip))
            elif ext == ".zip":
                kind, inner = _zip_kind(full)
                if kind == "error":
                    title = os.path.splitext(f)[0]
                    vols.append(
                        Volume(title, [full], "zip", _target(root, rel, title), "unreadable-zip")
                    )
                elif kind == "image-zip":
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

    _disambiguate_targets(vols)
    return vols


def _disambiguate_targets(vols):
    """Two active volumes with the same base title in one folder would resolve
    to the same target .epub, and the second would be silently skipped as
    already-existing. Give colliding volumes distinct output paths instead."""
    groups = defaultdict(list)
    for v in vols:
        if v.skip_reason is None:
            groups[v.target_epub].append(v)
    for group in groups.values():
        if len(group) > 1:
            group.sort(key=lambda v: (v.source_type, str(v.source_paths)))
            for i, v in enumerate(group[1:], start=2):
                base, ext = os.path.splitext(v.target_epub)
                v.target_epub = f"{base} ({i}){ext}"
