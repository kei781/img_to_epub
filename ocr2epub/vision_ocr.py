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
    # google.rpc.Code values worth retrying when Vision reports them as an in-body
    # per-image error: 3=INVALID_ARGUMENT ("Bad image data", empirically transient
    # on valid pages that succeed on an identical retry), 4=DEADLINE_EXCEEDED,
    # 8=RESOURCE_EXHAUSTED, 13=INTERNAL, 14=UNAVAILABLE. Permanent codes
    # (7=PERMISSION_DENIED, 16=UNAUTHENTICATED, ...) raise at once so a systemic
    # failure surfaces immediately instead of after N backoff sleeps per page.
    _RETRY_INBODY_CODES = {3, 4, 8, 13, 14}
    _BACKOFF = (1, 2, 4, 8)  # seconds before retries 2..5
    # Vision images:annotate rejects requests over 40 MiB. base64 inflates bytes
    # ~4/3, so keep the raw image under ~24 MiB to leave room for that plus the
    # JSON envelope. Oversized pages (illustration spreads at 350 dpi ~= 100 MP)
    # are downscaled to fit; normal body pages are far under this and pass
    # through byte-for-byte (so their OCR matches the pilot reference exactly).
    _MAX_RAW_BYTES = 24 * 1024 * 1024
    # Vision rejects OCR images over 75,000,000 pixels with an in-body
    # {"code":3,"message":"Bad image data."} error, INDEPENDENT of byte size
    # (verified empirically: 76 MP fails, 75 MP passes). A 2-page spread can be
    # small in bytes yet ~200 MP, so it must be capped by pixels too. Small margin
    # under the hard limit for boundary safety; the only pages this touches are
    # illustration spreads that is_body_text drops anyway, so resolution is moot.
    _MAX_PIXELS = 74_000_000

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
        """Return image bytes within Vision's request limits: at most _MAX_RAW_BYTES
        AND at most _MAX_PIXELS. Vision rejects OCR images over the pixel limit with
        a "Bad image data" error regardless of byte size, so a page that is small in
        bytes but huge in pixels (a 2-page spread) must still be downscaled. Data
        within both limits is returned unchanged (byte-identical -> matches the pilot
        reference); oversized data is downscaled (LANCZOS, from the original each
        pass so quality degrades only once) until it fits both."""
        # Open under a lifted DecompressionBomb guard: spreads reach ~200 MP, over
        # PIL's error threshold (2*MAX_IMAGE_PIXELS ~= 179 MP). Restore the guard in
        # finally so it never leaks into the easyocr path. Opening reads the size
        # from the header without decoding pixels, so the pixel check is cheap.
        prev_limit = Image.MAX_IMAGE_PIXELS
        Image.MAX_IMAGE_PIXELS = None
        try:
            orig = Image.open(io.BytesIO(data))
            w, h = orig.size
            if len(data) <= self._MAX_RAW_BYTES and w * h <= self._MAX_PIXELS:
                return data
            orig.load()
            if orig.mode not in ("L", "LA", "P", "RGB", "RGBA"):
                orig = orig.convert("RGB")  # a CMYK/YCbCr JPEG is not PNG-writable
            # Meet the pixel cap first (deterministic from dimensions), then iterate
            # for the byte cap (PNG size is not a closed form of dimensions).
            scale = min(1.0, (self._MAX_PIXELS / (w * h)) ** 0.5)
            for _ in range(6):
                ww = max(1, int(w * scale))
                hh = max(1, int(h * scale))
                buf = io.BytesIO()
                orig.resize((ww, hh), Image.LANCZOS).save(buf, "PNG")
                out = buf.getvalue()
                if len(out) <= self._MAX_RAW_BYTES and ww * hh <= self._MAX_PIXELS:
                    return out
                scale *= min((self._MAX_RAW_BYTES / len(out)) ** 0.5, 0.9)
            raise RuntimeError(
                f"could not fit image under {self._MAX_RAW_BYTES} bytes / "
                f"{self._MAX_PIXELS} px after 6 downscales "
                f"(last {len(out)} bytes, {ww * hh} px)"
            )
        finally:
            Image.MAX_IMAGE_PIXELS = prev_limit

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
                # Vision intermittently returns a transient in-body error (seen:
                # code 3 "Bad image data." on valid pages that succeed on an
                # identical retry). Retry the transient codes within the bounded
                # loop rather than raising now, which would abort the whole volume
                # for one glitch; a genuinely bad image keeps erroring and raises
                # after attempts. Permanent codes raise at once (fail fast).
                detail = json.dumps(r0["error"], ensure_ascii=False)
                if r0["error"].get("code") in self._RETRY_INBODY_CODES:
                    last_err = "API error: " + detail
                    continue
                raise RuntimeError("Vision API error: " + detail)
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
