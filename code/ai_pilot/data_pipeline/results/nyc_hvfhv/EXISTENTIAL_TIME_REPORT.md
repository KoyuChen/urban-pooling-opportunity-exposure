# NYC Gate F: existential timestamp completion and support reachability

Frozen evidence date: 2026-09-02 UTC

## Model correction

Directly replacing a trip by its full timestamp outer envelope is not a
monotone release relaxation: wider intervals can create overlap bridges but can
also create artificial simultaneous occupancy. Gate F instead uses the correct
existential quantifier. Each public row selects one latent pickup and drop-off
inside its released support, and ordered-run connectivity and capacity are
imposed on that selected completion.

The exact-time side is certified by complete enumeration of all feasible
unlabeled run columns on a fixed 16-row audit cohort (4 core and 12 candidate
buffers), followed by an exact disjoint-column master dynamic program. The
artificial coarse-time side is a continuous-time MILP with rooted overlap
connectivity and exact interval-graph C-coloring for simultaneous capacity.
The artificial supports are nearest-15-minute endpoints with +/-7.5-minute
independent supports; they are not asserted to be TLC's release mechanism.

## Support-cardinality frontier

| Capacity | Exact feasible selected-buffer counts | Largest exact count | Coarse existential certified counts | Newly certified by coarse support | Coarse unresolved |
|---:|---|---:|---|---|---|
| 2 | `0, 2, 4` | 4 | `0, 1, 2, 3, 4, 5, 6, 8` | `1, 3, 5, 6, 8` | `7, 9, 10, 11, 12` |
| 3 | `0--8` | 8 | `0--12` | `9, 10, 11, 12` | none |
| 4 | `0--12` | 12 | `0--12` | none | none |

For exact public timestamps, the largest feasible run column contains 2, 3,
and 4 members at C=2, 3, and 4, respectively. In this audit cohort, exact C=2
therefore collapses to pair columns and can select only 0, 2, or 4 buffers.
Under artificial coarse timestamp supports, a certified C=2 completion can
select 8 buffers. Thus the coarse C=2 world reaches the exact-time C=3 maximum
support count, while preserving simultaneous occupancy two in the replayed
witness. Counts above 8 at coarse C=2 remain unresolved rather than being
reported as infeasible.

## Outcome composition at common support

At four selected buffers (1/core), every exact and coarse cell for C=2,3,4 is
certified and has the same endpoint pair:

- mean selected-buffer miles: `9.26775--24.65800`;
- mean selected-buffer duration: `49.9500--83.6000` minutes.

At eight selected buffers (2/core), exact C=2 is proven infeasible by complete
run-column enumeration, whereas coarse existential C=2 is certified feasible.
For exact C=3/C=4 and coarse C=2/C=3/C=4, the endpoint pairs coincide:

- mean selected-buffer miles: `13.50125--21.196375`;
- mean selected-buffer duration: `60.6604--77.4854` minutes.

The first detectable timestamp-support effect in this cohort is therefore on
**support reachability**, not on composition conditional on a support count that
was already feasible. Artificial timestamp uncertainty admits higher-membership
sequential run worlds at low simultaneous capacity; once a common support count
is feasible, the same public-row outcome extremes can be attained here.

## Computational evidence

The exact fixed-time master enumerates 54, 394, and 1,719 feasible run columns
for C=2,3,4. Its reachable support masks are complete finite certificates. The
coarse existential frontier certifies every count at C=3 and C=4. At C=2, it
provides feasible replayed witnesses through count 8 but leaves five larger
counts unresolved under the declared time limit.

## Claim boundary

This Gate establishes only conditional feasible-world statements for one
predeclared small public-data audit cohort. It does not identify actual
co-riders, actual vehicle runs, realized capacity, provider matching logic, or
an NYC population effect. The 15-minute support experiment is artificial and
must not be described as the TLC observation operator. A certified feasible
coarse world proves possibility under the declared supports, not that such a
world occurred.
