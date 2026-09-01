# Chicago K=2 boundary-padding sensitivity protocol

This protocol adds a released-time boundary-padding axis to the existing
Chicago K=2 public temporal candidate-universe frontier. It does **not** recover
`Shared Trip ID`, co-rider identity, vehicle identity, or complete hidden pooled
runs.

## Definition

Let the released start and end of row `i` be `s_hat[i]` and `e_hat[i]`. The
declared nearest-15-minute release model uses half-width `delta = 7.5` minutes,
so the outer occupancy interval is

```text
[s_hat[i] - delta, e_hat[i] + delta].
```

For a fixed 15-minute core `C`, define

```text
s_min = min_{i in C} s_hat[i],
e_max = max_{i in C} e_hat[i].
```

At padding `p >= 0`, retain every core row, every target row with an
indeterminate released start or end, and every determinate target row `j`
satisfying

```text
s_hat[j] <= e_max + p,
e_hat[j] >= s_min - p.
```

Only edges incident to at least one core row are materialized. The temporal
edge rule remains closed outer-interval intersection.

## Structural identities

For `p <= q`, the retained row and edge families are nested. Consequently, for
any fixed edge-additive query, the minimum feasible value is nonincreasing and
the maximum feasible value is nondecreasing as padding expands.

The complete public-temporal endpoint is

```text
p* = 2 delta = 15 minutes.
```

Any determinate row capable of intersecting a core outer interval must satisfy
the two `p*` retrieval inequalities. Therefore the `p*` graph equals the full
count-closed core-incident public temporal graph. Increasing `p` beyond `p*`
may retrieve additional rows, but none can add a core-incident temporal edge
under the declared model. The implementation therefore canonically reuses the
`p*` endpoint for `p > p*` and audits that identity.

Padding below 15 minutes is an intentional under-padding stress test. It is not
a closed support claim and has no partner-recall interpretation.

## Three sensitivity axes

The live report keeps three distinct nested families:

1. **Boundary padding `p`:** changes released-time retrieval support up to the
   complete endpoint `p = 15` minutes.
2. **Endpoint radius `r`:** conditionally restricts the complete temporal graph
   by released pickup/dropoff centroid distance; missing centroids are retained.
3. **Core-incidence budget `Gamma`:** permits an increasing number of selected
   core incidences on measured edges outside a fixed base radius. It is not a
   candidate-miss count or estimated miss rate.

None of the three axes is a hidden-partner compatibility rule.

## Local or server run

From the repository root:

```bash
bash scripts/run_chicago_k2_boundary_local.sh
```

The script creates an isolated `.venv-chicago-k2`, installs pinned numerical
dependencies, runs deterministic self-tests and unit tests, then executes the
live count-reconciled Socrata extraction. Aggregate artifacts are written to
`tmp/chicago-k2-frontier-boundary/`; raw rows, raw trip identifiers, and selected
matching witnesses are not written.

Useful overrides are environment variables, for example:

```bash
OUTPUT_DIR=/data/chicago-k2-boundary \
BOUNDARY_PADDING_MINUTES=0,5,10,15,30 \
SOLVER_TIME_LIMIT=120 \
SOCRATA_APP_TOKEN='...' \
bash scripts/run_chicago_k2_boundary_local.sh
```

Set `INSTALL_DEPS=0` to reuse an existing environment and `RUN_TESTS=0` only
after the same commit has already passed the deterministic suite.

## Interpretation boundary

A successful report establishes snapshot-relative count closure of a
core-incident **public temporal candidate universe** under the declared release
model and conditional optimization ranges over its graph families. It does not
establish recursive buffer-run closure, actual temporal overlap, true pooled
partners, two complete latent Chicago worlds, partner recall, or a
Chicago-population effect.
