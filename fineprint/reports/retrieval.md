# Retrieval evaluation

| Strategy | Precision@1 | MRR | Hit@5 |
|---|---:|---:|---:|
| fixed | 83.3% | 0.903 | 100.0% |
| heading | 83.3% | 0.917 | 100.0% |

Heading-aware minus fixed: +0.0 points of Precision@1 -> **keep fixed (heading-aware did not gain enough)**.

Top score, answerable questions: min 0.631, median 0.715
Top score, unanswerable questions: max 0.672, median 0.664
Set MIN_SCORE between these. If they overlap, the citation check is your main safeguard.
