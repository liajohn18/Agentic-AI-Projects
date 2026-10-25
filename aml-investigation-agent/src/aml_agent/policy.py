"""Local BM25 retrieval for the fictional AML demo policy corpus."""

import math
import re
from pathlib import Path


POLICY_DIR = Path(__file__).resolve().parents[2] / "data" / "policies"
TOKEN_RE = re.compile(r"[a-z0-9]+", re.IGNORECASE)
STOPWORDS = {
    "above", "about", "after", "and", "are", "based", "before", "between",
    "by", "for", "from", "has", "have", "into", "its", "more", "not",
    "only", "should", "that", "the", "their", "then", "this", "through",
    "transaction", "with", "without",
}


def _tokens(text: str) -> list[str]:
    return [
        token.casefold()
        for token in TOKEN_RE.findall(text)
        if len(token) > 2 and token.casefold() not in STOPWORDS
    ]


def _load_chunks() -> list[dict[str, str]]:
    chunks = []
    for path in sorted(POLICY_DIR.glob("*.md")):
        current_title = path.stem.replace("_", " ")
        section_lines: list[str] = []

        def add_section() -> None:
            excerpt = "\n".join(section_lines).strip()
            if not excerpt:
                return
            slug = re.sub(r"[^A-Z0-9]+", "-", current_title.upper()).strip("-")
            chunks.append(
                {
                    "policy_id": f"{path.stem.upper()}#{slug}",
                    "title": current_title,
                    "source_file": f"data/policies/{path.name}",
                    "excerpt": excerpt[:1200],
                }
            )

        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("## "):
                add_section()
                current_title = line[3:].strip()
                section_lines = []
            else:
                section_lines.append(line)
        add_section()
    return chunks


def retrieve_policy(query: str, limit: int = 3) -> list[dict[str, str | float]]:
    """Rank local policy sections with BM25 for retrieval-augmented analysis.

    This is lexical search, not embedding similarity. The corpus is fictional
    demo material and is not regulatory or legal guidance.
    """
    query_tokens = _tokens(query)
    chunks = _load_chunks()
    if not query_tokens or not chunks or limit <= 0:
        return []

    tokenized_docs = [_tokens(chunk["title"] + " " + chunk["excerpt"]) for chunk in chunks]
    doc_freq: dict[str, int] = {}
    for tokens in tokenized_docs:
        for term in set(tokens):
            doc_freq[term] = doc_freq.get(term, 0) + 1

    count = len(chunks)
    average_length = sum(map(len, tokenized_docs)) / count or 1
    k1, b = 1.5, 0.75
    scored_chunks = []
    for chunk, tokens in zip(chunks, tokenized_docs):
        frequencies: dict[str, int] = {}
        for token in tokens:
            frequencies[token] = frequencies.get(token, 0) + 1

        score = 0.0
        for term in set(query_tokens):
            frequency = frequencies.get(term, 0)
            if not frequency:
                continue
            df = doc_freq.get(term, 0)
            inverse_frequency = math.log(
                1 + (count - df + 0.5) / (df + 0.5)
            )
            denominator = frequency + k1 * (
                1 - b + b * len(tokens) / average_length
            )
            score += inverse_frequency * frequency * (k1 + 1) / denominator

        if score > 0:
            scored_chunks.append((score, chunk))

    scored_chunks.sort(key=lambda item: (-item[0], item[1]["policy_id"]))
    return [
        {
            **chunk,
            "retrieval_method": "BM25 lexical search",
            "retrieval_score": round(score, 4),
        }
        for score, chunk in scored_chunks[:limit]
    ]
