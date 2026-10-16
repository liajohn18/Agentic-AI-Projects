"""STEP 1 - INGEST: PDF -> clean markdown, with a quality check.
Run:  uv run python step1_ingest.py
"""
import re

import pymupdf4llm

from common import CLEAN_PATH, PDF_PATH


def clean(text: str) -> str:
    text = re.sub(r"</?mark>", "", text)                       # highlight tags around some headings
    text = text.replace("**", "")                              # bold markers
    text = re.sub(r"<br\s*/?>", " ", text)                     # line breaks inside table cells
    text = re.sub(r"^(#+)[ \t]+(.+?)[ \t]*$", r"\1 \2", text, flags=re.MULTILINE)   # tidy heading lines
    text = re.sub(r"[ \t]+\n", "\n", text)                     # spaces at line ends
    text = re.sub(r"\n{3,}", "\n\n", text)                     # at most one blank line
    return text.strip()


def number_repeated_headings(text: str) -> str:
    """This KFS has eight sections all called 'Warning !!!'. Number them so each section has a unique
    name: 'Warning !!! (1)', 'Warning !!! (2)'... Citations can then point to one specific warning."""
    titles = re.findall(r"^#+ (.+)$", text, flags=re.MULTILINE)
    repeated = {t for t in titles if titles.count(t) > 1}
    seen = {}

    def rename(match):
        hashes, title = match.group(1), match.group(2)
        if title not in repeated:
            return match.group(0)
        seen[title] = seen.get(title, 0) + 1
        return f"{hashes} {title} ({seen[title]})"

    return re.sub(r"^(#+) (.+)$", rename, text, flags=re.MULTILINE)


if __name__ == "__main__":
    # 1. Read: one markdown string per page. Tables become markdown tables, bold/large text becomes # headings,
    #    and running page headers/footers are dropped. No OCR: the PDF must have selectable text.
    pages = pymupdf4llm.to_markdown(str(PDF_PATH), page_chunks=True, use_ocr=False, header=False, footer=False)
    page_texts = [clean(p["text"]) for p in pages]

    # 2. Quality check: stop if any page came out (nearly) empty - usually a scanned page.
    empty = [i for i, t in enumerate(page_texts, start=1) if len(t) < 50]
    assert not empty, f"Pages {empty} have no text - is the PDF scanned?"

    # 3. Save one clean file. Pages are joined so a section that crosses a page break stays together.
    markdown = number_repeated_headings("\n\n".join(page_texts))
    CLEAN_PATH.write_text(markdown, encoding="utf-8")

    headings = re.findall(r"^#+ (.+)$", markdown, flags=re.MULTILINE)
    tables = len(re.findall(r"^\|[-: |]+\|$", markdown, flags=re.MULTILINE))
    print(f"{len(pages)} pages -> {len(markdown):,} characters, {len(headings)} headings, {tables} tables")
    print("Headings:", headings)
    print(f"Saved {CLEAN_PATH.name}. Open it and compare with the PDF before continuing.")