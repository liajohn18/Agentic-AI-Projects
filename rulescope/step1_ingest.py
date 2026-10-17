"""STEP 1 - INGEST: every regulation PDF -> one clean markdown file, plus a quality report.
Run:  uv run python step1_ingest.py

For each regulation in the manifest it:
  1. reads the PDF as markdown (tables stay tables, headings become # lines; no OCR)
  2. cleans formatting noise, keeps the English text of bilingual pages, drops table-of-contents rows,
     and removes lines repeated on most pages (page headers, footers, labels)
  3. marks every "Article ..." heading in one standard form: "## Article 7: Title"
  4. saves data/clean/<doc_id>.md and reports what it found in reports/ingest_report.csv
"""
import csv
import re
from collections import Counter

import pymupdf4llm

from common import CLEAN_DIR, DOCS, REPORTS_DIR

# A line that starts with "Article 7", "Article (7)", "ARTICLE 7:", "**Article 7 - Title**", "## Article (7) Title"...
ARTICLE_LINE = re.compile(r"^[#*\s]*article\s*\(?\s*(\d+[a-z]?)\s*\)?\s*[:.\-–—]?\s*(.*?)[*\s]*$", re.IGNORECASE)
MIN_PAGE_CHARS = 50                 # a page with less text than this is probably a scan or blank


ARABIC = re.compile(r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF\u0660-\u0669]+")
TOC_ROW = re.compile(r"^\|\s*Article\s*\(?\s*\d+", re.IGNORECASE)     # table-of-contents rows: |Article (1)|Definitions|3|


def clean(text: str) -> str:
    text = re.sub(r"</?(mark|u|sup|sub)>", "", text)           # highlight, underline, superscript tags
    text = text.replace("**", "")                              # bold markers
    text = re.sub(r"<br\s*/?>", " ", text)                     # line breaks inside table cells
    text = ARABIC.sub("", text)                                # bilingual PDFs: keep the English text only
    text = "\n".join(l for l in text.splitlines() if not TOC_ROW.match(l.strip()))   # drop table-of-contents rows
    text = re.sub(r"^(#+)[ \t]+(.+?)[ \t]*$", r"\1 \2", text, flags=re.MULTILINE)   # tidy heading lines
    text = re.sub(r"^#+[^A-Za-z\n]*$", "", text, flags=re.MULTILINE)   # headings left with no words after removing Arabic
    text = re.sub(r"[ \t]{2,}", " ", text)                     # squash runs of spaces
    text = re.sub(r"[ \t]+\n", "\n", text)                     # spaces at line ends
    text = re.sub(r"\n{3,}", "\n\n", text)                     # at most one blank line
    return text.strip()


def drop_repeated_lines(pages: list[str]) -> tuple[list[str], set[str]]:
    """Remove short lines that appear on at least 60% of pages (running headers, footers, classification labels).
    Table rows (starting with |) are never removed."""
    counts = Counter()
    for page in pages:
        counts.update({line.strip() for line in page.splitlines() if line.strip()})
    limit = max(3, len(pages) * 0.6)
    repeated = {line for line, n in counts.items()
                if n >= limit and len(line) < 120 and not line.startswith("|")}
    kept = ["\n".join(l for l in page.splitlines() if l.strip() not in repeated) for page in pages]
    return kept, repeated


CLAUSE_LINE = re.compile(r"^(?:#+ |- )?(\d{1,2})\.\d+")       # a numbered clause such as "2.1.1.19 ..." or "##### 2.1.3 ..."


def tidy_title(title: str) -> str:
    """Clean an article title. Bilingual PDFs glue the next lines' numbering onto it:
    'Business Conduct : 5 5.1 Responsible Business Conduct 1.5 ...' -> 'Business Conduct'
    'Complaint Management and : 8 Complaint Resolution 8.1 ...'     -> 'Complaint Management and Complaint Resolution'"""
    title = re.sub(r"\(\s*:?\s*\d+\s*\)|\)\s*:?\s*\d+\s*\(", " ", title)      # leftovers like "(: 2)" or ") 1("
    title = re.split(r"\s\d+\.\d+", title)[0]                            # stop at the first sub-section number
    title = re.sub(r"\s*:\s*", " ", title)                                # drop stray " : "
    title = re.sub(r"\s\d+(?=\s|$)", "", title)                            # drop lone numbers like " 8"
    title = re.sub(r"[\s(\[\]:;.,\-–—\d]+$", "", title)                    # trailing punctuation and digits
    title = " ".join(title.split()).strip(" *#:-–—(")
    if title.count("(") > title.count(")"):                                # "Do Not Call Registry (DNCR" -> "...(DNCR)"
        title += ")"
    return title


