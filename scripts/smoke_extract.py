import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ocr2epub.discover import discover
from ocr2epub.extract import extract_pages

root = sys.argv[1]
only = sys.argv[2] if len(sys.argv) > 2 else "다나카"
vols = [v for v in discover(root) if v.skip_reason is None and only in v.title]
if not vols:
    print("no matching volume")
    sys.exit(1)
v = vols[0]
print(f"[{v.source_type}] {v.title}  paths={v.source_paths}")
work = tempfile.mkdtemp(prefix="smoke_")
pages = extract_pages(v, work)
print(f"pages={len(pages)}")
for pg in pages[:8]:
    kind = "text" if pg.text is not None else "image"
    detail = pg.text[:40] if pg.text else pg.image_path
    print(f"  p{pg.index} [{kind}] {detail}")
