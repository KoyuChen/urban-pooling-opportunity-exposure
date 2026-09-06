# ATR DIAMOR cross-day multi-query audit v1

Status: **PASS**.

The edge scorer is trained on DIAMOR-1 only and frozen before evaluation on
DIAMOR-2. Candidate membership uses distance, heading, and speed only. Group
labels still determine eligibility, exclusions, oracle `q`, training labels,
and final evaluation. Headlines are therefore cross-day point-reconstruction
diagnostics, not deployment accuracy.

The model sees 663 training candidate edges, including 142 annotated positives.
On the 381 DIAMOR-2 cells where annotated truth is representable and endpoints
are exact, average relation recall is 89.62% for closest-distance, 81.96% for
the hand-built motion-affinity score, and 89.24% for the frozen learned score.

| Query | Closest-distance errors | Motion-affinity errors | Learned-score errors | Learned errors flagged |
|---|---:|---:|---:|---:|
| Mean distance | 32 | 111 | 44 | 44/44 |
| Mean speed gap | 44 | 128 | 70 | 70/70 |
| Mean heading gap | 38 | 39 | 35 | 35/35 |

Each denominator is 1,143 threshold decisions (381 cells times three fixed
thresholds). The same point matching is evaluated for all three queries; it is
not re-optimized to favor the query. The learned and distance rules have nearly
identical relation recall but materially different query-specific errors,
showing that edge recovery alone is not a sufficient downstream reliability
metric.

All conditional errors are frontier-ambiguous. As in the fixed-query audit,
this is a positive control implied by representable truth, not an unconditional
safety rate. The learned scorer is a transparent linear baseline, not a
state-of-the-art trajectory model.
