"""Helper (not a pipeline step): are the article labels on the chunks right?
Run:  uv run python check_labels.py
"""
import re
from collections import Counter

from common import CHUNKS_DIR, CLEAN_DIR, load_jsonl

chunks = load_jsonl(CHUNKS_DIR / "chunks_article.jsonl")

# 1. How many chunks each article got, in document order. One giant article usually means a missed heading.
for doc_id in dict.fromkeys(c["doc_id"] for c in chunks):
    counts = Counter(c["article"] for c in chunks if c["doc_id"] == doc_id)
    with_section = sum(1 for c in chunks if c["doc_id"] == doc_id and c["section"])
    total = sum(counts.values())
    print(f"\n{doc_id}: {total} chunks, {with_section} with a sub-section label")
    for article, n in counts.items():
        print(f"   {n:3d}  {article[:90]}")

# 2. The Consumer Protection Standards in detail: its article headings and some numbered lines.
text = (CLEAN_DIR / "consumer_protection_standards.md").read_text(encoding="utf-8")
print("\n--- consumer_protection_standards: article headings ---")
for line in re.findall(r"^## Article.*$", text, flags=re.MULTILINE):
    print("  ", line[:120])
print("\n--- consumer_protection_standards: first 25 lines that start with a number like 2.1 ---")
for line in re.findall(r"^(?:#+ )?\d+\.\d+.*$", text, flags=re.MULTILINE)[:25]:
    print("  ", line[:120])

# 3. The chunk the KFS answer cited as "Definitions".
chunk = next(c for c in chunks if c["chunk_id"] == "consumer_protection_standards-article-0007")
print("\n--- consumer_protection_standards-article-0007 (first 700 characters) ---")
print(chunk["text"][:700])