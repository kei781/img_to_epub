import os
import json
import hashlib

import numpy as np
from PIL import Image


def _preprocess_image(path, black=80, white=155, min_width=1500):
    """Clean a low-quality scan for OCR: grayscale, upscale small scans, and a
    'levels' curve that pushes light bleed-through/ghost pixels to white while
    darkening real text. Measured to cut ghost 'alien-string' detections on
    REN scans (grayscale levels beat hard binarization for EasyOCR). Returns an
    RGB array. Does NOT recover soft-glyph detail, so it does not fix body
    syllable errors on genuinely blurry scans — only the spurious garbage."""
    im = Image.open(path).convert("L")
    if im.width < min_width:
        im = im.resize((im.width * 2, im.height * 2), Image.LANCZOS)
    a = np.asarray(im).astype(np.float32)
    a = (a - black) / max(1.0, white - black) * 255.0
    a = np.clip(a, 0, 255).astype(np.uint8)
    return np.stack([a, a, a], axis=-1)


def _ytop(bbox):
    return min(p[1] for p in bbox)


def _xleft(bbox):
    return min(p[0] for p in bbox)


def sort_reading_order(results, line_tol=15):
    items = [(_ytop(b), _xleft(b), t) for (b, t, c) in results]
    items.sort(key=lambda r: (r[0], r[1]))
    # 같은 줄(비슷한 y)은 x 순으로 묶기
    lines, cur, cur_y = [], [], None
    for y, x, t in items:
        if cur_y is None or abs(y - cur_y) <= line_tol:
            cur.append((x, t))
            cur_y = y if cur_y is None else cur_y
        else:
            lines.append(cur)
            cur = [(x, t)]
            cur_y = y
    if cur:
        lines.append(cur)
    out = []
    for ln in lines:
        ln.sort(key=lambda r: r[0])
        out.append(" ".join(t for _, t in ln))
    return out


class OcrEngine:
    def __init__(self, cache_dir):
        import easyocr  # lazy: pure funcs above stay importable without GPU stack

        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)
        # verbose=False silences per-page "Progress: |...|% Complete" spam that
        # would otherwise bloat the batch log to GBs over ~20k pages.
        self.reader = easyocr.Reader(["ko", "en"], gpu=True, verbose=False)

    def _cache_path(self, cache_key):
        h = hashlib.sha1(cache_key.encode("utf-8")).hexdigest()
        return os.path.join(self.cache_dir, h + ".json")

    def page_text(self, page, cache_key, preprocess=False):
        if page.text is not None:
            return page.text
        cp = self._cache_path(cache_key)
        if os.path.exists(cp):
            try:
                with open(cp, encoding="utf-8") as f:
                    return json.load(f)["text"]
            except (json.JSONDecodeError, KeyError, ValueError, OSError):
                # truncated/empty cache from an interrupted write -> re-OCR
                try:
                    os.remove(cp)
                except OSError:
                    pass
        # Load via PIL, not by path: cv2.imread (EasyOCR's default) returns None
        # for non-ASCII paths on Windows (e.g. Korean folder names from rar),
        # which crashed the rar volume. PIL handles Unicode paths + more formats.
        # preprocess=True (low-quality scans) applies the levels cleanup.
        if preprocess:
            img = _preprocess_image(page.image_path)
        else:
            img = np.array(Image.open(page.image_path).convert("RGB"))
        results = self.reader.readtext(img, detail=1, paragraph=False)
        lines = sort_reading_order(results)
        text = "\n".join(lines)
        tmp = cp + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"text": text}, f, ensure_ascii=False)
        os.replace(tmp, cp)  # atomic: cp is never left half-written
        return text
