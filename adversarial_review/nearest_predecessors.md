# Nearest-Predecessor Audit

## Residual novelty verdict

The original frozen Chicago paper does not introduce min/max aggregate answers over feasible
linkages, uncertain-linkage propagation, multiple-instance scoring,
budget-constrained matching, missing-network bounds, mobility exposure, or
Chicago pooling analysis individually. Its defensible residual difference is much
narrower:

> Within one privacy-coarsened trip table that does not publish partner or group
> identity, a verified, internally consistent, boundary-complete
> `Shared Trip Match = true, Trips Pooled = 2` cohort induces a nonbipartite
> hidden perfect matching. Conditional on the declared candidate graph
> containing the true edges, the proposed output is a min/max range of a
> pair-context functional rather than one proxy graph.

That frozen contribution was an application/structure specialization. The
post-audit KDD pivot now adds a narrower algorithmic increment: an implemented
exact temporal-frontier dynamic program for compiled matching, latent-label,
threshold-release, omitted-edge-budget, and score-floor constraints; a
pathwidth-two weak-NP-completeness boundary for the score-aware endpoint
problem; and a certified outward score relaxation. These results are not a
claim that generic frontier dynamic programming, bounded-width CSP, budgeted
matching, or matching-level conformal prediction is new. Their remaining
increment is the particular compiled state, correctness invariant, witness
recovery, and audited release-coupled endpoint interface. The explicit-DNF
compiler and temporal-locality certificate are enabling components, not
standalone novelty claims. Current documentation supports Chicago's high-level
rule; implementation/null causes and production schedules remain unverified.

## Citation-grade comparison matrix

