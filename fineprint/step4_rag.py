"""STEP 4 - THE RAG WORKFLOW: retrieve -> decide -> generate -> check citations, as a small LangGraph.
Try it:  uv run python step4_rag.py "Is there a fee to open an account?"
"""
import sys
import time
from typing import TypedDict

from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field

from common import MIN_SCORE, REFUSAL, STRATEGY, TOP_K, get_llm, get_store, norm

GROUNDED, INSUFFICIENT = "GROUNDED", "INSUFFICIENT_EVIDENCE"


# --- 1. The shape the model must answer in (structured output) ---
class Claim(BaseModel):
    text: str = Field(description="One short factual statement that answers part of the question.")
    chunk_id: str = Field(description="The id of the evidence chunk that supports it, e.g. heading-012.")
    excerpt: str = Field(description="Words copied exactly from that chunk that prove the statement.")


class Answer(BaseModel):
    answerable: bool = Field(description="False if the evidence does not answer the question.")
    claims: list[Claim] = Field(default_factory=list)


PROMPT = ChatPromptTemplate.from_messages([
    ("system",
     "You explain a bank's Key Facts Statement to customers in plain English.\n"
     "Use ONLY the evidence chunks below. For every claim give the chunk_id and an excerpt copied word for word "
     "from that chunk. Copy amounts, rates and conditions exactly. Never use outside knowledge.\n"
     "If the evidence does not answer the question, set answerable to false and return no claims."),
    ("human", "Evidence:\n{evidence}\n\nQuestion: {question}"),
])


# --- 2. The state: everything the steps share ---
class State(TypedDict, total=False):
    question: str
    hits: list          # retrieved chunks: text, metadata, score
    claims: list        # claims that passed the citation check
    rejected: list      # claims that failed it
    state: str          # GROUNDED or INSUFFICIENT_EVIDENCE
    answer: str


# --- 3. The nodes: one small job each ---
def retrieve(s: State) -> State:
    results = get_store(STRATEGY).similarity_search_with_score(s["question"], k=TOP_K)
    hits = [{"text": d.page_content, **d.metadata, "score": float(score)} for d, score in results]
    return {"hits": hits}


def refuse(s: State) -> State:
    return {"state": INSUFFICIENT, "answer": REFUSAL, "claims": []}


def generate(s: State) -> State:
    evidence = "\n\n".join(f"[{h['chunk_id']}] (section: {h['section']})\n{h['text']}" for h in s["hits"])
    answer = (PROMPT | get_llm().with_structured_output(Answer, method="function_calling")).invoke(
        {"evidence": evidence, "question": s["question"]})
    return {"claims": [c.model_dump() for c in answer.claims] if answer.answerable else []}


def validate(s: State) -> State:
    """The application, not the model, decides which citations are real."""
    by_id = {h["chunk_id"]: h for h in s["hits"]}
    accepted, rejected, seen = [], [], set()
    for c in s["claims"]:
        hit = by_id.get(c["chunk_id"])
        if not (hit and norm(c["excerpt"]) in norm(hit["text"])):        # wrong chunk id?
            hit = next((h for h in s["hits"] if norm(c["excerpt"]) in norm(h["text"])), hit)   # find the real one
            c = {**c, "chunk_id": hit["chunk_id"]} if hit else c         # relabel it correctly
        if hit and len(norm(c["excerpt"])) >= 10 and norm(c["excerpt"]) in norm(hit["text"]):
            if norm(c["text"]) in seen:                                  # skip a duplicate claim
                continue
            seen.add(norm(c["text"]))
            accepted.append({**c, "section": hit["section"], "source": hit["title"], "url": hit["url"]})
        else:
            rejected.append(c)
    if not accepted:
        return {"state": INSUFFICIENT, "answer": REFUSAL, "claims": [], "rejected": rejected}
    answer = "\n".join(f"- {c['text']} [{i}]" for i, c in enumerate(accepted, start=1))
    return {"state": GROUNDED, "answer": answer, "claims": accepted, "rejected": rejected}


# --- 4. The decision after retrieval ---
def enough_evidence(s: State) -> str:
    return "generate" if s["hits"] and s["hits"][0]["score"] >= MIN_SCORE else "refuse"


# --- 5. Wire it together ---
def build():
    g = StateGraph(State)
    for name, fn in [("retrieve", retrieve), ("refuse", refuse), ("generate", generate), ("validate", validate)]:
        g.add_node(name, fn)
    g.add_edge(START, "retrieve")
    g.add_conditional_edges("retrieve", enough_evidence, {"generate": "generate", "refuse": "refuse"})
    g.add_edge("generate", "validate")
    g.add_edge("validate", END)
    g.add_edge("refuse", END)
    return g.compile()


GRAPH = None


def ask(question: str) -> dict:
    global GRAPH
    GRAPH = GRAPH or build()
    t0 = time.perf_counter()
    out = GRAPH.invoke({"question": question})
    out["seconds"] = time.perf_counter() - t0
    return out


if __name__ == "__main__":
    out = ask(sys.argv[1] if len(sys.argv) > 1 else "Is there a fee to open an account?")
    print(f"\n{out['state']} ({out['seconds']:.1f}s)\n\n{out['answer']}\n")
    for i, c in enumerate(out["claims"], start=1):
        print(f"[{i}] {c['section']} ({c['chunk_id']}): \"{c['excerpt']}\"")
    print("\nRetrieved:", [(h["chunk_id"], round(h["score"], 3)) for h in out["hits"]])