def mark_articles(text: str) -> tuple[str, list[str]]:
    """Rewrite each article heading as '## Article <n>: <title>' so step 2 can cut the text at every article.
    A line counts as a heading only if it is short and the words after the number look like a title
    (start with a capital letter or nothing, and do not end like a sentence).
    Bilingual PDFs often repeat the same heading on the next line or two; the repeat is dropped.

    Some headings cannot be read at all (in the Consumer Protection Standards, Articles 2 and 3 are lost in the
    bilingual layout). Their clauses are still numbered "2.1.1 ...", so a second pass adds '## Article 2' just
    before the first clause numbered 2.x - but only for a missing number that comes next in sequence."""
    lines, found = [], []
    last_heading, last_at = None, -10
    for i, line in enumerate(text.splitlines()):
        m = ARTICLE_LINE.match(line)
        if m and len(line) < 160:
            number, title = m.group(1), tidy_title(m.group(2))
            looks_like_title = (not title) or (title[0].isupper() or title[0].isdigit())
            if looks_like_title and not title.endswith((".", ";", ",")):
                heading = f"Article {number}" + (f": {title}" if title else "")
                if heading == last_heading and i - last_at <= 3:            # bilingual repeat of the same heading
                    continue
                line, last_heading, last_at = f"## {heading}", heading, i
                found.append(heading)
        lines.append(line)

    # Second pass: fill gaps in the article sequence from the clause numbers.
    numbers = {int(re.match(r"Article (\d+)", h).group(1)) for h in found if re.match(r"Article \d+", h)}
    if not numbers:
        return "\n".join(lines), found                                    # no articles at all (e.g. the AI note)
    filled, current = [], 0
    for line in lines:
        heading = re.match(r"^## Article (\d+)", line)
        clause = CLAUSE_LINE.match(line)
        if heading:
            current = int(heading.group(1))
        elif clause and int(clause.group(1)) == current + 1 and current + 1 not in numbers:
            current += 1
            filled.append(f"## Article {current}")
            found.append(f"Article {current} (from clause numbers)")
        filled.append(line)
    return "\n".join(filled), found


if __name__ == "__main__":
    CLEAN_DIR.mkdir(exist_ok=True)
    report = []
    for doc in DOCS:
        # 1. Read: one markdown string per page.
        pages = pymupdf4llm.to_markdown(str(doc["path"]), page_chunks=True, use_ocr=False, header=False, footer=False)
        texts = [clean(p["text"]) for p in pages]
        empty = [i for i, t in enumerate(texts, start=1) if len(t) < MIN_PAGE_CHARS]

        # 2. Remove repeated page furniture, then join pages so an article crossing a page break stays together.
        texts, repeated = drop_repeated_lines(texts)
        markdown, articles = mark_articles("\n\n".join(texts))
        markdown = re.sub(r"\n{3,}", "\n\n", markdown).strip()
        markdown = f"# {doc['title']}\n\n{markdown}\n"                  # the regulation's title on top

        # 3. Save and measure.
        (CLEAN_DIR / f"{doc['doc_id']}.md").write_text(markdown, encoding="utf-8")
        numbers = [a.split(":")[0] for a in articles]
        duplicates = sorted({n for n in numbers if numbers.count(n) > 1})
        row = {"doc_id": doc["doc_id"], "pages": len(pages), "chars": len(markdown),
               "headings": len(re.findall(r"^#+ ", markdown, flags=re.MULTILINE)),
               "articles": len(articles), "repeated_article_numbers": " ".join(duplicates),
               "tables": len(re.findall(r"^\|[-: |]+\|$", markdown, flags=re.MULTILINE)),
               "empty_pages": " ".join(map(str, empty)),
               "removed_repeated_lines": " | ".join(sorted(repeated))[:200],
               "first_articles": " | ".join(articles[:3])}
        report.append(row)
        print(f"{doc['doc_id']:36s} {row['pages']:4d} pages {row['chars']:8,d} chars "
              f"{row['articles']:4d} articles {row['tables']:3d} tables"
              + (f"  EMPTY PAGES: {row['empty_pages']}" if empty else ""))

    with open(REPORTS_DIR / "ingest_report.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=report[0].keys())
        w.writeheader()
        w.writerows(report)

    total_chars = sum(r["chars"] for r in report)
    print(f"\n{len(report)} regulations -> {total_chars:,} characters (about {total_chars // 4:,} tokens)")
    print("Saved data/clean/*.md and reports/ingest_report.csv. Open a few .md files and compare with the PDFs.")