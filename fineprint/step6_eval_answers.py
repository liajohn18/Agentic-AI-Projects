"""STEP 6 - EVALUATE ANSWERS: run every question through the full workflow, then score it.
Run:  uv run python step6_eval_answers.py

Our own checks (plain Python):  grounded rate, correct refusals, rejected citations, latency
RAGAS (an LLM acts as judge):   faithfulness, answer relevancy, context precision, context recall
"""
import csv
import statistics

from common import REPORTS_DIR, QUESTIONS_PATH, get_embeddings, get_llm, load_jsonl
from step4_rag import GROUNDED, INSUFFICIENT, ask

LATENCY_TARGET_S = 8.0          # decided before running


def run_questions():
    rows = []
    for q in load_jsonl(QUESTIONS_PATH):
        out = ask(q["question"])
        rows.append({"id": q["id"], "answerable": bool(q["answer_phrase"]), "question": q["question"],
                     "reference": q["reference"], "state": out["state"], "answer": out["answer"],
                     "contexts": [h["text"] for h in out["hits"]], "rejected": len(out.get("rejected", [])),
                     "seconds": round(out["seconds"], 2)})
        print(f"{q['id']}  {out['state']:22s} {out['seconds']:.1f}s")
    return rows


def ragas_scores(rows):
    """RAGAS judges the answerable questions that got a grounded answer."""
    from ragas import EvaluationDataset, evaluate
    from ragas.embeddings import LangchainEmbeddingsWrapper
    from ragas.llms import LangchainLLMWrapper
    from ragas.metrics import Faithfulness, LLMContextPrecisionWithReference, LLMContextRecall, ResponseRelevancy

    judged = [r for r in rows if r["answerable"] and r["state"] == GROUNDED]
    if not judged:
        return {}, []
    dataset = EvaluationDataset.from_list([
        {"user_input": r["question"], "retrieved_contexts": r["contexts"], "response": r["answer"],
         "reference": r["reference"]} for r in judged])
    result = evaluate(dataset=dataset,
                      metrics=[Faithfulness(), ResponseRelevancy(), LLMContextPrecisionWithReference(), LLMContextRecall()],
                      llm=LangchainLLMWrapper(get_llm()), embeddings=LangchainEmbeddingsWrapper(get_embeddings()))
    table = result.to_pandas()
    metric_cols = [c for c in table.columns if c not in ("user_input", "retrieved_contexts", "response", "reference")]
    per_question = [{"id": r["id"], **{c: table.iloc[i][c] for c in metric_cols}} for i, r in enumerate(judged)]
    averages = {c: float(table[c].mean()) for c in metric_cols}
    return averages, per_question


if __name__ == "__main__":
    rows = run_questions()
    answerable = [r for r in rows if r["answerable"]]
    traps = [r for r in rows if not r["answerable"]]
    seconds = sorted(r["seconds"] for r in rows)
    p95 = seconds[max(0, round(0.95 * len(seconds)) - 1)]

    with open(REPORTS_DIR / "answers.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=[k for k in rows[0] if k != "contexts"], extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    print("Saved reports/answers.csv. Now running RAGAS...")

    averages, per_question = ragas_scores(rows)
    if per_question:
        with open(REPORTS_DIR / "ragas_scores.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=per_question[0].keys())
            w.writeheader()
            w.writerows(per_question)

    lines = ["| Measure | Result |", "|---|---:|",
             f"| Answerable questions answered (Grounded) | {sum(r['state'] == GROUNDED for r in answerable)}/{len(answerable)} |",
             f"| Unanswerable questions refused | {sum(r['state'] == INSUFFICIENT for r in traps)}/{len(traps)} |",
             f"| Citations rejected by the check | {sum(r['rejected'] for r in rows)} |",
             f"| Latency median / p95 | {statistics.median(seconds):.1f}s / {p95:.1f}s |",
             f"| Latency target (p95 < {LATENCY_TARGET_S:.0f}s) | {'MET' if p95 < LATENCY_TARGET_S else 'NOT MET'} |"]
    lines += [f"| RAGAS {name} | {value:.3f} |" for name, value in averages.items()]
    report = "\n".join(lines)
    (REPORTS_DIR / "answers.md").write_text("# Answer evaluation\n\n" + report + "\n", encoding="utf-8")
    print("\n" + report)