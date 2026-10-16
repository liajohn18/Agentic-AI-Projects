"""Settings and small helpers shared by every step. Change values here, not inside the steps."""
import json
import os
import re
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()                                   # puts NEBIUS_API_KEY and PINECONE_API_KEY into the environment

# --- where things live ---
ROOT = Path(__file__).resolve().parent
PDF_PATH = ROOT / "data" / "enbd_accounts_kfs.pdf"    # the one source document
CLEAN_PATH = ROOT / "data" / "clean.md"               # step 1 output
CHUNKS_DIR = ROOT / "data"                            # step 2 output
QUESTIONS_PATH = ROOT / "eval" / "questions.jsonl"    # your test questions
REPORTS_DIR = ROOT / "reports"                        # results

# --- document facts, shown in citations ---
SOURCE = {"bank": "Emirates NBD", "title": "Key Facts Statement: Current and Savings Accounts (Individuals)",
          "url": "https://www.emiratesnbd.com/kfs", "retrieved_on": "2026-10-15"}   # your download date


# --- models (Nebius Token Factory, OpenAI-compatible API) ---
NEBIUS_BASE_URL = "https://api.tokenfactory.nebius.com/v1/"
EMBEDDING_MODEL = "Qwen/Qwen3-Embedding-8B"           # text -> 4,096 numbers
EMBEDDING_DIM = 4096
CHAT_MODEL = "Qwen/Qwen3-30B-A3B-Instruct-2507"       # writes the answers

# --- chunking (tokens) ---
CHUNK_SIZE = 200
CHUNK_OVERLAP = 30

# --- Pinecone ---
INDEX_NAME = "fineprint-nebius"                    # one index; one namespace per chunking strategy

# --- production settings: choose them from your step 5 and step 6 results ---
STRATEGY = "fixed"                          # "fixed" or "heading"
TOP_K = 5                                     # chunks given to the model
MIN_SCORE = 0.60                              # best-match score below this -> refuse
REFUSAL = "I couldn't verify that from the bank's Key Facts Statement."


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
                            check_embedding_ctx_length=False)


def get_llm():
    from langchain_openai import ChatOpenAI
    return ChatOpenAI(model=CHAT_MODEL, base_url=NEBIUS_BASE_URL,
                      api_key=os.environ["NEBIUS_API_KEY"], temperature=0,
                      timeout=60, max_retries=2)


def get_store(namespace: str):
    """A LangChain view of one Pinecone namespace: add chunks, search chunks."""
    from langchain_pinecone import PineconeVectorStore
    return PineconeVectorStore(index_name=INDEX_NAME, embedding=get_embeddings(), namespace=namespace)


REPORTS_DIR.mkdir(exist_ok=True)