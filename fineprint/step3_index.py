"""STEP 3 - EMBED + STORE: turn every chunk into 4,096 numbers and store it in Pinecone.
Run:  uv run python step3_index.py
Each chunking strategy goes into its own namespace ("fixed", "heading") inside one index.
"""
import time

from langchain_core.documents import Document
from pinecone import Pinecone, ServerlessSpec

from common import CHUNKS_DIR, EMBEDDING_DIM, INDEX_NAME, SOURCE, get_store, load_jsonl

if __name__ == "__main__":
    pc = Pinecone()                                            # reads PINECONE_API_KEY
    if INDEX_NAME not in pc.list_indexes().names():
        pc.create_index(name=INDEX_NAME, dimension=EMBEDDING_DIM, metric="cosine",
                        spec=ServerlessSpec(cloud="aws", region="us-east-1"))
        print(f"Created index '{INDEX_NAME}'")

    for strategy in ("fixed", "heading"):
        chunks = load_jsonl(CHUNKS_DIR / f"chunks_{strategy}.jsonl")
        try:
            pc.Index(INDEX_NAME).delete(delete_all=True, namespace=strategy)   # start clean: no stale chunks
        except Exception:
            pass                                                               # namespace doesn't exist yet
        docs = [Document(page_content=c["text"],
                         metadata={"chunk_id": c["chunk_id"], "section": c["section"], **SOURCE})
                for c in chunks]
        get_store(strategy).add_documents(docs, ids=[c["chunk_id"] for c in chunks])   # embed + upload
        print(f"Uploaded {len(docs)} chunks to namespace '{strategy}'")

    time.sleep(10)    # Pinecone needs a few seconds before new records are searchable
    print("Done. Check the record counts on app.pinecone.io.")