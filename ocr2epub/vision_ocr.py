import re
import io
import os
import json
import time
import base64
import hashlib
import urllib.request
import urllib.error

from PIL import Image

from .ocr import _preprocess_image

# Middle-dot / bullet family Vision emits for ellipsis, plus the ellipsis char
# itself. Kept as a class so a run of 2+ collapses but a lone interpunct (e.g.
# "1·2권") survives. ASCII "..." (3+) is also treated as an ellipsis.
_DOT_RUN = re.compile(r"[・·∙•…]{2,}|\.{3,}")


def normalize_vision_text(text):
    """Clean Google Vision OCR artifacts seen on Korean lightnovel scans:
      1. collapse middle-dot / bullet / ellipsis runs to a standard '……';
      2. drop spurious standalone '66'/'99' lines (stylized double-quotes Vision
         mis-read as digits and split onto their own line).
    Dash-drops (rare, e.g. '——' rendered as no gap) are left as-is: any generic
    fix risks over-correction."""
    text = _DOT_RUN.sub("……", text)
    lines = [ln for ln in text.split("\n") if ln.strip() not in ("66", "99")]
    return "\n".join(lines)


class VisionOcrEngine:
    """Google Cloud Vision OCR with the same seam as OcrEngine. Caches RAW
    Vision text (per page) in its own dir; normalization is applied on read so
    changing normalize rules needs only a re-run, not a re-call."""

    ENDPOINT = "https://vision.googleapis.com/v1/images:annotate"
    _RETRY_STATUS = {429, 500, 502, 503, 504}
    _BACKOFF = (1, 2, 4, 8)  # seconds before retries 2..5
    # Vision images:annotate rejects requests over 40 MiB. base64 inflates bytes
    # ~4/3, so keep the raw image under ~24 MiB to leave room for that plus the
    # JSON envelope. Oversized pages (illustration spreads at 350 dpi ~= 100 MP)
    # are downscaled to fit; normal body pages are far under this and pass
    # through byte-for-byte (so their OCR matches the pilot reference exactly).
    _MAX_RAW_BYTES = 24 * 1024 * 1024

    def __init__(self, cache_dir, key_path):
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)
        self.key = open(key_path, encoding="utf-8-sig").read().strip()

    def _cache_path(self, cache_key):
        h = hashlib.sha1(cache_key.encode("utf-8")).hexdigest()
        return os.path.join(self.cache_dir, h + ".json")

    def _read_cache(self, cache_key):
        cp = self._cache_path(cache_key)
        if os.path.exists(cp):
            try:
                with open(cp, encoding="utf-8") as f:
                    return json.load(f)["text"]
            except (json.JSONDecodeError, KeyError, ValueError, OSError):
                try:
                    os.remove(cp)  # truncated/interrupted write -> re-OCR
                except OSError:
                    pass
        return None

    def _write_cache(self, cache_key, text):
        cp = self._cache_path(cache_key)
        tmp = cp + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"text": text}, f, ensure_ascii=False)
        os.replace(tmp, cp)  # atomic: cp never left half-written

    def _fit_payload(self, data):
        """Return image bytes small enough for the Vision request cap. Data under
        the cap is returned unchanged; oversized data is downscaled (LANCZOS, from
        the original each pass so quality degrades only once) until it fits."""
        if len(data) <= self._MAX_RAW_BYTES:
            return data
        # Spreads render to ~100 MP; that is under PIL's DecompressionBombError
        # threshold (2*MAX_IMAGE_PIXELS ~= 179 MP) but over its warning line
        # (~89 MP). Lift the guard just for our own trusted-scan open (suppresses
        # the warning, and covers a rare >179 MP page), then restore it.
        prev_limit = Image.MAX_IMAGE_PIXELS
        Image.MAX_IMAGE_PIXELS = None
        try:
            orig = Image.open(io.BytesIO(data))
            orig.load()
        finally:
            Image.MAX_IMAGE_PIXELS = prev_limit
        if orig.mode not in ("L", "LA", "P", "RGB", "RGBA"):
            orig = orig.convert("RGB")  # e.g. a CMYK/YCbCr JPEG is not PNG-writable
        scale = 1.0
        for _ in range(6):
            scale *= min((self._MAX_RAW_BYTES / len(data)) ** 0.5, 0.9)
            w = max(1, int(orig.width * scale))
            h = max(1, int(orig.height * scale))
            buf = io.BytesIO()
            orig.resize((w, h), Image.LANCZOS).save(buf, "PNG")
            data = buf.getvalue()
            if len(data) <= self._MAX_RAW_BYTES:
                return data
        raise RuntimeError(
            f"could not fit image under {self._MAX_RAW_BYTES} bytes after 6 "
            f"downscales (last {len(data)} bytes)"
        )

    def _image_bytes(self, image_path, preprocess):
        if not preprocess:
            with open(image_path, "rb") as f:
                return self._fit_payload(f.read())
        # low-res scan: reuse the pipeline's LANCZOS upscale + levels cleanup,
        # re-encode to PNG for the API. (Phase-2 gate may swap this method.)
        arr = _preprocess_image(image_path)
        buf = io.BytesIO()
        Image.fromarray(arr).save(buf, "PNG")
        return self._fit_payload(buf.getvalue())

    def _call_vision(self, image_path, preprocess):
        content = base64.b64encode(self._image_bytes(image_path, preprocess)).decode("ascii")
        body = {
            "requests": [{
                "image": {"content": content},
                "features": [{"type": "DOCUMENT_TEXT_DETECTION"}],
                "imageContext": {"languageHints": ["ko", "en"]},
            }]
        }
        data = json.dumps(body).encode("utf-8")
        url = self.ENDPOINT + "?key=" + self.key
        last_err = None
        for attempt in range(5):
            if attempt:
                time.sleep(self._BACKOFF[attempt - 1])
            try:
                req = urllib.request.Request(
                    url, data=data, headers={"Content-Type": "application/json"}
                )
                with urllib.request.urlopen(req, timeout=180) as r:
                    resp = json.load(r)
            except urllib.error.HTTPError as e:
                if e.code in self._RETRY_STATUS:
                    last_err = f"HTTP {e.code}"
                    continue
                detail = e.read().decode("utf-8", "replace")[:500]
                raise RuntimeError(f"Vision hard error HTTP {e.code}: {detail}")
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                last_err = f"{type(e).__name__}: {e}"
                continue
            r0 = resp["responses"][0]
            if "error" in r0:
                raise RuntimeError(
                    "Vision API error: " + json.dumps(r0["error"], ensure_ascii=False)
                )
            fta = r0.get("fullTextAnnotation")
            return fta["text"] if fta else ""   # "" = genuine blank page
        raise RuntimeError(f"Vision failed after 5 attempts: {last_err}")

    def page_text(self, page, cache_key, preprocess=False):
        if page.text is not None:
            return page.text                    # text-layer passthrough
        raw = self._read_cache(cache_key)
        if raw is None:
            raw = self._call_vision(page.image_path, preprocess)
            self._write_cache(cache_key, raw)   # only cached on success
        return normalize_vision_text(raw)
