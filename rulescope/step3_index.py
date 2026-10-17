"""STEP 3 - INDEX: turn every chunk into numbers (embeddings) and store them in Pinecone.
Run:  uv run python step3_index.py

One Pinecone index called "rulescope", with two namespaces (separate drawers in the same cabinet):
  fixed    the chunks from data/chunks_fixed.jsonl
  article  the chunks from data/chunks_article.jsonl
Step 5 searches both and compares them fairly, because everything else is identical.

Safe to run again: each namespace is emptied first, so you never end up with old and new chunks mixed.
"""
import time

from pinecone import Pinecone, ServerlessSpec

from common import CHUNKS_DIR, DOC_BY_ID, EMBEDDING_DIM, INDEX_NAME, get_store, load_jsonl

STRATEGIES = ("fixed", "article")
TEST_QUESTION = "When must a bank give the customer a Key Facts Statement?"


def create_index_if_missing(pc: Pinecone) -> None:
    if INDEX_NAME in pc.list_indexes().names():
        print(f"Index '{INDEX_NAME}' already exists")
        return
    print(f"Creating index '{INDEX_NAME}' ({EMBEDDING_DIM} dimensions, cosine)...")
    pc.create_index(name=INDEX_NAME, dimension=EMBEDDING_DIM, metric="cosine",   # must match the embedding model
                    spec=ServerlessSpec(cloud="aws", region="us-east-1"))         # the free-plan region
    while not pc.describe_index(INDEX_NAME).status["ready"]:
        time.sleep(2)


def metadata_for(chunk: dict, strategy: str) -> dict:
    """What Pinecone stores next to each vector. The app shows these as the citation.
    Pinecone does not accept empty (None) values, so every field is a string."""
    doc = DOC_BY_ID[chunk["doc_id"]]
    return {"chunk_id": chunk["chunk_id"], "strategy": strategy, "doc_id": chunk["doc_id"],
            "article": chunk["article"], "section": chunk["section"] or "",
            "title": doc["title"], "reference": doc["reference"] or "",
            "effective": doc["effective"] or "", "page_url": doc["page_url"] or ""}


if __name__ == "__main__":
    pc = Pinecone()                                            # reads PINECONE_API_KEY from .env
    create_index_if_missing(pc)
    index = pc.Index(INDEX_NAME)

    for strategy in STRATEGIES:
        chunks = load_jsonl(CHUNKS_DIR / f"chunks_{strategy}.jsonl")
        try:
            index.delete(delete_all=True, namespace=strategy)  # start clean (fails harmlessly the first time)
        except Exception:
            pass

        print(f"{strategy}: embedding and uploading {len(chunks)} chunks... (a few minutes)")
        start = time.time()
        get_store(strategy).add_texts(
            texts=[c["text"] for c in chunks],
            metadatas=[metadata_for(c, strategy) for c in chunks],
            ids=[c["chunk_id"] for c in chunks],               # the same id every run -> no duplicates
            batch_size=32,                                     # vectors per upload to Pinecone
            embedding_chunk_size=64)                           # texts per request to Nebius
        print(f"{strategy}: done in {time.time() - start:.0f}s")

    time.sleep(10)                                             # Pinecone counts update a few seconds later
    counts = index.describe_index_stats()["namespaces"]
    for strategy in STRATEGIES:
        expected = len(load_jsonl(CHUNKS_DIR / f"chunks_{strategy}.jsonl"))
        stored = counts.get(strategy, {}).get("vector_count", 0)
        print(f"{strategy:8s} stored {stored:4d} / expected {expected:4d}  {'OK' if stored == expected else 'CHECK'}")

    # A first search, so you can see retrieval working before we build the full RAG step.
    print(f"\nTest search (article namespace): {TEST_QUESTION}")
    for doc, score in get_store("article").similarity_search_with_score(TEST_QUESTION, k=3):
        print(f"  {score:.3f}  {doc.metadata['title']} | {doc.metadata['article']} | {doc.metadata['section']}")