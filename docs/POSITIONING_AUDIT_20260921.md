# Closest-prior-work positioning audit

Status: **PASS_SHARP_POSITIONING_WITH_OPEN_PRIORITY_CLAIMS**.  Audited on
2026-09-21 against the primary papers and publisher/proceedings records linked
below.  This document records an object-level comparison; it is not a claim of
exhaustive bibliographic priority.

## One-sentence niche

EventFrontier computes conditional aggregate ranges over **hidden temporal-event
partitions** whose blocks must admit one joint timestamp completion, connected
positive overlap, and bounded simultaneous occupancy; it does not infer one
matching, one clustering, or one most likely event world.

## Novelty matrix

| Line | Latent world / constraint | Output | Already established | EventFrontier's narrower difference |
|---|---|---|---|---|
| Resolution-aware and probabilistic record linkage | Alternative entity resolutions or constrained one-to-one / one-to-many / many-to-many links | Aggregate bounds or distributions | Possible-world aggregation, matching constraints, and uncertainty propagation | A world is a partition into temporal events, not a set of bipartite links |
| Aggregate ranges over integrated data | Candidate-constrained one-to-many matching; truth coverage depends on candidate recall | Minimum and maximum aggregate answers | Extremal aggregation, matching-based algorithms, and candidate false-negative sensitivity | Event feasibility requires a single joint time completion and cannot be checked link by link |
| Consistent query answering and attribute uncertainty | Tuple repairs or bounded attribute values | Consistent extrema or propagated bounds | Range semantics over admissible database worlds | The admissible-world family couples partition membership, time, connectivity, and instantaneous capacity |
| Fixed-interval scheduling and decomposition | Partition fixed jobs into schedules in which overlapping jobs cannot share a machine | Cost-optimal schedules; column generation and branch-and-price | Consecutive-ones/TU arguments, pricing, decomposition, and branch-and-price | Our event columns require overlap connectivity while limiting its depth; overlap is connective evidence rather than a conflict |
| Ride-pooling and group inference | Predicted or optimized assignments, or proxy groups | A selected allocation, prediction, or descriptive network | Mobility applications and point reconstructions | We bound retrospective aggregates over every declared feasible event world and do not recover realized assignments |

The closest comparison is therefore not “bounds versus point estimates.”  Bounds
under linkage uncertainty already exist.  The defendable change is **which
possible worlds are legal**: variable-cardinality event blocks, a shared temporal
completion, connectivity by positive overlap, and capacity applied to
simultaneous occupancy rather than total membership.

## Claims the paper must not make

- Possible-world or extremal aggregate answering is new.
- Candidate omission or truth-in-support is a new issue.
- Matching reductions, total unimodularity, column generation, or
  branch-and-price are new techniques.
- EventFrontier recovers actual memberships, estimates their posterior, or
  identifies population prevalence.
- The full event-partition problem is polynomial, NP-hard, or city-scale; the
  current manuscript establishes none of those global statements.
- Public data currently demonstrate a practical advantage of ordered events
  over pair or clique models; the frozen fixed-input comparison is 0/24.

## Claims supported at the current evidence level

1. **Object/formulation.** The paper formalizes conditional identification when
   rows are complete only relative to a declared candidate universe but their
   temporal-event partition and timestamps are not.
2. **Structural distinction.** Pairwise compatibility and outer time envelopes
   need not imply a jointly realizable event; sequential membership can exceed
   instantaneous capacity.
3. **Local algorithmic result.** For exact intervals, fixed root and span, and
   additive row weights, segment coverage and boundary bridges yield an
   integral single-event pricing LP.  The global event-partition master can
   remain fractional.
4. **Audit architecture.** Solver validity, truth-in-support, and decision
   informativeness are tested separately; candidate deletion can manufacture
   apparently precise but false certificates in controlled truth.

## Primary sources checked

- Sismanis et al., *Resolution-Aware Query Answering for Business
  Intelligence*, ICDE 2009, [DOI](https://doi.org/10.1109/ICDE.2009.81).
- Hua and Pei, *Aggregate Queries on Probabilistic Record Linkages*, EDBT 2012,
  [open proceedings](https://openproceedings.org/2012/conf/edbt/HuaP12.pdf).
- Chen et al., *Aggregate Queries on Constrained Probabilistic Similarity Join
  Pairs*, Information Sciences 2019,
  [DOI](https://doi.org/10.1016/j.ins.2019.04.023).
- Sadinle, *Bayesian Estimation of Bipartite Matchings for Record Linkage*, JASA
  2017, [DOI](https://doi.org/10.1080/01621459.2016.1148612).
- Turkcapar and Krishnan, *Quantifying Uncertainty in Aggregate Queries over
  Integrated Datasets*, 2023, [arXiv](https://arxiv.org/abs/2309.05178).
- Amezian El Khalfioui and Wijsen, *Computing Range Consistent Answers to
  Aggregation Queries via Rewriting*, PACMMOD 2024,
  [DOI](https://doi.org/10.1145/3695836).
- Feng et al., *Efficient Uncertainty Tracking for Complex Queries with
  Attribute-Level Bounds*, SIGMOD 2021,
  [DOI](https://doi.org/10.1145/3448016.3452791).
- Muir and Toriello, *Interval Scheduling with Economies of Scale*, Computers &
  Operations Research 2023,
  [DOI](https://doi.org/10.1016/j.cor.2022.106056).
- Santi et al., *Quantifying the Benefits of Vehicle Pooling with Shareability
  Networks*, PNAS 2014,
  [DOI](https://doi.org/10.1073/pnas.1403657111).
- Alonso-Mora et al., *On-Demand High-Capacity Ride-Sharing via Dynamic
  Trip--Vehicle Assignment*, PNAS 2017,
  [DOI](https://doi.org/10.1073/pnas.1611675114).
- Taiebat et al., *Sharing Behavior in Ride-Hailing Trips: A Machine Learning
  Inference Approach*, Transportation Research Part D 2022,
  [DOI](https://doi.org/10.1016/j.trd.2021.103166).

## Submission wording adopted

The title now names the distinct object directly: **“Aggregate Identification
over Hidden Temporal-Event Partitions.”**  The abstract opens by distinguishing
that object from uncertain linkages and database repairs.  Related work states
explicitly that possible-world aggregation, extremal bounds, matching
constraints, candidate omission, TU, and branch-and-price are inherited ideas.
This leaves the novelty claim deliberately narrow and falsifiable.
