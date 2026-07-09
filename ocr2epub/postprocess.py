import re

# 문장 종결로 취급할 말미 문자: 마침표류 + 닫는 따옴표/괄호
_SENT_END = ("。", ".", "!", "?", "！", "？", "”", "’", "」", "』", ")", '"', "'")


def _hangul_count(s):
    return sum(1 for c in s if "가" <= c <= "힣")


def is_body_text(lines, min_total=80, min_long_lines=2, long_line_hangul=12):
    """True if a page's OCR lines look like real prose body text, not a
    cover/illustration page that OCR'd into scattered garbage tokens.

    Judged by Hangul density + presence of several real prose lines. Illustration
    pages yield few, short tokens (max line ~5 Hangul) with little total text;
    body pages yield many long prose lines (300+ Hangul). EasyOCR confidence is
    deliberately NOT used — measured body and illustration pages score alike."""
    total = 0
    long_lines = 0
    for ln in lines:
        h = _hangul_count(ln)
        total += h
        if h >= long_line_hangul:
            long_lines += 1
    return total >= min_total and long_lines >= min_long_lines


def strip_furniture(lines):
    out = []
    for ln in lines:
        s = ln.strip()
        if not s:
            out.append("")  # 빈 줄은 문단 경계로 보존
            continue
        if re.fullmatch(r"[-—\s]*\d+[-—\s]*", s):  # 페이지번호만 있는 줄
            continue
        out.append(s)
    return out


def merge_paragraphs(page_lines):
    lines = strip_furniture(page_lines)
    paras, buf = [], ""

    def flush():
        nonlocal buf
        if buf.strip():
            paras.append(buf.strip())
        buf = ""

    for ln in lines:
        if ln == "":
            flush()
            continue
        if buf == "":
            buf = ln
        else:
            buf += " " + ln
        if ln.endswith(_SENT_END):
            flush()
    flush()
    return paras
