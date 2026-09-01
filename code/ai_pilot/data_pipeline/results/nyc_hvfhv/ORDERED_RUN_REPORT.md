# NYC HVFHV ordered latent-run frontier

Frozen evidence date: 2026-09-01 UTC  
Validated workflow: `33545170861`  
Artifact: `9815675232`  
Artifact digest: `sha256:7ecad13140f22f1aa83409d34eadfa32836995d973a2a1accb96fe90b8170506`  
Evidence commit: `89295584b589594c0b675014b5551201ac8c116b`

## Cohort and model

Source dataset: NYC Open Data `u253-aew4` (2023 High Volume FHV Trip Data).

The smoke cohort uses provider `HV0005`, core window `2023-01-03 17:45:00`--`18:00:00`, and an ordered subcore of 8 public shared-match rows inside a fixed determinate candidate universe of 437 rows.

A latent run is a connected positive-overlap interval subgraph. Capacity `C` restricts simultaneous occupancy on every elementary time segment; it does **not** cap total run cardinality. A run may therefore contain an `A-B-C` temporal chain even when `A` and `C` never overlap.

The compact segment formulation is exact for this declared interval-graph connectivity rule. It uses consecutive active elementary segments plus a positive-overlap bridge at each active boundary instead of edge-flow variables.

## Certified frontier

| Time model | C | Query | Lower | Upper | Width |
|---|---:|---|---:|---:|---:|
| exact second | 2 | run count / core | 0.5000 | 1.0000 | 0.5000 |
| exact second | 3 | run count / core | 0.3750 | 1.0000 | 0.6250 |
| exact second | 4 | run count / core | 0.2500 | 1.0000 | 0.7500 |
| 15-min outer | 2 | run count / core | 0.5000 | 1.0000 | 0.5000 |
| 15-min outer | 2 | selected buffer rows / core | 0.0000 | 9.0000 | 9.0000 |
| 15-min outer | 2 | companion mass / core | 0.5000 | 9.0000 | 8.5000 |
| 15-min outer | 3 | run count / core | 0.3750 | 1.0000 | 0.6250 |
| 15-min outer | 3 | selected buffer rows / core | 0.0000 | 14.1250 | 14.1250 |
| 15-min outer | 3 | companion mass / core | 0.5000 | 14.1250 | 13.6250 |
| 15-min outer | 4 | run count / core | 0.2500 | 1.0000 | 0.7500 |
| 15-min outer | 4 | selected buffer rows / core | 0.0000 | 18.5000 | 18.5000 |
| 15-min outer | 4 | companion mass / core | 0.5000 | 18.5000 | 18.0000 |

Capacity nesting audit: `PASS` over 8 adjacent certified comparisons.

The exact-second run-count endpoints are certified with zero MIP gap. Exact-second *upper* endpoints for selected-buffer and companion-mass objectives were not published: the 60-second-per-endpoint smoke limit produced either no incumbent or unresolved gaps for those maximization problems. Their minimization sides solved, but the report remains fail-closed and suppresses incomplete interval pairs.

## Identification geometry

Two features are already visible.

First, allowing larger simultaneous capacity widens the run-count identified set monotonically. The lower endpoint falls from `0.500` at `C=2` to `0.375` at `C=3` and `0.250` at `C=4`, while the upper endpoint remains `1.000`. Thus capacity uncertainty acts mainly through the possibility of consolidating core trips into fewer connected runs.

Second, under the deliberately coarse 15-minute outer-time model, chain-compatible buffer uncertainty grows much faster than the run-count range. The maximum selected-buffer mass rises from `9.0` to `14.125` to `18.5` rows per core as `C` increases from 2 to 4. This is not a statement about realized NYC pooling; it is the size of the public-data feasible set under the declared ordered-run model.

The contrast is useful: run-count uncertainty is moderate and structured, while latent membership can remain extremely weakly identified because a bounded-occupancy run may accumulate many sequential members over time.

## Computational geometry

The exact-second model has 846 elementary segments, 17,040 variables (10,272 binary), and 31,021 constraints. The 15-minute outer model has only 19 elementary segments, 3,808 variables (3,656 binary), and 4,557 constraints. Time coarsening therefore makes the graph denser but collapses the temporal state space enough to make the current MILP much easier.

This creates a nontrivial computational-identification tradeoff: more precise timestamps shrink the feasible linkage set but increase the number of elementary temporal states that an exact formulation must represent.

## Claim boundary

Supported: conditional structural endpoints for connected public-time interval runs in this fixed candidate universe under declared capacity `C`; exactness of the compact segment connectivity formulation for that declared rule; capacity-nesting comparisons among certified endpoints.

Not supported: actual vehicle/run recovery, co-rider identity, partner recall, true NYC pool size or vehicle capacity, production matching logic, or population/policy effects.
