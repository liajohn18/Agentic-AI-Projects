"""STEP 0 - DOWNLOAD: fetch every PDF listed in data/corpus_manifest.csv and check it is usable.
Run:  uv run python step0_download.py            (skips files you already have)
      uv run python step0_download.py --force    (downloads everything again)

For each row with include=yes it:
  1. downloads the URL into data/pdfs/<filename> (with a normal browser User-Agent; some sites block scripts)
  2. checks it really is a PDF (files start with %PDF) and counts pages
  3. checks it has selectable text (scanned PDFs have almost none)
  4. writes today's date into the manifest's retrieved_on column
Results go to reports/download_report.csv. Fix or download by hand anything marked FAILED or CHECK.
"""
import csv
import sys
import time
import urllib.request
from datetime import date
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parent
MANIFEST = ROOT / "data" / "corpus_manifest.csv"
PDF_DIR = ROOT / "data" / "pdfs"
REPORT = ROOT / "reports" / "download_report.csv"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                         "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
           "Accept": "application/pdf,*/*"}
MIN_CHARS_PER_PAGE = 100          # less than this on average -> probably scanned


def download(url: str, path: Path) -> None:
    request = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(request, timeout=60) as response:
        data = response.read()
    if not data.startswith(b"%PDF"):
        raise ValueError("not a PDF (the site returned a web page instead)")
    path.write_bytes(data)


def inspect(path: Path) -> tuple[int, int]:
    """Pages, and average characters of text per page."""
    with pymupdf.open(path) as pdf:
        chars = sum(len(page.get_text()) for page in pdf)
        return pdf.page_count, chars // max(pdf.page_count, 1)


if __name__ == "__main__":
    force = "--force" in sys.argv
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    REPORT.parent.mkdir(exist_ok=True)

    with open(MANIFEST, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    fields = list(rows[0].keys())

    report = []
    for row in rows:
        if row["include"].strip().lower() != "yes":
            continue
        path = PDF_DIR / row["filename"]
        status, detail, pages, chars = "OK", "", 0, 0
        try:
            if force or not path.exists():
                download(row["url"], path)
                row["retrieved_on"] = date.today().isoformat()
                time.sleep(2)                                     # be polite to the website: one file every few seconds
            pages, chars = inspect(path)
            if chars < MIN_CHARS_PER_PAGE:
                status, detail = "CHECK", "very little text - scanned or image-only?"
        except Exception as error:                                # network error, 403, not a PDF...
            status, detail = "FAILED", str(error)[:120]
        report.append({"doc_id": row["doc_id"], "title": row["title"], "status": status, "pages": pages,
                       "chars_per_page": chars, "detail": detail})
        print(f"{status:6s} {row['doc_id']:30s} {pages:3d} pages {chars:6d} chars/page {detail}")

    with open(MANIFEST, "w", newline="", encoding="utf-8") as f:   # save the retrieved_on dates
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    with open(REPORT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=report[0].keys())
        w.writeheader()
        w.writerows(report)

    counts = {s: sum(r["status"] == s for r in report) for s in ("OK", "CHECK", "FAILED")}
    print(f"\n{counts} -> details in {REPORT.relative_to(ROOT)}")