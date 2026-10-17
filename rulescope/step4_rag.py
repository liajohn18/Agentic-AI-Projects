"""STEP 4 - RAG: answer a question from the regulations, with checked article citations.
Run:  uv run python step4_rag.py                       (runs the demo questions at the bottom)
Used by step 6 (evaluation) and app.py through:  answer(question)

The pipeline, as a LangGraph workflow:

  retrieve  -> fetch the 20 chunks closest in meaning to the question (Pinecone)
  gate      -> if even the best chunk is not close enough, refuse instead of guessing
  rerank    -> a second model re-reads those 20 and keeps the 5 that really answer the question
  generate  -> the LLM writes the answer as short claims; each claim names its source and quotes it
  validate  -> code (not the LLM) checks every quote is really in the cited chunk; fixes or drops claims

Nothing reaches the user unless code has checked it against the regulation text.
"""
import re
import time
from typing import TypedDict

from langgraph.graph import END, StateGraph
from pydantic import BaseModel, Field
from rapidfuzz import fuzz

from common import (CANDIDATES, DOC_BY_ID, MIN_SCORE, REFUSAL, STRATEGY, TOP_K, USE_RERANKER,
                    get_llm, get_store, norm, rerank)

MIN_QUOTE_CHARS = 15            # a quote shorter than this proves nothing
QUOTE_MATCH = 90                # 0-100: how closely a quote must match the source (100 = exact; allows tiny slips)

# Who a regulation protects. The SME regulation covers businesses; the consumer protection
# regulation and standards cover individual consumers. Their wording is nearly identical, so a
# retail question must never be answered from SME rules, or the other way round.
SME_ONLY = {"sme_customer_protection_regulation"}
CONSUMER_ONLY = {"consumer_protection_regulation", "consumer_protection_standards"}
SME_WORDS = re.compile(r"\b(smes?|small and medium|business(es)?|compan(y|ies)|enterprises?|corporate)\b", re.IGNORECASE)


# ---------- what the LLM must return (structured output) ----------
class Claim(BaseModel):
    statement: str = Field(description="One fact that answers part of the question, in plain English.")
    source: str = Field(description="The label of the source that supports it, e.g. 'S2'.")
    quote: str = Field(description="Words copied exactly from that source that prove the statement (one sentence or less).")


class Answer(BaseModel):
    claims: list[Claim] = Field(description="The facts that answer the question. Empty if the sources do not answer it.")


SYSTEM = """You answer questions about UAE Central Bank consumer-protection regulations, using ONLY the numbered sources given.
Rules:
- Answer the exact question first. Prefer sources that state the rule itself over definitions.
- Every claim must be supported by ONE source. Give that source's label and copy a quote from it
  character for character (do not reword or shorten words inside the quote).
- Never use outside knowledge. If the sources do not answer the question, return no claims.
- Keep regulations apart: SME rules are not retail-consumer rules; a Standard is not the Regulation it supports.
- Explain what the rules say. Do not give personal legal advice or tell the user what they should do.
- Be concise: at most 5 claims."""


# ---------- the state that flows through the graph ----------
class State(TypedDict, total=False):
    question: str
    strategy: str
    doc_ids: list[str] | None          # optional filter: only search these regulations
    audience: str                      # "sme" or "consumer" - decides which regulations may answer
    use_reranker: bool
    candidates: list[dict]             # the 20 retrieved chunks, with similarity scores
    sources: list[dict]                # the 5 chunks given to the LLM, labelled S1..S5
    claims: list[dict]                 # what the LLM wrote
    final_claims: list[dict]           # what survived validation
    refused: bool
    refusal_reason: str
    notes: list[str]                   # what validation repaired or dropped (shown in the X-Ray tab)
    timings: dict


def where(meta: dict) -> str:
    """'Consumer Protection Standards, Article 2: ... > 2.1.3 Key Facts Statement'"""
    place = meta["article"] + (f" > {meta['section']}" if meta.get("section") else "")
    return f"{meta['title']}, {place}"


