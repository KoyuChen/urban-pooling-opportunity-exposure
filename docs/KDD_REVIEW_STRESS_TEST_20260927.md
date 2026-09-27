# KDD 2027 submission stress test

Date: 2026-09-27  
Evidence base: commit `2e9c096a762c4741b808335ebbe790ef19c7da6e`  
Gate: `PASS_KDD_NARRATIVE_STRESS_TEST_WITH_OPEN_IMPACT_RISK`

## Protocol

This is a fail-closed reviewer pre-mortem, not a new experiment. The criteria
are taken from the KDD 2027 Research Track call: technical merit, originality,
potential impact, execution, presentation, related work, reproducibility, and
ethical considerations. Each proposed response must already follow from a
frozen evidence object. A response that needs a new city, model, query, solver
status, or post-hoc outcome is forbidden in this gate.

Official criterion source (checked 2026-09-27):
<https://kdd2027.kdd.org/research-track-call-for-papers/>.

## Claim--evidence--reviewer-risk matrix

| Criterion | Defensible claim and frozen evidence | Likely reviewer objection | Evidence-neutral response now in the paper | Boundary that must remain |
|---|---|---|---|---|
| Technical merit | Exact-time fixed-root/fixed-span additive pricing has an integral LP; the global master remains integer. Theory audit checked 2,956 low-depth cases, 752 fixed-q cells, and 503,310 exposed-face cases with zero mismatch. | The paper uses established optimization tools and has no global hardness classification. | State the narrow local primitive, the exact-q gap, and the projection-to-frontier theorem; do not market branch-and-price itself as new. | General complexity, including fixed capacity two, remains open. Numerical closure is not exact arithmetic. |
| Originality | The object is a hidden temporal-event partition with one joint completion, positive-overlap connectivity, and simultaneous occupancy. The new conceptual separation is partition $\rightarrow$ selected-row projection $\rightarrow$ additive frontier. | This may look like uncertain linkage plus column generation. | Lead with the distinct feasible-world object and the three-layer theorem; explicitly concede that possible-world bounds, matching, total unimodularity, column generation, and branch-and-price are established. | Do not claim a new uncertain-aggregation semantics, generic matching theory, or exhaustive first-in-literature priority. |
| Potential impact | Candidate deletion creates 6.9--7.7% false certificates among apparently certified decisions; NYC has 125/126 witness-certified ambiguous cells. | The ordered-event model has no demonstrated public-data endpoint advantage: 0/48 declared comparisons move. | Present the public result as a mechanism-resolved null: 36/48 cells add only partitions, 4/48 also add projections, and no added projection reaches a declared endpoint. | Do not convert the null into model equivalence or an ordered-event advantage. A post-hoc public query is inadmissible. This is the largest residual acceptance risk. |
| Execution | Chicago completes 90/96 declared windows; 10,728/10,762 data-complete endpoint pairs are certified. The NYC support lattice closes 18/18 cells and its four dominant cells reduce pricing LPs 29.6% under the exact cache. | Denominators and incomplete transport may be hidden by high completion percentages. | Retain six Chicago ineligible windows, 34 unresolved Chicago endpoint pairs, 13 NYC transport-unresolved cells, and three NYC ineligible cells wherever relevant. | Timeout is never infeasible; these results do not establish city-scale closure. |
| Presentation | The paper fits eight main-text pages and now uses the same three-layer vocabulary in abstract, contributions, public results, discussion, and conclusion. | The prior abstract read as a list of datasets and counts; the core idea was hard to identify. | Put the object and partition/projection/frontier distinction before algorithms and datasets; group the public null with its mechanism. | Do not remove adverse denominators or compress away the difference between support, solver, and decision failures. |
| Related work | The primary-source positioning audit covers uncertain aggregation, constrained probabilistic similarity joins, interval formulations, and branch-and-price. | Aggregate bounds and constrained matching are already known. | Make the novelty the quantified temporal-event world, not aggregate bounds or the optimization toolbox. | Do not claim that aggregate queries over uncertain matching, candidate omission, or extremal bounds originate here. |
| Reproducibility | A clean checkout reconstructs 8 manuscript tables, 53 rows, and 345 cells; 25 derived artifacts reproduce byte for byte. Claim checks run in CI. | ATR raw data/witnesses and NYC row-level solves are not fully bundled. | State aggregate-replay closure separately from raw-row replay and keep source/manifest boundaries explicit. | Do not call the artifact unrestricted end-to-end reproduction. |
| Ethics | The release and artifact report aggregates, statuses, and hashes, not reconstructed partners, latent timestamps, or stable personal identities. | Event reconstruction could expose sensitive associations. | Keep the estimand aggregate and explicitly reject membership recovery, causal inference, socioeconomic attribution, and prevalence claims. | No individual endpoint assignments, inferred partners, or raw private witnesses are published. |

## Adversarial decision

The submission is technically defensible and unusually well guarded against
claim drift. Its strongest contribution is the combination of a distinct
temporal feasible-world object, conditional decision certificates, and the
partition--projection--frontier explanation of when richer latent structure
changes an aggregate answer.

The largest unresolved reviewer risk is **potential impact**, not numerical
correctness: the frozen public comparison gives an explained endpoint null,
not an ordered-event outcome advantage. No evidence-neutral rewrite can erase
that limit. The revised manuscript therefore treats the null as a diagnostic
result and keeps the advantage question open.

## Changes authorized by this gate

1. Rewrite the abstract around the three-layer object and theorem.
2. Make the first contribution and public-results paragraph use the same
   partition--projection--frontier vocabulary.
3. Replace generic “remaining empirical test” language with the precise open
   public-data advantage question.
4. Add CI guards for the mechanism counts and forbidden escalations.

No empirical number, solver certificate, denominator, model, or query changes.
