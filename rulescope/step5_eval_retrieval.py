"""STEP 8 - EVALUATE RETRIEVAL: does search find the right article? Four set-ups, same questions.
Run:  uv run python step5_eval_retrieval.py

                    no reranker        reranker
  fixed chunks          A                 B
  article chunks        C                 D

For every answerable question we know the right regulation and article (from eval/questions.jsonl).
A retrieved chunk is "correct" when it comes from that regulation AND that article.

  P@1       is the FIRST chunk correct?                       (what the user sees first)
  MRR       1 / position of the first correct chunk           (1.0 = first, 0.5 = second, 0.2 = fifth, 0 = not in top 5)
  Hit@5     is ANY of the 5 chunks given to the LLM correct?   (can the LLM answer at all?)
  Doc@1     is the first chunk at least from the right regulation?

"family" scores also accept the twin document at the same article
(Bank Loans Regulation <-> its Clarifications, Consumer Protection Regulation <-> its Standards).

Decision rules, fixed before seeing results:
  keep article chunking only if it beats fixed by >= 5 points of P@1
  keep the reranker      only if it beats no-reranker by >= 5 points of P@1

Out-of-scope questions are used to calibrate MIN_SCORE (the refusal gate).
"""
import csv
import statistics
import time

from common import CANDIDATES, MIN_SCORE, QUESTIONS_PATH, REPORTS_DIR, TOP_K, get_store, load_jsonl, rerank
from step4_rag import search_filter

STRATEGIES = ("fixed", "article")
FAMILY = {"bank_loans_clarifications": "bank_loans_regulation",
          "consumer_protection_standards": "consumer_protection_regulation"}
GAIN_NEEDED = 5.0                                              # percentage points


def article_number(label: str | None) -> str:
    """'Article 7: Responsible Financing' -> 'Article 7'"""
    return (label or "").split(":")[0].strip()


def is_correct(meta: dict, q: dict, family: bool = False) -> bool:
    doc, expected = meta["doc_id"], q["expected_doc"]
    if family:
        doc, expected = FAMILY.get(doc, doc), FAMILY.get(expected, expected)
    return doc == expected and article_number(meta["article"]) == article_number(q["expected_article"])


def rank_metrics(top: list[dict], q: dict, family: bool = False) -> tuple[float, float, float]:
    """P@1, reciprocal rank and Hit@5 for one question."""
    hits = [is_correct(c["meta"], q, family) for c in top]
    first = next((i for i, h in enumerate(hits, start=1) if h), None)
    return float(hits[0]) if hits else 0.0, (1 / first if first else 0.0), float(first is not None)


def with_retry(fn, *args, **kwargs):
    for attempt in range(3):                                   # free-tier rate limits: wait and try again
        try:
            return fn(*args, **kwargs)
        except Exception as error:
            if attempt == 2:
                raise
            print(f"   retrying after error: {str(error)[:80]}")
            time.sleep(5 * (attempt + 1))


