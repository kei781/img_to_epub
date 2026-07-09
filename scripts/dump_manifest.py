import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ocr2epub.discover import discover

vols = discover(sys.argv[1])
active = [v for v in vols if v.skip_reason is None]
print(f"active={len(active)} total={len(vols)}")
for v in active:
    print(f"[{v.source_type}] {v.title}")
for v in vols:
    if v.skip_reason:
        print(f"SKIP({v.skip_reason}) {v.title}")
