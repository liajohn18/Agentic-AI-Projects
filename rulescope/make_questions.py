"""STEP 7 - QUESTIONS: build the test set used by steps 8 and 9.
Run in two stages:

  uv run python make_questions.py              1. DRAFT: the LLM writes ~30 questions, each from one known article
                                                  -> eval/questions_review.csv   (open it in Excel and review)
  uv run python make_questions.py --finalize   2. FINALIZE: your reviewed rows -> eval/questions.jsonl (frozen)

Why each question comes from ONE chunk: we then know the right answer's regulation and article,
so step 8 can measure whether retrieval finds it (Precision@1, MRR, article accuracy).

The review CSV also contains 15 starter rows for YOUR hand-written questions (type = lookalike,
out_of_scope, advice, cross_regulation). These are the hard cases an LLM would not think of.
"""
import csv
import random
import sys
from collections import defaultdict

from pydantic import BaseModel, Field

from common import CHUNKS_DIR, DOC_BY_ID, QUESTIONS_PATH, get_llm, load_jsonl, save_jsonl

REVIEW_PATH = QUESTIONS_PATH.parent / "questions_review.csv"
TARGET = 30                       # generated questions
PER_DOC_MIN, PER_DOC_MAX = 2, 4   # every regulation is tested; no regulation dominates
MIN_CHUNK_CHARS = 600             # skip short scraps
SKIP_ARTICLES = ("Preamble", "Definitions", "Interpretation", "Publication", "Cancellation", "Conflict")
COLUMNS = ["id", "keep", "type", "question", "expected_doc", "expected_article", "expected_section",
           "should_refuse", "reference_answer", "quote", "source_chunk_id"]


class Draft(BaseModel):
    answerable: bool = Field(description="False if the passage contains no clear rule a person could ask about.")
    question: str = Field(description="One question a bank customer or compliance analyst would ask.")
    answer: str = Field(description="The answer, in one or two sentences, using only the passage.")
    quote: str = Field(description="Words copied exactly from the passage that contain the answer.")


PROMPT = """You write test questions for a search assistant over UAE Central Bank regulations.
From the passage below, write ONE question that a bank customer or a compliance analyst might really ask,
which this passage alone answers.
- Use everyday wording. Do not copy distinctive phrases from the passage.
- Do not mention article numbers, section numbers, or "the passage".
- Ask about a concrete rule (a deadline, a duty, a limit, a right), not a definition.
- If the passage has no clear rule (a list of contents, a form, a fragment), set answerable to false.

Regulation: {title}
Passage:
{text}"""

# Starter rows for the hand-written questions. Fill expected_doc / expected_article yourself:
# search data/clean/<doc_id>.md (Ctrl+F) to find the article that answers it.
HANDWRITTEN = [
    ("lookalike", "As an individual customer, how many days do I have to cancel a personal loan after signing?", "no"),
    ("lookalike", "As a small business owner, what must my bank tell me before I sign a business loan?", "no"),
    ("lookalike", "Does the bank have to give my company a Key Facts Statement?", "no"),
    ("lookalike", "What fees can a bank charge me for closing my personal current account?", "no"),
    ("cross_regulation", "If my complaint to the bank is not resolved, where can I escalate it?", "no"),
    ("cross_regulation", "Can a bank call me about a credit card offer if I never gave consent?", "no"),
    ("cross_regulation", "What happens to the money in my account if I stop using it for years?", "no"),
    ("advice", "Should I sue my bank for charging me a late fee?", "no"),
    ("advice", "Which loan should I take, a personal loan or a credit card?", "no"),
    ("out_of_scope", "Which UAE bank offers the highest savings interest rate right now?", "yes"),
    ("out_of_scope", "What is the VAT rate in the UAE?", "yes"),
    ("out_of_scope", "How do I apply for a UAE golden visa?", "yes"),
    ("out_of_scope", "What is Emirates NBD's share price?", "yes"),
    ("out_of_scope", "Write me a poem about banking.", "yes"),
    ("out_of_scope", "What are the anti-money laundering rules for crypto exchanges in Dubai (VARA)?", "yes"),
]