# ---------- the nodes ----------
def search_filter(question: str, doc_ids: list[str] | None) -> tuple[str, dict]:
    """Audience guard: SME questions never see consumer-only rules, and consumer questions never see SME rules."""
    audience = "sme" if SME_WORDS.search(question) else "consumer"
    excluded = CONSUMER_ONLY if audience == "sme" else SME_ONLY
    if doc_ids:                                                        # the user picked regulations in the app
        return audience, {"doc_id": {"$in": [d for d in doc_ids if d not in excluded]}}
    return audience, {"doc_id": {"$nin": sorted(excluded)}}


def retrieve_node(state: State) -> State:
    start = time.time()
    audience, flt = search_filter(state["question"], state.get("doc_ids"))
    results = get_store(state["strategy"]).similarity_search_with_score(
        state["question"], k=CANDIDATES, filter=flt)
    candidates = [{"text": doc.page_content, "meta": doc.metadata, "similarity": float(score)}
                  for doc, score in results]
    return {"candidates": candidates, "audience": audience, "timings": {"retrieve": time.time() - start}}


def gate_node(state: State) -> State:
    best = max((c["similarity"] for c in state["candidates"]), default=0.0)
    if best < MIN_SCORE:
        return {"refused": True, "refusal_reason": f"best similarity {best:.2f} is below {MIN_SCORE}"}
    return {"refused": False}


def rerank_node(state: State) -> State:
    start = time.time()
    candidates = state["candidates"]
    if state["use_reranker"]:
        order = rerank(state["question"], [c["text"] for c in candidates], top_n=TOP_K)
        picked = [dict(candidates[i], rerank_score=score) for i, score in order]
    else:
        picked = candidates[:TOP_K]                                    # already sorted by similarity
    sources = [dict(c, label=f"S{n}") for n, c in enumerate(picked, start=1)]
    return {"sources": sources, "timings": {**state["timings"], "rerank": time.time() - start}}


def generate_node(state: State) -> State:
    start = time.time()
    context = "\n\n".join(f"[{s['label']}] {where(s['meta'])}\n{s['text']}" for s in state["sources"])
    llm = get_llm().with_structured_output(Answer, method="function_calling")
    result = llm.invoke([("system", SYSTEM),
                         ("human", f"Sources:\n\n{context}\n\nQuestion: {state['question']}")])
    claims = [c.model_dump() for c in result.claims] if result else []
    return {"claims": claims, "timings": {**state["timings"], "generate": time.time() - start}}


def clean_quote(text: str) -> str:
    text = text.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    return norm(text).strip(" .\"'…")


def quote_match(quote: str, text: str) -> float:
    """100 if the quote is in the text exactly; otherwise how closely its best-matching stretch matches (0-100).
    Allows tiny slips (a curly apostrophe, a missing 'the') but never a different number:
    '3 days' must not match '1 days', so every number in the quote must also be in the text."""
    if quote in text:
        return 100.0
    if not set(re.findall(r"\d+(?:\.\d+)*", quote)) <= set(re.findall(r"\d+(?:\.\d+)*", text)):
        return 0.0
    return fuzz.partial_ratio(quote, text)


def validate_node(state: State) -> State:
    """Keep a claim only if its quote is really in a source. If the quote is in a different source than
    the one the LLM named, correct the label (FinePrint lesson: models sometimes swap labels)."""
    by_label = {s["label"]: clean_quote(s["text"]) for s in state["sources"]}
    final, notes, seen = [], [], []
    for claim in state["claims"]:
        quote = clean_quote(claim["quote"])
        if len(quote) < MIN_QUOTE_CHARS:
            notes.append(f"dropped (quote too short): {claim['statement'][:60]}")
            continue
        named = claim["source"].strip().strip("[]").upper()
        scores = {lab: quote_match(quote, text) for lab, text in by_label.items()}
        best = max(scores, key=lambda lab: (scores[lab], lab == named)) if scores else None   # ties go to the named source
        if best is None or scores[best] < QUOTE_MATCH:
            notes.append(f"dropped (quote not found in any source): {claim['statement'][:60]}")
            continue
        label = named if scores.get(named, 0) == scores[best] else best
        if label != named:
            notes.append(f"label repaired {named} -> {label}: {claim['statement'][:60]}")
        if scores[label] < 100:
            notes.append(f"quote matched approximately ({scores[label]:.0f}/100): {claim['statement'][:60]}")
        statement = norm(claim["statement"])
        if any(fuzz.token_set_ratio(statement, earlier) >= 90 for earlier in seen):   # FinePrint lesson: duplicates
            notes.append(f"dropped (repeats an earlier claim): {claim['statement'][:60]}")
            continue
        seen.append(statement)
        final.append({**claim, "source": label, "match": scores[label]})

    if not final:
        return {"final_claims": [], "notes": notes, "refused": True,
                "refusal_reason": "no claim could be verified against the sources"}
    return {"final_claims": final, "notes": notes}


