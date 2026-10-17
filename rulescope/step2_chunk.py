"""STEP 2 - CHUNK: cut every clean regulation into small pieces, two ways, so step 5 can compare them.
Run:  uv run python step2_chunk.py

fixed    windows of ~350 tokens across each regulation, ignoring its structure
article  one unit per Article (or per numbered section when a document has no articles, e.g. the AI note);
         long articles are split further by size, and each piece remembers its sub-section (2.1, 6.1.2 ...)

Every chunk records which regulation, article and sub-section it comes from, and starts with a short
context line ("[Consumer Protection Regulation | Article 2: Disclosure and Transparency]") so the
embedding knows where the text belongs.
"""
import re

from langchain_text_splitters import RecursiveCharacterTextSplitter

from common import CHUNK_OVERLAP, CHUNK_SIZE, CHUNKS_DIR, CLEAN_DIR, DOCS, save_jsonl

ARTICLE = re.compile(r"^## (Article \w+)(?::\s*(.*))?$", re.MULTILINE)            # made by step 1
SECTION = re.compile(r"^#{1,3} (\d{1,2})\.?\s+([A-Z].{2,100})$", re.MULTILINE)      # "## 1 Definitions" (no-article docs)
SUBSECTION = re.compile(r"^(?:#+ )?(\d+(?:\.\d+)+)\.?\s+([A-Z][^\n]{2,100})$", re.MULTILINE)   # "6.1.2 Data Management"
MIN_CHARS = 40                                                                      # skip near-empty pieces


def splitter() -> RecursiveCharacterTextSplitter:
    # Size in tokens; prefers to cut at blank lines, then line ends, then sentences, then words.
    return RecursiveCharacterTextSplitter.from_tiktoken_encoder(
        encoding_name="cl100k_base", chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)


def pieces(text: str) -> list[tuple[int, str]]:
    """(start position, text) for every piece the splitter cuts from `text`.
    We find each start ourselves: LangChain's add_start_index treats the 50-token overlap as 50 characters,
    so it often looks too far ahead and returns -1 - which made many fixed chunks look like 'Preamble'."""
    found, search_from = [], 0
    for piece in splitter().split_text(text):
        position = text.find(piece, search_from)
        if position == -1:                                   # should not happen; keep the order anyway
            position = search_from
        found.append((position, piece))
        search_from = position + 1                           # the next piece starts after this one starts
    return found


def marks(text: str) -> list[tuple[int, str]]:
    """Where each Article starts (or each numbered section, for documents without articles)."""
    found = [(m.start(), m.group(1) + (f": {m.group(2)}" if m.group(2) else "")) for m in ARTICLE.finditer(text)]
    if not found:
        found = [(m.start(), f"Section {m.group(1)}: {m.group(2).strip()}") for m in SECTION.finditer(text)]
    return found


def label_at(position: int, starts: list[tuple[int, str]], default: str = "Preamble") -> str:
    """The last label that starts at or before `position`."""
    label = default
    for pos, name in starts:
        if pos > position:
            break
        label = name
    return label


def make_chunk(doc: dict, article: str, section: str, body: str) -> dict:
    where = article + (f" > {section}" if section else "")
    return {"doc_id": doc["doc_id"], "article": article, "section": section,
            "text": f"[{doc['title']} | {where}]\n{body.strip()}"}


def article_chunks(doc: dict, text: str) -> list[dict]:
    """Cut at every article first; only then split long articles by size."""
    starts = marks(text)
    if not starts or starts[0][0] > 0:
        starts = [(0, "Preamble")] + starts                            # introduction, scope, objectives
    ends = [s for s, _ in starts[1:]] + [len(text)]
    chunks = []
    for (start, label), end in zip(starts, ends):
        unit = text[start:end]
        subsections = [(m.start(), f"{m.group(1)} {m.group(2).strip()}") for m in SUBSECTION.finditer(unit)]
        for pos, piece in pieces(unit):                                # a short article stays in one piece
            if len(piece.strip()) >= MIN_CHARS:
                chunks.append(make_chunk(doc, label, label_at(pos, subsections, default=""), piece))
    return chunks


def fixed_chunks(doc: dict, text: str) -> list[dict]:
    """Same-size windows over the whole regulation; each is labelled with the article it starts in."""
    starts = marks(text)
    return [make_chunk(doc, label_at(pos, starts), "", piece)
            for pos, piece in pieces(text) if len(piece.strip()) >= MIN_CHARS]


if __name__ == "__main__":
    for strategy, make in (("fixed", fixed_chunks), ("article", article_chunks)):
        all_chunks = []
        for doc in DOCS:
            text = (CLEAN_DIR / f"{doc['doc_id']}.md").read_text(encoding="utf-8")
            for i, chunk in enumerate(make(doc, text)):
                chunk["chunk_id"] = f"{doc['doc_id']}-{strategy}-{i:04d}"     # e.g. telemarketing_regulation-article-0012
                all_chunks.append(chunk)
        save_jsonl(all_chunks, CHUNKS_DIR / f"chunks_{strategy}.jsonl")

        mixed = sum(1 for c in all_chunks if len(ARTICLE.findall(c["text"])) > 1)   # pieces containing two articles
        labelled = sum(1 for c in all_chunks if c["article"] != "Preamble")
        sizes = sorted(len(c["text"]) for c in all_chunks)
        print(f"{strategy:8s} {len(all_chunks):5d} chunks | {mixed:4d} contain two articles | "
              f"{labelled / len(all_chunks):.0%} labelled with an article/section | "
              f"median {sizes[len(sizes) // 2]:,} chars -> chunks_{strategy}.jsonl")