if __name__ == "__main__":
    questions = load_jsonl(QUESTIONS_PATH)
    answerable = [q for q in questions if not q["should_refuse"]]
    out_of_scope = [q for q in questions if q["should_refuse"]]
    print(f"{len(answerable)} answerable + {len(out_of_scope)} out-of-scope questions\n")

    rows, best_scores = [], {"answerable": [], "out_of_scope": []}
    for strategy in STRATEGIES:
        store = get_store(strategy)
        for q in questions:
            # 1. Search once (20 candidates); both reranker settings reuse the same candidates -> a fair comparison.
            start = time.time()
            _, flt = search_filter(q["question"], None)
            results = with_retry(store.similarity_search_with_score, q["question"], k=CANDIDATES, filter=flt)
            candidates = [{"text": d.page_content, "meta": d.metadata, "similarity": float(s)} for d, s in results]
            search_time = time.time() - start
            best = max((c["similarity"] for c in candidates), default=0.0)
            if strategy == "article":                          # calibrate the gate on the production strategy
                best_scores["out_of_scope" if q["should_refuse"] else "answerable"].append((best, q["id"]))
            if q["should_refuse"]:
                continue

            # 2. Without the reranker: the top 5 by similarity.
            # 3. With the reranker: the 5 the reranker ranks highest among the 20.
            start = time.time()
            order = with_retry(rerank, q["question"], [c["text"] for c in candidates], top_n=TOP_K)
            rerank_time = time.time() - start
            setups = {"no": candidates[:TOP_K], "yes": [candidates[i] for i, _ in order]}

            for reranked, top in setups.items():
                p1, rr, hit5 = rank_metrics(top, q)
                fp1, frr, fhit5 = rank_metrics(top, q, family=True)
                rows.append({"strategy": strategy, "reranker": reranked, "id": q["id"], "type": q["type"],
                             "question": q["question"], "expected": f"{q['expected_doc']} | {q['expected_article']}",
                             "got_first": f"{top[0]['meta']['doc_id']} | {article_number(top[0]['meta']['article'])}" if top else "",
                             "p1": p1, "rr": rr, "hit5": hit5,
                             "doc1": float(bool(top) and top[0]["meta"]["doc_id"] == q["expected_doc"]),
                             "family_p1": fp1, "family_rr": frr, "family_hit5": fhit5,
                             "best_similarity": round(best, 3),
                             "seconds": round(search_time + (rerank_time if reranked == "yes" else 0), 2)})
            print(f"{strategy:7s} {q['id']}  no-rerank {'OK ' if setups['no'] and rows[-2]['p1'] else '-- '}"
                  f" rerank {'OK ' if rows[-1]['p1'] else '-- '} {q['question'][:60]}")
            time.sleep(0.3)                                    # be gentle with the free tier

    # ---------- per-question details ----------
    with open(REPORTS_DIR / "retrieval_eval.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys())
        w.writeheader()
        w.writerows(rows)

    # ---------- summary: the 2 x 2 table ----------
    summary = []
    for strategy in STRATEGIES:
        for reranked in ("no", "yes"):
            part = [r for r in rows if r["strategy"] == strategy and r["reranker"] == reranked]
            mean = lambda key: 100 * statistics.mean(r[key] for r in part)
            summary.append({"strategy": strategy, "reranker": reranked, "questions": len(part),
                            "P@1": round(mean("p1"), 1), "MRR": round(mean("rr") / 100, 3), "Hit@5": round(mean("hit5"), 1),
                            "Doc@1": round(mean("doc1"), 1), "family_P@1": round(mean("family_p1"), 1),
                            "family_Hit@5": round(mean("family_hit5"), 1),
                            "median_seconds": round(statistics.median(r["seconds"] for r in part), 2)})
    with open(REPORTS_DIR / "retrieval_summary.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=summary[0].keys())
        w.writeheader()
        w.writerows(summary)

    print(f"\n{'set-up':22s} {'P@1':>6s} {'MRR':>6s} {'Hit@5':>6s} {'Doc@1':>6s} {'famP@1':>7s} {'famHit5':>8s} {'sec':>5s}")
    for s in summary:
        name = f"{s['strategy']} + {'reranker' if s['reranker'] == 'yes' else 'no reranker'}"
        print(f"{name:22s} {s['P@1']:6.1f} {s['MRR']:6.3f} {s['Hit@5']:6.1f} {s['Doc@1']:6.1f} "
              f"{s['family_P@1']:7.1f} {s['family_Hit@5']:8.1f} {s['median_seconds']:5.2f}")

    # ---------- the two decisions ----------
    p1 = {(s["strategy"], s["reranker"]): s["P@1"] for s in summary}
    rerank_gain = statistics.mean([p1[(st, "yes")] - p1[(st, "no")] for st in STRATEGIES])
    article_gain = statistics.mean([p1[("article", r)] - p1[("fixed", r)] for r in ("no", "yes")])
    print(f"\nReranker gain:          {rerank_gain:+.1f} points of P@1 -> "
          f"{'KEEP (USE_RERANKER = True)' if rerank_gain >= GAIN_NEEDED else 'DROP (USE_RERANKER = False)'}")
    print(f"Article chunking gain:  {article_gain:+.1f} points of P@1 -> "
          f"{'KEEP (STRATEGY = article)' if article_gain >= GAIN_NEEDED else 'DROP (STRATEGY = fixed)'}")

    # ---------- calibrate the refusal gate ----------
    lowest_ok = min(best_scores["answerable"])
    highest_oos = max(best_scores["out_of_scope"]) if best_scores["out_of_scope"] else (0.0, "-")
    print(f"\nRefusal gate (best similarity, article chunks):")
    print(f"   answerable questions:   lowest {lowest_ok[0]:.3f} ({lowest_ok[1]})")
    print(f"   out-of-scope questions: highest {highest_oos[0]:.3f} ({highest_oos[1]})")
    for score, qid in sorted(best_scores["out_of_scope"], reverse=True):
        print(f"      {qid} {score:.3f} {'refused' if score < MIN_SCORE else 'NOT refused'} at MIN_SCORE {MIN_SCORE}")
    wrongly_refused = [qid for score, qid in best_scores["answerable"] if score < MIN_SCORE]
    print(f"   answerable questions wrongly refused at {MIN_SCORE}: {len(wrongly_refused)} {wrongly_refused}")
    if highest_oos[0] < lowest_ok[0]:
        print(f"   A clean gap: any MIN_SCORE between {highest_oos[0]:.2f} and {lowest_ok[0]:.2f} separates them; "
              f"the midpoint is {(highest_oos[0] + lowest_ok[0]) / 2:.2f}")
    else:
        print("   The two groups overlap: the gate alone cannot separate them (validation must catch the rest).")
    print("\nSaved reports/retrieval_eval.csv (every question) and reports/retrieval_summary.csv (the table).")