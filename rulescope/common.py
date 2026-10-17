"""Settings and small helpers shared by every RuleScope step. Change values here, not inside the steps."""
import csv
import json
import os
import re
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()                                        # puts NEBIUS_API_KEY and PINECONE_API_KEY into the environment

# --- where things live ---
ROOT = Path(__file__).resolve().parent
MANIFEST_PATH = ROOT / "data" / "corpus_manifest.csv"   # the list of regulations (committed to git)
PDF_DIR = ROOT / "data" / "pdfs"                         # downloaded PDFs (git-ignored)
CLEAN_DIR = ROOT / "data" / "clean"                      # step 1 output: one .md per regulation (git-ignored)
CHUNKS_DIR = ROOT / "data"                               # step 2 output: chunks_fixed.jsonl, chunks_article.jsonl
QUESTIONS_PATH = ROOT / "eval" / "questions.jsonl"       # the frozen test questions
REPORTS_DIR = ROOT / "reports"                           # evaluation results

# --- source, attribution and disclaimer (shown in the app and the README) ---
SOURCE_NAME = "Central Bank of the UAE Rulebook"
ATTRIBUTION = "Source: Central Bank of the UAE Rulebook (public website). © Central Bank of the UAE."
DISCLAIMER = ("The Rulebook has no legal effect; the officially issued regulations prevail. "
              "RuleScope is for education only and is not legal or compliance advice.")

# --- models (Nebius Token Factory, OpenAI-compatible API) ---
NEBIUS_BASE_URL = "https://api.tokenfactory.nebius.com/v1/"
EMBEDDING_MODEL = "Qwen/Qwen3-Embedding-8B"              # text -> 4,096 numbers
EMBEDDING_DIM = 4096
CHAT_MODEL = "Qwen/Qwen3-30B-A3B-Instruct-2507"          # writes the answers

# --- chunking (tokens) ---
CHUNK_SIZE = 350                                         # legal articles are longer than KFS rows
CHUNK_OVERLAP = 50

# --- Pinecone ---
INDEX_NAME = "rulescope"                                 # one index; one namespace per chunking strategy
RERANK_MODEL = "bge-reranker-v2-m3"                      # Pinecone-hosted reranker (uses PINECONE_API_KEY)

# --- production settings: placeholders until steps 5 and 6 decide them ---
STRATEGY = "article"                                     # "fixed" or "article"
CANDIDATES = 20                                          # chunks fetched from Pinecone before reranking
TOP_K = 5                                                # chunks given to the model
USE_RERANKER = True                                      # keep only if it gains >= 5 points of Precision@1
MIN_SCORE = 0.53                                         # best similarity below this -> refuse (calibrate in step 5)
REFUSAL = "I couldn't verify that from the Central Bank regulations in RuleScope."


# --- the documents ---
def load_docs() -> list[dict]:
    """Every regulation marked include=yes in the manifest whose PDF has been downloaded."""
    with open(MANIFEST_PATH, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    docs = []
    for row in rows:
        row["path"] = PDF_DIR / row["filename"]
        if row["include"].strip().lower() == "yes" and row["path"].exists():
            docs.append(row)
    return docs


DOCS = load_docs()
DOC_BY_ID = {d["doc_id"]: d for d in DOCS}               # look up a regulation by its doc_id


# --- helpers ---
def norm(text: str) -> str:
    """Lower-case, drop markdown symbols, squash spaces. Used to compare text fairly."""
    text = re.sub(r"[*#|]", " ", text.lower())
    return " ".join(text.split())


def save_jsonl(rows: list[dict], path: Path) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def load_jsonl(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def get_embeddings():
    from langchain_openai import OpenAIEmbeddings
    return OpenAIEmbeddings(model=EMBEDDING_MODEL, base_url=NEBIUS_BASE_URL,
                            api_key=os.environ["NEBIUS_API_KEY"],
                            check_embedding_ctx_length=False)      # send plain text, not OpenAI token ids


def get_llm():
    from langchain_openai import ChatOpenAI
    return ChatOpenAI(model=CHAT_MODEL, base_url=NEBIUS_BASE_URL,
                      api_key=os.environ["NEBIUS_API_KEY"], temperature=0,
                      timeout=60, max_retries=2)                    # learned in FinePrint: stop provider hangs


def get_store(namespace: str):
    """A LangChain view of one Pinecone namespace: add chunks, search chunks."""
    from langchain_pinecone import PineconeVectorStore
    return PineconeVectorStore(index_name=INDEX_NAME, embedding=get_embeddings(), namespace=namespace)


def rerank(query: str, texts: list[str], top_n: int) -> list[tuple[int, float]]:
    """Ask Pinecone's reranker which texts best answer the query.
    Returns (position in `texts`, rerank score) pairs, best first."""
    from pinecone import Pinecone
    result = Pinecone().inference.rerank(model=RERANK_MODEL, query=query, documents=texts,
                                         top_n=top_n, return_documents=False)
    return [(item.index, float(item.score)) for item in result.data]


REPORTS_DIR.mkdir(exist_ok=True)