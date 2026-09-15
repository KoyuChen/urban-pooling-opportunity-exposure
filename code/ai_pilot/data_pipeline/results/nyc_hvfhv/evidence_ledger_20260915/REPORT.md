# NYC evidence and claim ledger

Overall status: **PASS_CLAIM_ALIGNMENT_WITH_GEOMETRY_HOLD**.

| Evidence object | Scientific question | Status | Certified / cells | Unresolved |
|---|---|---|---:|---:|
| `outcome_decision_panel` | What outcome ranges and threshold decisions are invariant over the declared feasible worlds? | `PASS_PANEL_WITH_UNRESOLVED_ENDPOINTS` | 101/126 | 25 |
| `support_maximization_lattice` | Can the branch-and-price implementation certify maximum selected-buffer support on the frozen nested-size cohort? | `PASS_INTEGER_SUPPORT` | 18/18 | 0 |
| `fixed_q_structure_comparator` | Do pair or clique restrictions change endpoints at common positive q on one fixed small input? | `PASS_VERIFIED_NULL` | 24/24 | 0 |
| `outcome_blind_geometry_census` | How often is a local non-clique event column available in the declared public candidate geometry? | `HOLD_TRANSPORT_INCOMPLETE` | 8/24 | 13 |

## Interpretation

The 18/18 support-maximization result does not close the decision panel's 25 numerically unresolved outcome endpoint pairs. Conversely, two-sided feasible witnesses certify 125/126 median-threshold decisions as ambiguous without requiring optimal endpoints. The 0/24 fixed-q structure result is a verified null on one small common-intersection input. The geometry census remains HOLD because 13/24 declared cells are transport-unresolved; its eight completed views establish only local column availability.

Historical timeouts remain in provenance and are never called infeasible. No object identifies realized memberships, population prevalence, production logic, or a city-scale guarantee.
