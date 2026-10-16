"""STEP 5 - EVALUATE RETRIEVAL: which chunking strategy finds the answer-bearing chunk first?
Run:  uv run python step5_eval_retrieval.py

For each answerable question, find the rank of the first retrieved chunk that contains the answer phrase.
Precision@1 = share found at rank 1 | MRR = average of 1/rank | Hit@5 = share found in the top 5
"""
import csv
import statistics

from common import REPORTS_DIR, QUESTIONS_PATH, TOP_K, get_store, load_jsonl, norm

MIN_GAIN_POINTS = 5     # decided BEFORE running: heading must beat fixed by 5 points of Precision@1


def first_correct_rank(hits, phrase):
    for rank, (doc, _score) in enumerate(hits, start=1):
        if norm(phrase) in norm(doc.page_content):
            return rank
    return None


def summarize(ranks):
    n = len(ranks)
    return {"precision_at_1": sum(r == 1 for r in ranks) / n,
            "mrr": sum(1 / r for r in ranks if r) / n,
            "hit_at_5": sum(1 for r in ranks if r and r <= 5) / n}


if __name__ == "__main__":
    questions = [q for q in load_jsonl(QUESTIONS_PATH) if q["answer_phrase"]]
    rows, summary = [], {}
    for strategy in ("fixed", "heading"):
        store, ranks = get_store(strategy), []
        for q in questions:
            hits = store.similarity_search_with_score(q["question"], k=TOP_K)
            rank = first_correct_rank(hits, q["answer_phrase"])
            ranks.append(rank)
            rows.append({"strategy": strategy, "id": q["id"], "rank": rank or "",
                         "top_chunk": hits[0][0].metadata["chunk_id"], "top_score": round(hits[0][1], 4),
                         "top_section": hits[0][0].metadata["section"]})
        summary[strategy] = summarize(ranks)

    with open(REPORTS_DIR / "retrieval_details.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys())
        w.writeheader()
        w.writerows(rows)

    lines = ["| Strategy | Precision@1 | MRR | Hit@5 |", "|---|---:|---:|---:|"]
    for s, m in summary.items():
        lines.append(f"| {s} | {m['precision_at_1']:.1%} | {m['mrr']:.3f} | {m['hit_at_5']:.1%} |")
    gain = 100 * (summary["heading"]["precision_at_1"] - summary["fixed"]["precision_at_1"])
    verdict = "use heading-aware" if gain >= MIN_GAIN_POINTS else "keep fixed (heading-aware did not gain enough)"
    lines.append(f"\nHeading-aware minus fixed: {gain:+.1f} points of Precision@1 -> **{verdict}**.")

    # Threshold help: top scores of answerable questions vs the trap questions, for MIN_SCORE in common.py
    store = get_store("heading")
    answerable = [store.similarity_search_with_score(q["question"], k=1)[0][1] for q in questions]
    traps = [store.similarity_search_with_score(q["question"], k=1)[0][1]
             for q in load_jsonl(QUESTIONS_PATH) if not q["answer_phrase"]]
    lines.append(f"\nTop score, answerable questions: min {min(answerable):.3f}, median {statistics.median(answerable):.3f}")
    lines.append(f"Top score, unanswerable questions: max {max(traps):.3f}, median {statistics.median(traps):.3f}")
    lines.append("Set MIN_SCORE between these. If they overlap, the citation check is your main safeguard.")

    report = "\n".join(lines)
    (REPORTS_DIR / "retrieval.md").write_text("# Retrieval evaluation\n\n" + report + "\n", encoding="utf-8")
    print(report)