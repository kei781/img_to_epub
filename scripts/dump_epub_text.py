import re
import sys
from ebooklib import epub

book = epub.read_epub(sys.argv[1])
limit = int(sys.argv[2]) if len(sys.argv) > 2 else 3000
docs = [i for i in book.get_items() if i.get_type() == 9]
chunks = [d.get_content().decode("utf-8", "ignore") for d in docs]
full = re.sub(r"<[^>]+>", "", "\n".join(chunks))
print(full[:limit])
