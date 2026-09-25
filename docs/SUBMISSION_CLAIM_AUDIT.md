# Submission claim-to-evidence audit

Status: **PASS_SUBMISSION_CLAIM_ALIGNMENT_WITH_OPEN_LIMITS**.

This ledger separates what each frozen evidence object supports from the
stronger interpretation it does not support. `scripts/audit_submission_claims.py`
recomputes the headline counts and fails CI if the manuscript wording drifts.

| Evidence object | Supported headline | Required boundary |
|---|---|---|
| Controlled truth | 3,000 instances; full-support point errors are flagged; six-of-eight truncation retains about 84% of members but only 31--33% of worlds and creates 6.9--7.7% false certificates among certified decisions | Synthetic-generator validation, not public truth coverage |
| ATR/DIAMOR dyads | Pilot-selected support retains 81/82 follow-up annotated worlds and certifies 29/246 decisions | One-coder, label-assisted reference; not city-rule validation or prevalence |
| Chicago K=2 | 90/96 windows complete, six ineligible; 10,728/10,762 data-complete endpoint pairs numerically certified and 34 unresolved | Purposive calendar, hidden partners unidentified, not exact-arithmetic or population inference |
| NYC outcome panel | 101/126 endpoint pairs numerically closed; 125/126 decisions witness-certified ambiguous | Conditional on the declared support; 25 endpoints remain unresolved |
| NYC structure comparator | 0/24 common-\(q\) comparisons change an endpoint | Honest null on one fixed complete-clique input, not evidence against the general model |
| NYC outcome-blind non-clique diagnostic | Ordered adds worlds versus clique in 1/24 common-feasible cells, but 0/48 ordered--clique endpoints change across two queries | Conditional four-window null; 13 geometry cells remain transport-unresolved; not model equivalence, accuracy, or prevalence |
| NYC endpoint-attainment mechanism | All 192 ordered endpoint--restriction checks have same-buffer-subset pair/clique witnesses; 36/48 restriction cells add partitions only and 4/48 add projected subsets | Existing windows, supports and queries only; explains the null but does not turn it into model equivalence or a public advantage claim |
| NYC geometry census | 8 complete, 3 ineligible, 13 transport-unresolved | Local columns are not complete worlds; prevalence remains unidentified |
| NYC support lattice | 18/18 integer brackets close under the numerical and witness-replay protocol | “Certified,” not exact arithmetic; separate from outcome closure and city scale |
| Pricing cache | Four dominant reconstructed cells preserve certificates and paths while actual LP calls fall 29.6% | Snapshot-consistent, not byte-identical; elapsed time is descriptive |

Global boundary: no result identifies realized memberships, population
prevalence, production logic, causal effects, or a city-scale runtime guarantee.
The general global complexity classification also remains open.
