import os
import json
import hashlib


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
        self.reader = easyocr.Reader(["ko", "en"], gpu=True)

    def _cache_path(self, cache_key):
        h = hashlib.sha1(cache_key.encode("utf-8")).hexdigest()
        return os.path.join(self.cache_dir, h + ".json")

    def page_text(self, page, cache_key):
        if page.text is not None:
            return page.text
        cp = self._cache_path(cache_key)
        if os.path.exists(cp):
            with open(cp, encoding="utf-8") as f:
                return json.load(f)["text"]
        results = self.reader.readtext(page.image_path, detail=1, paragraph=False)
        lines = sort_reading_order(results)
        text = "\n".join(lines)
        with open(cp, "w", encoding="utf-8") as f:
            json.dump({"text": text}, f, ensure_ascii=False)
        return text