| Proposed claim | Nearest primary predecessor | Exact overlap | Exact remaining difference | Claim disposition |
|---|---|---|---|---|
| Min/max aggregate over candidate-consistent links | Turkcapar & Krishnan, [*Quantifying Uncertainty in Aggregate Queries over Integrated Datasets*](https://arxiv.org/abs/2309.05178) | Candidate-link graph, matching constraints, aggregate extrema, false-positive widening, and loss of coverage from false negatives | Their linkage is two-table bipartite; under the boundary-complete `K=2` and candidate-support assumptions, Chicago uses a within-file nonbipartite exact cover and an SES pair functional | Application specialization, not a new range-query principle |
| Aggregate uncertainty over compatible record linkages | Hua & Pei, EDBT 2012, [doi:10.1145/2247596.2247639](https://doi.org/10.1145/2247596.2247639) | Compatible possible linkages and downstream aggregate queries | They return probabilistic answer distributions rather than worst-case endpoints | Cannot claim linkage-to-aggregate propagation as new |
| Uncertain attributes through relational queries | Feng et al., SIGMOD 2021, [doi:10.1145/3448016.3452791](https://doi.org/10.1145/3448016.3452791) | Compact under-/over-approximations to certain and possible query answers; attribute annotations include value bounds | AU-DB answers are not generally exact/sharp and do not jointly solve fine geography and perfect matching under Chicago's operator | Suppression-aware exact structure may remain distinct |
| Narrowest aggregate range over repaired databases | Flesca, Furfaro & Parisi, [doi:10.1007/978-3-642-15951-0_19](https://doi.org/10.1007/978-3-642-15951-0_19) | Min/max aggregate answers across every admissible repair/world | Different repair semantics and constraints | “Range over feasible worlds” is established prior art |
| Hard aggregate bounds with missing or withheld rows | Liang et al., [doi:10.1145/3318464.3389785](https://doi.org/10.1145/3318464.3389785) | Contingency ranges for aggregate queries under formal, possibly overlapping constraints on missing tuples | Their uncertainty is missing rows under predicate constraints, not an unpublished within-file partner relation | Hard bounds under declared missing-data constraints are established prior art |
| Range-consistent aggregation across database repairs | Amezian El Khalfioui & Wijsen, [doi:10.1145/3695836](https://doi.org/10.1145/3695836) | Extremal aggregate answers over primary-key repairs and their query-complexity structure | Different repair semantics; no hidden perfect matching or Chicago observation operator | A modern database-theory predecessor for range semantics |
| Multiple imputation using potential matches | Goldstein, Harron & Wade, [doi:10.1002/sim.5508](https://doi.org/10.1002/sim.5508) | Propagates match-weight information through multiple imputation rather than selecting one deterministic match | Model-based multiple imputation; not worst-case enumeration of globally compatible exact covers | One-graph avoidance is not new by itself |
| Bayesian propagation of linkage uncertainty | Sadinle's globally constrained bipartite linkage model, [JASA 2017](https://doi.org/10.1080/01621459.2016.1148612), and linkage-averaged population-size estimation, [doi:10.1214/18-AOAS1178](https://doi.org/10.1214/18-AOAS1178) | A posterior over global linkage structure and downstream propagation of linkage uncertainty | Bayesian linkage averaging rather than an assumption-indexed endpoint range | Must acknowledge both global linkage and downstream-propagation predecessors |
| Positive-bag / noisy-OR-style weak supervision | Maron & Lozano-Pérez, [*A Framework for Multiple-Instance Learning*](https://proceedings.neurips.cc/paper/1997/hash/82965d4ed8150294d4330ace00821d77-Abstract.html) | A positive bag contains at least one positive instance; instance labels need not be observed | The Chicago node bags overlap through shared candidate edges and must also satisfy a matching constraint | Node-level OR supervision is established; coherence across overlapping bags remains unresolved |
| Joint linkage and causal/regression inference | Guha, Reiter & Mercatanti, [doi:10.1214/21-BA1297](https://doi.org/10.1214/21-BA1297); Steorts, Tancredi & Liseo, [doi:10.1007/978-3-319-99771-1_20](https://doi.org/10.1007/978-3-319-99771-1_20) | Downstream causal effects or regression while linkage is latent | Bayesian bipartite linkage, not worst-case DDD under a suppressed within-file relation | Coefficient propagation is not categorically new |
| Aggregate query utility after anonymization | Zhang et al., ICDE 2007, [doi:10.1109/ICDE.2007.367857](https://doi.org/10.1109/ICDE.2007.367857) | Aggregate-query utility under permutation-based anonymization, compared with generalization | It does not study suppression or optimize over a hidden matching/geography feasible set | Privacy-coarsening motivation needs a narrower claim |
| Chicago tract suppression and complete-case bias | Mucci & Erhardt, [doi:10.32866/001c.34191](https://doi.org/10.32866/001c.34191) | Legacy 2018–2020 data; documents selective suppression and bias in low-density/lower-income contexts; its authors describe a tract-pair rule | Does not reconstruct partners or bound pair exposure; its characterization cannot establish the 2025/2026 operator | Indispensable domain predecessor, but operator claims must come from version-specific official documentation |
| Bounds on assortativity/mixing under constraints | Cinelli et al., [doi:10.1103/PhysRevE.102.062310](https://doi.org/10.1103/PhysRevE.102.062310) | Extremal binary assortativity under degree-distribution, full-topology, and metadata-proportion regimes | Their feasible spaces vary graph configurations and/or binary metadata under prescribed degree, topology, and proportion constraints; they do not impose a latent exact-cover/perfect-matching relation or suppression-constrained geography | Blocks broad “first extremal mixing” claims |
| Bounds with missing links | Thirkettle, 2019 working paper, [*Identification and Estimation of Network Statistics with Missing Link Data*](https://matthewthirkettle.github.io/files/Thirkettle_Identification_Missing_Links.pdf) | Worst-case bounds and a tractable outer approximation under a structural network-formation model | Not two-transaction exact covers; working-paper status should remain explicit | Partial-network framing is established |
| Partial identification with interval data | Manski & Tamer, [doi:10.1111/1468-0262.00294](https://doi.org/10.1111/1468-0262.00294) | Regression objects with interval/coarsened outcomes or regressors | Does not exploit matching structure | Merely bounding a coefficient is not a novelty claim |
| Inference for identified-set endpoints | Imbens & Manski, [doi:10.1111/j.1468-0262.2004.00555.x](https://doi.org/10.1111/j.1468-0262.2004.00555.x); Kaido, Molinari & Stoye, [doi:10.3982/ECTA14075](https://doi.org/10.3982/ECTA14075) | Establishes that endpoint/projection confidence regions require explicit coverage theory | Their procedures do not automatically apply to this discrete matching estimator; the manuscript proves no such theory for its proposed bootstrap | Sampling inference is an open requirement, not an appendix detail |
| Trip shareability graph and matching | Santi et al., PNAS 2014, [doi:10.1073/pnas.1403657111](https://doi.org/10.1073/pnas.1403657111) | Spatiotemporal compatibility graph and pooled-trip matching | Counterfactual pooling with request data, not recovery of a suppressed realized partner | Candidate graph is not itself new |
| Socioeconomic mobility mixing/exposure | Moro et al., [doi:10.1038/s41467-021-24899-8](https://doi.org/10.1038/s41467-021-24899-8); Nilforoshan et al., [doi:10.1038/s41586-023-06757-3](https://doi.org/10.1038/s41586-023-06757-3) | Neighborhood-income proxies and mobility-derived visitation or colocation exposure networks | Their exposure structures are inferred from mobility traces, not a verified two-transaction ride partner | Use a narrow contextual-composition term, not a broad new exposure construct |
| Chicago pooled demand and socioeconomic geography | Soria & Stathopoulos, [doi:10.1016/j.jtrangeo.2021.103148](https://doi.org/10.1016/j.jtrangeo.2021.103148); Dean & Kockelman, [doi:10.1016/j.jtrangeo.2020.102944](https://doi.org/10.1016/j.jtrangeo.2020.102944) | Same data family, shared-versus-solo use, neighborhood disadvantage, and spatial variation | Origin demand rather than pairwise partner composition | No claim to first connect Chicago pooling and SES geography |
| Proxy grouping of hidden Chicago trip groups | Sebti & Chen, [doi:10.1007/s42421-026-00149-5](https://doi.org/10.1007/s42421-026-00149-5) | Chicago TNC data spanning 2024 through April 2025, DBSCAN potential groups, match classifiers, actual partners absent | This project would report endpoint ranges instead of one proxy grouping | Clearest empirical comparator; must be run on the same production window |
| Chicago sharing and successful-match inference | Mucci & Erhardt, [doi:10.1177/03611981231173636](https://doi.org/10.1177/03611981231173636), with [corrigendum](https://doi.org/10.1177/03611981241284953); Taiebat, Amini & Xu, [doi:10.1016/j.trd.2021.103166](https://doi.org/10.1016/j.trd.2021.103166) | Chicago trip-level sharing choice, successful matching, travel time, cost, and predictive inference | They do not bound which matched transaction was paired with which other transaction | Blocks novelty claims based only on predicting authorization or successful match |
| Matching with a side budget | Berger et al., [doi:10.1007/s10107-009-0307-4](https://doi.org/10.1007/s10107-009-0307-4) | Maximum-weight matching with an additional budget constraint; hardness and approximation machinery | The current score-floor exact cover is an application of a related side-constrained matching structure, not a new general algorithm | Do not claim score-floor optimization as algorithmic novelty without a distinct result |
| EPTAS for budgeted matching | Doron-Arad, Kulik & Shachnai, [doi:10.4230/LIPIcs.ICALP.2023.49](https://doi.org/10.4230/LIPIcs.ICALP.2023.49) | An EPTAS for budgeted matching and budgeted matroid intersection | The outward rounding result here is a bicriteria feasible-set certificate with query containment, not a generic approximation scheme for budgeted matching | Do not call the relaxation a PTAS/FPTAS or claim approximation novelty |
| Structured conformal prediction with matching outputs | Cauchois et al., [JMLR 2024](https://jmlr.org/papers/v25/23-0253.html) | Conformal predictive inference under weak supervision, including perfect-matching structured outputs and matching-oracle implementations | This paper freezes one reference score range across a candidate-omission sensitivity path and uses calibration only as a safety layer for a release-coupled world optimizer | Matching-level conformalization is prior art; the optimizer, not conformal prediction, is the candidate increment |
| Bounded-width CSP and bucket elimination | Freuder, [AAAI 1990](https://cdn.aaai.org/AAAI/1990/AAAI90-001.pdf); Dechter, [doi:10.1016/S0004-3702(99)00059-4](https://doi.org/10.1016/S0004-3702(99)00059-4) | Exact inference by elimination with complexity exponential in compiled induced width | The temporal algorithm exposes a release-specific live state and a pseudo-polynomial score coordinate; generic bounded-width inference itself is not new | State and prove only the compiled temporal specialization and its audit boundary |
| Vertex separation and pathwidth | Kinnersley, [doi:10.1016/0020-0190(92)90234-M](https://doi.org/10.1016/0020-0190(92)90234-M) | Vertex-separation number equals pathwidth | Chronological candidate-window density gives a data-measurable bound for this compiler's supplied order | Useful production certificate, not a new graph-width theorem |
| Boolean/OBDD knowledge compilation | Amarilli et al., [doi:10.1007/s00224-019-09930-2](https://doi.org/10.1007/s00224-019-09930-2); Sinz, [doi:10.1007/11564751_73](https://doi.org/10.1007/11564751_73) | Width-sensitive circuit-to-OBDD compilation and compact sequential cardinality counters | A schedule-aligned release monitor could avoid some DNF expansions, but compact formulas can still have exponential residual width | Explicit-DNF compilation is an auditable interface, not a general knowledge-compilation novelty |
| Rainbow matching on low-width graphs | Le & Pfender, [doi:10.1016/j.tcs.2013.12.013](https://doi.org/10.1016/j.tcs.2013.12.013) | Global color constraints can remain hard even on path-like underlying graphs | Confirms that width must be measured after release/resource factors are compiled, not on the raw candidate graph | Blocks any raw-candidate-pathwidth tractability claim |
| Chicago shared-trip tax effects | Zheng et al., [doi:10.1016/j.tra.2023.103639](https://doi.org/10.1016/j.tra.2023.103639); Abkarian et al., [doi:10.1177/03611981221098665](https://doi.org/10.1177/03611981221098665) | Chicago tax natural experiments, shared-trip shares/counts, spatial effects | A possible difference is hidden partner composition and a 2026 policy change, conditional on independent verification of the operative law, dates, zones, and endpoint treatment | Another volume DDD is not novel |

## Operator correction

The current base-release metadata points to the City's
[privacy methodology](https://data.cityofchicago.org/stories/s/82d7-i4i2) as
the approach used in `6dvr-xwnh`; it documents the current at-most-two-trip
threshold and paired endpoint coarsening. The companion
[City clarification](https://data.cityofchicago.org/stories/s/28mt-8asw),
whose footer lists legacy dataset IDs,
defines separate pickup `(rounded start time, pickup tract)` and drop-off
`(rounded end time, drop-off tract)` buckets. Both tract fields are removed if
either assigned endpoint bucket contains fewer than three trips. It does not
define an OD-tract-pair threshold. Together these are documentary support for
the current high-level rule, not independent validation of the transformation
code or a converse explanation for every blank tract.

If verified for the target release, this paired-removal rule creates subtler
coupling than a capacity-two OD label:
a suppressed row may belong to a large pickup bucket and a small drop-off
bucket, while visible row counts need not equal the latent bucket totals.

## Exact reductions that limit two proposed contributions

### Fixed block policy ranges

If the manuscript declares independent block sets \(\mathcal F_c\), fixed
weights \(a_c\), and

\[
L_c=\min_{M\in\mathcal F_c}H(M),\qquad
U_c=\max_{M\in\mathcal F_c}H(M),
\]

then the exact contrast endpoints are simply

\[
\underline\theta=\sum_{a_c\ge0}a_cL_c+\sum_{a_c<0}a_cU_c,
\qquad
\overline\theta=\sum_{a_c\ge0}a_cU_c+\sum_{a_c<0}a_cL_c.
\]

Calling this a global coupled optimization overstates the contribution. A
genuinely global matching matters only when edges cross blocks or when latent
geography changes treatment, sample membership, denominators, or design
weights. With fixed design, membership, denominators, an additive edge-linear
coefficient, and no further global constraints, the coefficient reduces to
signed min/max-weight perfect matching.

### Independent missing-bin supports

If missing node \(i\) has an independent allowed set \(\mathcal B_i\), define

\[
g^-_{ij}=\min_{b_i\in\mathcal B_i,b_j\in\mathcal B_j}1\{b_i=b_j\},
\qquad
g^+_{ij}=\max_{b_i\in\mathcal B_i,b_j\in\mathcal B_j}1\{b_i=b_j\}.
\]

With independent Cartesian node supports, every node used exactly once, and a
fixed graph, population, and denominator with no cross-node count or
suppression constraint, the joint matching/label endpoints are ordinary
weighted perfect matchings using \(g^-\) and \(g^+\). Thus independent
missing-label completion is a useful correctness repair, but not a standalone
algorithmic contribution.

## Post-audit residual contribution and remaining gates

A defensible current methodological claim is:

> Exact and certified-outward aggregate-query frontiers for a declared temporal
> feasible-world model that jointly represents hidden matchings, latent labels,
> threshold-release constraints, candidate omissions, and a calibrated score
> floor.

The reference implementation, exact small-instance oracle, weak-hardness
construction, and outward-containment audit now support that algorithmic claim
conditionally. The explicit-DNF LOW/HIGH release compiler, bounded capacity profile, UCI block-1
boundary audit, and FEBRL4 method-fit test are now implemented. They do not yet
support a Chicago scientific or production-scale claim. Before submission, the
project must still (i) validate City implementation/null causes and construct a
run-closed temporal order from real data, (ii) benchmark runtime/frontier size
on complete snapshots, (iii) finish the all-ten-block UCI audit and candidate
eligibility evidence, and (iv) compare against generic MILP, independent-label
envelopes, single imputation, and proxy grouping under the same world set.
