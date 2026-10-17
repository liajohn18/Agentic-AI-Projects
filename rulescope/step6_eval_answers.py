"""STEP 9 - EVALUATE ANSWERS: run the full pipeline on every test question and grade what the user would see.
Run:  uv run python step6_eval_answers.py          (about 8-10 minutes: one full RAG run per question)

Uses the production settings in common.py (article chunks + reranker + MIN_SCORE).

  Refusals       out-of-scope questions refused?  answerable questions NOT refused?
  Citation       does the answer cite the expected regulation + article?  (first citation / any citation)
  Correctness    does the answer state the key fact of the reference answer?  graded by an LLM judge:
                 correct / partial / wrong
  Grounding      every claim shown was quote-checked by code; we report how many claims validation
                 had to drop or repair (a measure of how often the model tried to say unsupported things)
  Latency        seconds per question, total and per stage

Results: reports/answer_eval.csv (every question) and the summary printed at the end.
"""
import csv
import statistics
import time

from pydantic import BaseModel, Field

from common import QUESTIONS_PATH, REPORTS_DIR, get_llm, load_jsonl
from step4_rag import answer
from step5_eval_retrieval import FAMILY, article_number, with_retry


class Grade(BaseModel):
    verdict: str = Field(description="One of: correct, partial, wrong.")
    reason: str = Field(description="One short sentence explaining the verdict.")


JUDGE = """You grade answers from a regulation assistant. Compare the ASSISTANT ANSWER with the REFERENCE ANSWER,
which was written from the regulation itself.
- correct: the assistant states the key fact(s) of the reference and says nothing that contradicts it.
- partial: the assistant is on the right topic but misses or blurs a key fact (a number, a deadline, a condition).
- wrong:   the assistant states something different from the reference, or answers a different question.
Extra correct details from the regulation are fine. Judge facts, not wording.

QUESTION: {question}
REFERENCE ANSWER: {reference}
ASSISTANT ANSWER:
{answer}"""


def cites(result: dict, q: dict, family: bool = False, first_only: bool = False) -> bool:
    expected_doc = FAMILY.get(q["expected_doc"], q["expected_doc"]) if family else q["expected_doc"]
    citations = result["citations"][:1] if first_only else result["citations"]
    for c in citations:
        doc = FAMILY.get(c["doc_id"], c["doc_id"]) if family else c["doc_id"]
        if doc == expected_doc and article_number(c["article"]) == article_number(q["expected_article"]):
            return True
    return False


def pct(values: list[bool]) -> str:
    return f"{100 * sum(values) / len(values):5.1f}%  ({sum(values)}/{len(values)})" if values else "  n/a"


if __name__ == "__main__":
    questions = load_jsonl(QUESTIONS_PATH)
    judge = get_llm().with_structured_output(Grade, method="function_calling")
    rows = []
    for q in questions:
        result = with_retry(answer, q["question"])
        row = {"id": q["id"], "type": q["type"], "question": q["question"], "should_refuse": q["should_refuse"],
               "refused": result["refused"], "refusal_reason": result["refusal_reason"],
               "expected": f"{q['expected_doc']} | {q['expected_article']}" if q["expected_doc"] else "",
               "cited": " ; ".join(f"{c['doc_id']} | {article_number(c['article'])}" for c in result["citations"]),
               "cite_first": "", "cite_any": "", "cite_any_family": "", "verdict": "", "judge_reason": "",
               "claims_written": len(result["claims"]),
               "claims_dropped": sum(n.startswith("dropped") for n in result["notes"]),
               "labels_repaired": sum(n.startswith("label repaired") for n in result["notes"]),
               "seconds": round(result["timings"]["total"], 1),
               "retrieve_s": round(result["timings"].get("retrieve", 0), 1),
               "rerank_s": round(result["timings"].get("rerank", 0), 1),
               "generate_s": round(result["timings"].get("generate", 0), 1),
               "answer": result["answer"]}

        if not q["should_refuse"] and not result["refused"]:
            row["cite_first"] = cites(result, q, first_only=True)
            row["cite_any"] = cites(result, q)
            row["cite_any_family"] = cites(result, q, family=True)
            grade = with_retry(judge.invoke, JUDGE.format(question=q["question"], reference=q["reference_answer"],
                                                           answer=result["answer"]))
            verdict = (grade.verdict.strip().lower() if grade else "wrong")
            row["verdict"] = verdict if verdict in ("correct", "partial", "wrong") else "wrong"
            row["judge_reason"] = grade.reason if grade else ""
        elif not q["should_refuse"]:
            row["verdict"] = "refused"                                  # an answerable question we wrongly refused

        rows.append(row)
        status = ("REFUSED " if result["refused"] else "answered") + (f" {row['verdict']:8s}" if row["verdict"] else "")
        print(f"{q['id']:4s} {status:18s} {row['seconds']:5.1f}s  {q['question'][:65]}")

    with open(REPORTS_DIR / "answer_eval.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys())
        w.writeheader()
        w.writerows(rows)

    # ---------- summary ----------
    answerable = [r for r in rows if not r["should_refuse"]]
    out_of_scope = [r for r in rows if r["should_refuse"]]
    answered = [r for r in answerable if not r["refused"]]
    verdicts = [r["verdict"] for r in answerable]

    print("\n=== Refusals ===")
    print(f"   out-of-scope correctly refused:      {pct([r['refused'] for r in out_of_scope])}")
    print(f"   answerable wrongly refused:          {pct([r['refused'] for r in answerable])}")
    for r in out_of_scope:
        print(f"      {r['id']} {'refused  (' + r['refusal_reason'] + ')' if r['refused'] else 'ANSWERED: ' + r['answer'][:70]}")

    print("\n=== Citations (answered questions) ===")
    print(f"   first citation = expected article:  {pct([r['cite_first'] for r in answered])}")
    print(f"   any citation   = expected article:  {pct([r['cite_any'] for r in answered])}")
    print(f"   any citation, twin documents allowed: {pct([r['cite_any_family'] for r in answered])}")

    print("\n=== Correctness (all answerable questions, LLM judge) ===")
    for v in ("correct", "partial", "wrong", "refused"):
        print(f"   {v:8s} {verdicts.count(v):3d}  ({100 * verdicts.count(v) / len(verdicts):.0f}%)")

    print("\n=== Grounding ===")
    written = sum(r["claims_written"] for r in rows)
    print(f"   claims written by the model:   {written}")
    print(f"   dropped by validation:         {sum(r['claims_dropped'] for r in rows)}  (no supporting quote found)")
    print(f"   labels repaired by validation: {sum(r['labels_repaired'] for r in rows)}")
    print("   every claim shown to a user has a quote verified against its cited source")

    print("\n=== Latency (answered questions) ===")
    secs = sorted(r["seconds"] for r in answered)
    if secs:
        print(f"   median {statistics.median(secs):.1f}s | slowest {secs[-1]:.1f}s | "
              f"median per stage: retrieve {statistics.median(r['retrieve_s'] for r in answered):.1f}s, "
              f"rerank {statistics.median(r['rerank_s'] for r in answered):.1f}s, "
              f"generate {statistics.median(r['generate_s'] for r in answered):.1f}s")
    print("\nSaved reports/answer_eval.csv - open it to read every answer and the judge's reason.")