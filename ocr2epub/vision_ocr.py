import re

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
