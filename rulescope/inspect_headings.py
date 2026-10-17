"""Helper: show how each clean regulation is structured, so the chunker can follow it.
Run:  uv run python inspect_headings.py
"""
import re
from pathlib import Path

for f in sorted(Path("data/clean").glob("*.md")):
    text = f.read_text(encoding="utf-8")
    headings = re.findall(r"^#+ .*$", text, flags=re.MULTILINE)                       # markdown headings
    numbered = re.findall(r"^\s*\(?\d+(?:\.\d+)*[.)]?\s+[A-Z][^\n]{0,80}$", text, flags=re.MULTILINE)  # "3.2 Title", "1. Scope"
    article_words = re.findall(r"^.{0,20}\bArticle\b.{0,60}$", text, flags=re.MULTILINE | re.IGNORECASE)
    print(f"\n=== {f.stem}: {len(headings)} headings, {len(numbered)} numbered lines, "
          f"{len(article_words)} lines starting near 'Article'")
    for h in headings[:8]:
        print("  H  ", h[:100])
    for n in numbered[:6]:
        print("  N  ", n.strip()[:100])
    for a in article_words[:4]:
        print("  A  ", a.strip()[:100])