"""STEP 2 - CHUNK: cut the clean text into small pieces, two ways, so we can compare them later.
Run:  uv run python step2_chunk.py

fixed    windows of ~200 tokens across the whole document, ignoring its structure
heading  one piece per section (cut at every heading); long sections are split further,
         and each extra piece gets its section heading repeated at the top
"""
import re

from langchain_text_splitters import RecursiveCharacterTextSplitter

from common import CHUNK_OVERLAP, CHUNK_SIZE, CHUNKS_DIR, CLEAN_PATH, save_jsonl

HEADING = re.compile(r"^#+ (.+)$", re.MULTILINE)


def splitter() -> RecursiveCharacterTextSplitter:
    # Measures size in tokens (what models count), and prefers to cut at blank lines, then line ends,
    # then sentences, then words. Table rows are separate lines, so rows are never cut in half.
    return RecursiveCharacterTextSplitter.from_tiktoken_encoder(
        encoding_name="cl100k_base", chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)


def section_at(position: int, text: str) -> str:
    """The heading that the given character position falls under."""
    current = "Introduction"
    for m in HEADING.finditer(text):
        if m.start() > position:
            break
        current = m.group(1)
    return current


def fixed_chunks(text: str) -> list[dict]:
    chunks, cursor = [], 0
    for piece in splitter().split_text(text):
        start = text.find(piece[:60], max(cursor - 1000, 0))     # where this piece starts in the document
        cursor = start if start >= 0 else cursor
        chunks.append({"text": piece, "section": section_at(cursor, text)})
    return chunks


def heading_chunks(text: str) -> list[dict]:
    starts = [m.start() for m in HEADING.finditer(text)]
    if not starts or starts[0] != 0:
        starts = [0] + starts                                        # text before the first heading
    sections = [text[a:b].strip() for a, b in zip(starts, starts[1:] + [len(text)])]

    chunks = []
    for section_text in sections:
        title = HEADING.match(section_text)
        name = title.group(1) if title else "Introduction"
        pieces = splitter().split_text(section_text)
        for i, piece in enumerate(pieces):
            if i > 0:                                                # later pieces: repeat the heading for context
                piece = f"## {name} (continued)\n{piece}"
            chunks.append({"text": piece, "section": name})
    return chunks


if __name__ == "__main__":
    text = CLEAN_PATH.read_text(encoding="utf-8")
    for strategy, make in (("fixed", fixed_chunks), ("heading", heading_chunks)):
        chunks = make(text)
        for i, c in enumerate(chunks):
            c["chunk_id"] = f"{strategy}-{i:03d}"                     # a stable, readable ID for citations
        save_jsonl(chunks, CHUNKS_DIR / f"chunks_{strategy}.jsonl")
        crossing = sum(1 for c in chunks if "\n#" in c["text"].strip())  # pieces that contain a second heading
        print(f"{strategy:8s} {len(chunks):3d} chunks | {crossing} contain a second heading -> chunks_{strategy}.jsonl")