def pick_chunks(chunks: list[dict]) -> list[dict]:
    """A fair sample: 2-4 chunks per regulation, in proportion to its size, from rule-bearing articles."""
    random.seed(42)                                            # same sample every run
    by_doc = defaultdict(list)
    for c in chunks:
        if len(c["text"]) >= MIN_CHUNK_CHARS and not any(w in c["article"] for w in SKIP_ARTICLES):
            by_doc[c["doc_id"]].append(c)
    total = sum(len(v) for v in by_doc.values())
    picked = {}
    for doc_id, items in by_doc.items():
        quota = max(PER_DOC_MIN, min(PER_DOC_MAX, round(TARGET * len(items) / total)))
        random.shuffle(items)
        picked[doc_id] = items                                 # shuffled; we use the first `quota` that work
        picked[doc_id + "#quota"] = quota
    return picked


def draft() -> None:
    chunks = load_jsonl(CHUNKS_DIR / "chunks_article.jsonl")
    pool = pick_chunks(chunks)
    llm = get_llm().with_structured_output(Draft, method="function_calling")
    rows, n = [], 0
    for doc_id in DOC_BY_ID:
        items, quota, made, used_articles = pool.get(doc_id, []), pool.get(doc_id + "#quota", 0), 0, set()
        for chunk in items:
            if made >= quota:
                break
            if chunk["article"] in used_articles:              # spread questions across different articles
                continue
            body = chunk["text"].split("\n", 1)[-1]            # without the [Title | Article] context line
            result = llm.invoke(PROMPT.format(title=DOC_BY_ID[doc_id]["title"], text=body))
            if not result or not result.answerable or not result.question.strip():
                continue
            n += 1
            made += 1
            used_articles.add(chunk["article"])
            rows.append({"id": f"G{n:02d}", "keep": "yes", "type": "generated", "question": result.question.strip(),
                         "expected_doc": doc_id, "expected_article": chunk["article"].split(":")[0],
                         "expected_section": chunk["section"], "should_refuse": "no",
                         "reference_answer": result.answer.strip(), "quote": result.quote.strip(),
                         "source_chunk_id": chunk["chunk_id"]})
            print(f"G{n:02d} {doc_id:36s} {chunk['article'][:30]:30s} {result.question[:70]}")

    for i, (kind, question, refuse) in enumerate(HANDWRITTEN, start=1):
        rows.append({"id": f"H{i:02d}", "keep": "todo", "type": kind, "question": question,
                     "expected_doc": "", "expected_article": "", "expected_section": "", "should_refuse": refuse,
                     "reference_answer": "", "quote": "", "source_chunk_id": ""})

    QUESTIONS_PATH.parent.mkdir(exist_ok=True)
    with open(REVIEW_PATH, "w", newline="", encoding="utf-8-sig") as f:   # utf-8-sig: Excel shows ’ and – correctly
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(rows)
    print(f"\n{n} generated + {len(HANDWRITTEN)} hand-written starters -> {REVIEW_PATH.relative_to(QUESTIONS_PATH.parents[1])}")
    print("Review it in Excel, then run:  uv run python make_questions.py --finalize")


def finalize() -> None:
    with open(REVIEW_PATH, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    final, problems = [], []
    for r in rows:
        keep = r["keep"].strip().lower()
        if keep == "no":
            continue
        if keep != "yes":
            problems.append(f"{r['id']}: keep is '{r['keep']}' - set it to yes or no")
            continue
        refuse = r["should_refuse"].strip().lower() == "yes"
        if not refuse and (r["expected_doc"] not in DOC_BY_ID or not r["expected_article"].startswith(("Article", "Section"))):
            problems.append(f"{r['id']}: needs a valid expected_doc and expected_article (e.g. 'Article 2')")
            continue
        final.append({"id": r["id"], "type": r["type"], "question": r["question"].strip(),
                      "expected_doc": r["expected_doc"] or None, "expected_article": r["expected_article"] or None,
                      "expected_section": r["expected_section"] or None, "should_refuse": refuse,
                      "reference_answer": r["reference_answer"], "source_chunk_id": r["source_chunk_id"] or None})
    if problems:
        print("Fix these rows in the CSV first:\n  " + "\n  ".join(problems))
        return
    save_jsonl(final, QUESTIONS_PATH)
    kinds = defaultdict(int)
    for q in final:
        kinds[q["type"]] += 1
    print(f"{len(final)} questions frozen -> eval/questions.jsonl  {dict(kinds)}")


if __name__ == "__main__":
    finalize() if "--finalize" in sys.argv else draft()