# ---------- the graph ----------
def build_graph():
    graph = StateGraph(State)
    graph.add_node("retrieve", retrieve_node)
    graph.add_node("gate", gate_node)
    graph.add_node("rerank", rerank_node)
    graph.add_node("generate", generate_node)
    graph.add_node("validate", validate_node)
    graph.set_entry_point("retrieve")
    graph.add_edge("retrieve", "gate")
    graph.add_conditional_edges("gate", lambda s: "stop" if s["refused"] else "go", {"stop": END, "go": "rerank"})
    graph.add_edge("rerank", "generate")
    graph.add_edge("generate", "validate")
    graph.add_edge("validate", END)
    return graph.compile()


GRAPH = build_graph()


def answer(question: str, strategy: str = STRATEGY, use_reranker: bool = USE_RERANKER,
           doc_ids: list[str] | None = None) -> dict:
    """Run the whole pipeline. Returns the answer text, its citations, and everything needed for the X-Ray tab."""
    start = time.time()
    state = GRAPH.invoke({"question": question, "strategy": strategy, "use_reranker": use_reranker,
                          "doc_ids": doc_ids, "notes": []})
    labels = {s["label"]: s for s in state.get("sources", [])}

    if state.get("refused"):
        text, citations = REFUSAL, []
    else:
        cited = []                                                     # number sources in order of first use
        for c in state["final_claims"]:
            if c["source"] not in cited:
                cited.append(c["source"])
        lines = [f"- {c['statement']} [{cited.index(c['source']) + 1}]" for c in state["final_claims"]]
        text = "\n".join(lines)
        citations = []
        for n, label in enumerate(cited, start=1):
            meta = labels[label]["meta"]
            citations.append({"n": n, "where": where(meta), "doc_id": meta["doc_id"], "article": meta["article"],
                              "reference": meta.get("reference", ""), "page_url": meta.get("page_url", ""),
                              "chunk_id": meta["chunk_id"],
                              "quotes": [c["quote"] for c in state["final_claims"] if c["source"] == label]})

    return {"question": question, "answer": text, "citations": citations, "audience": state.get("audience", ""),
            "refused": bool(state.get("refused")), "refusal_reason": state.get("refusal_reason", ""),
            "candidates": state.get("candidates", []), "sources": state.get("sources", []),
            "claims": state.get("claims", []), "notes": state.get("notes", []),
            "timings": {**state.get("timings", {}), "total": time.time() - start}}


if __name__ == "__main__":
    DEMO = [
        "When must a bank give a customer the Key Facts Statement?",                  # retail consumer protection
        "What must a bank disclose to an SME before it signs a facility agreement?",  # look-alike: SME, not retail
        "When does a bank account become dormant?",                                   # dormant accounts
        "What hours are banks allowed to make telemarketing calls?",                  # telemarketing
        "Which UAE bank has the best credit card rewards?",                           # out of scope -> refuse
    ]
    for q in DEMO:
        r = answer(q)
        top = r["candidates"][0]["similarity"] if r["candidates"] else 0
        print("=" * 100)
        print(f"Q: {q}\n   audience {r['audience']} | best similarity {top:.3f} | {r['timings']['total']:.1f}s"
              + (f" | REFUSED: {r['refusal_reason']}" if r["refused"] else ""))
        print(r["answer"])
        for c in r["citations"]:
            print(f"   [{c['n']}] {c['where']}  ({c['chunk_id']})")
        for note in r["notes"]:
            print(f"   note: {note}")