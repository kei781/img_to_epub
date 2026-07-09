import re

# 문장 종결로 취급할 말미 문자: 마침표류 + 닫는 따옴표/괄호
_SENT_END = ("。", ".", "!", "?", "！", "？", "”", "’", "」", "』", ")", '"', "'")


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
