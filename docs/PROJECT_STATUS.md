# Verified project status

Checkpoint: 2026-09-05. This status distinguishes checked-in evidence from planned work.

## Frozen manuscript

The manuscript/evidence baseline is commit `10108d088f8b70efc1d8d5c483690e385546ceea`.
It includes the NYC 24-window panel (21 eligible; 126 outcome-capacity cells),
14/18 closed branch-and-price scale cells, and Chicago release-operator run 164
(60 core rows, 611 candidates, 50,405 contributors). NYC point-method disagreement
is not an error rate against observed membership truth.

## Remote exploration

Branch: `explore-selective-disclosure-20260904`.
Last verified checkpoint before the current implementation work:
`74c0fc25fc26a9199e290dc34a7f5838bc151ca4`.

Checked-in controlled results:

- 9,000 usage-threshold comparisons; 5,954 initially ambiguous; mean ex-post
  minimum decision certificate 1.5574 facts. This is not adaptive query cost.
- 272/300 ambiguous event-count instances after conditioning on complete row
  usage; minimum pair certificate mean 2.0147 facts.
- Complete-column constraint generation agrees with the explicit small oracle
  in 900 usage cells and 90 pair cells. The separation tolerance is 1e-6.
- Decision-versus-recovery certificate comparisons and all-partition family
  code are on the exploration branch, not in the manuscript.

## Not completed at this checkpoint

- Implicit branch-and-price separation with fixed support and truthful audit
  answers (the next implementation target).
- External real event-membership truth, email-Eu learned-linkage validation,
  and real sequential-episode truth. Earlier conversational claims that these
  were committed are unsupported by the current repository and are withdrawn.
- Noise-robust audit guarantees and operational availability/cost of queries.
- Selective-disclosure integration into the paper.

## Evidence policy

A successful old CI run is not a new experiment. Record new source commits,
actual test outcomes, numerical tolerances, unresolved cases, and artifact
provenance before changing this status. Never certify absence of an opposite
world using only a feasible incumbent or a solver success flag.
