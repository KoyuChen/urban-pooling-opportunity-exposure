# ATR DIAMOR local-degree-cap audit v1

Status: **PASS**.

This post-hoc mechanism audit asks whether the density shift observed under the
fixed 3 m/120 degree rule can be mitigated without sacrificing its pilot truth
coverage. Within that frozen support, each node retains its `k` nearest
incident edges and the undirected union is used. DIAMOR-1 alone selects the
smallest graph that preserves the fixed rule's 85/88 covered snapshots.

The selected cap is `k=2`. It preserves pilot coverage while reducing mean
candidate edges from 4.52 to 4.33. Frozen on DIAMOR-2, it also preserves the
fixed rule's 81/82 covered snapshots and reduces mean edges from 12.17 to 11.20:
80 of 998 edges, or 8.0%, are removed.

All 82 follow-up frontiers close exactly. The cap does not improve decision
yield: both fixed and capped graphs certify 29/246 threshold decisions and leave
217/246 ambiguous. No false certificate occurs at the evaluated thresholds.

This is a negative result for the simple density-control mechanism. The removed
high-degree edges are irrelevant to these endpoint decisions; ambiguity is
sustained by structural alternative matchings that survive the cap. The audit
does not validate data-dependent support learning, and the zero false-certificate
count is threshold-specific. Labels still determine eligibility, the pilot
coverage constraint, oracle cardinality, and evaluation; DIAMOR-2 is not a
pristine holdout.

