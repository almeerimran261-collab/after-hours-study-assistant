# Public retrieval development benchmark

Retrieval only on a fixed synthetic development set; no answer, citation, or refusal accuracy scores.

Corpus: 40 authored PDF pages; questions: 40.
Dataset SHA256: `b47262d32ced21cd039518a5385384bc14d6a3463a10c117648e7df361800559`

| Pipeline | Hit@1 | Hit@5 | MRR@5 | Mean ms | p95 ms |
| --- | ---: | ---: | ---: | ---: | ---: |
| vector_only | 90.0% | 100.0% | 0.944 | 44.4 | 62.3 |
| hybrid_reranked | 92.5% | 100.0% | 0.956 | 602.6 | 759.7 |

Hit@k is the fraction of questions with the labeled page in the first k results.
MRR@5 averages reciprocal labeled-page rank; misses contribute zero.
Each question has one labeled page. The source PDFs are included in notes/.
Scores use exact labeled pages; other returned pages may still contain useful information.
This small authored set is for development checks; it does not establish performance on unseen courses.
No retriever settings were tuned during this run. Corpus preparation is outside the retrieval timing.
Model IDs, resolved revisions where available, and package versions are recorded in summary.json.
