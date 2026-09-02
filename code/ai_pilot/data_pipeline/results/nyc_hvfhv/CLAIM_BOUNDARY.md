# NYC HVFHV claim boundary

## Supported

- The public HVFHV releases contain shared-match flags, second-level
  pickup/drop-off timestamps, Taxi Zones, and trip outcomes, but no public
  co-rider key, shared-run key, or realized pool size in the audited schema.
- Candidate multiplicity under provider/time overlap is large even at exact
  second-level resolution.
- Conditional on declared `C in {2,3,4}`, feasible worlds may be represented as
  connected positive-overlap interval runs with simultaneous occupancy bounded
  by `C`; total run membership may exceed `C` through sequential turnover.
- Within a fixed time-support model, capacity relaxation is nested and the
  reported common-support endpoint audits obey the implied monotonicity.
- A correct coarse-time partial-identification world uses an existential latent
  timestamp completion inside each declared support. Exact singleton supports
  are contained in the artificial coarse supports.
- Complete fixed-time run-column enumeration provides exact feasibility and
  infeasibility certificates for the frozen 16-row audit cohorts.
- In the base audit cohort, artificial time support expands reachable support
  at low `C`; at fixed feasible support counts `q=4,6,8`, compared outcome
  endpoint pairs coincide.
- In six predeclared purposive audit windows, artificial time support has a
  positive certified support-gain lower bound at both `C=2` and `C=3` in every
  window. The six-window aggregate audit passes.
- Unresolved coarse counts are retained as unresolved and never converted to
  infeasibility. Same-zone restrictions remain analyst sensitivity screens.

## Not supported

- Actual co-rider, vehicle, or shared-run reconstruction.
- Hidden-run closure or partner recall outside the declared candidate universe.
- Any assertion that a public NYC shared trip had realized pool size or
  occupancy two, three, four, or another value.
- Interpreting declared `C` as an estimate of the platform's true vehicle
  capacity.
- TLC production matching logic or provider implementation fidelity.
- Treating the artificial nearest-15-minute timestamp supports as TLC's actual
  release operator.
- A universal statement that timestamp uncertainty equals exactly one capacity
  step. The observed substitution magnitude is heterogeneous across audit
  windows.
- Interpreting `C=4` panel saturation as structural: the audit has only twelve
  candidate buffers and is right-censored at that ceiling.
- NYC population prevalence, sampling inference, causal effects, policy
  effects, or validation of provider-submitted records beyond the public
  release.

## Current model boundary

Chicago remains the public known-`K=2` matching benchmark. NYC is the
unknown-capacity ordered-run extension. The strongest current NYC result is a
conditional, release-support-indexed statement:

> Under an artificial existential timestamp-support experiment, reachable
> latent-run membership expands at low simultaneous capacity in every one of
> six predeclared purposive audit windows, while the capacity-equivalent
> magnitude varies with local temporal structure.

This is a feasible-world possibility result, not evidence that any particular
latent world occurred.
