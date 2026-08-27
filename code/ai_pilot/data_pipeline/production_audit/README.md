# Chicago K=2 production audit

This harness audits a pinned, all-row Chicago extraction before a matched
`Trips Pooled = 2` hidden-partner analysis. It does not reconstruct or validate
the true partner relation. The public table omits Shared Trip ID, vehicle ID,
and partner identity, so every report fixes hidden-run closure to
`NOT_IDENTIFIED_FROM_PUBLIC_ROWS` and partner recall to
`NOT_ESTIMATED_FROM_PUBLIC_ROWS`.

No City row or raw trip identifier is committed here. The fixture is wholly
synthetic and marks that fact in every row. Runtime reports contain only
aggregate counts and hashes; even cover witnesses are not serialized.

## Necessary temporal rule

Let the released start and end be \(\hat s_i,\hat e_i\). Under the declared
nearest-15-minute release interpretation, the error bound is
\(\delta=7.5\) minutes. Thus

\[
s_i\in[\hat s_i-\delta,\hat s_i+\delta],\qquad
e_i\in[\hat e_i-\delta,\hat e_i+\delta].
\]

For two individually feasible released intervals, the transactions can have
overlapping occupancy intervals if and only if

\[
\hat s_i-\delta\le \hat e_j+\delta
\quad\text{and}\quad
\hat s_j-\delta\le \hat e_i+\delta.
\]

The condition presumes each row itself admits some \(s_i\le e_i\). A
chronology-impossible or missing interval is not forced through this
equivalence: the code conservatively retains all otherwise permitted edges and
reports the row anomaly. Released timestamps must use a complete local
date-time lexical form and lie exactly on the 15-minute publication grid;
date-only and off-grid values are malformed rather than silently normalized.
The outer intervals are closed. Equality is retained: the deterministic test
fixture includes one pair whose expanded intervals meet only at `10:37:30`.
A missing or malformed endpoint cannot prove non-overlap, so the locked
`retain_indeterminate` policy keeps every otherwise permitted incident edge,
while a malformed/off-grid target row blocks a production-ready conclusion.
If this makes the graph exceed the declared materialization limit, the audit
returns unresolved; it never converts that limit into an implicit degree cap.

The logical graph uses exactly three conditions:

1. both rows have literal `Shared Trip Match = true` and integer
   `Trips Pooled = 2`;
2. at least one endpoint is a core row; and
3. the closed timestamp envelopes can overlap.

`Shared Trip Authorized` is never a necessary screen. A `Match=true,
Authorized=false, K=2` row remains pair-eligible and is reported as an operator
contradiction. Null/invalid flags, `Match=true, K<2`, duplicate IDs, and blank
IDs remain separately counted rather than being coerced or silently
deduplicated.

## Roles and midnight boundaries

- **Core:** unique nonnull ID, literal `Match=true`, integer `K=2`, and released
  start in the half-open core window. Core degree must equal one.
- **Buffer:** the same literal K=2 target outside the core-start window (or
  without a usable anchor). Buffer degree is at most one. Core-buffer edges
  can cross midnight; buffer-buffer edges are irrelevant to covering the core
  and are not built.
- **Context:** every other extracted row. These rows are not matched by this
  audit but remain available to a downstream release-operator adapter as
  contributors to privacy counts.

An all-row extraction is required. A released-start range query by itself is
not a closed selection frame: it can omit a literal `Match=true, K=2` row whose
released start is null. The contract must therefore pin evidence that the
server-side count of such rows is zero, or append all such rows and reconcile
their included count to the pinned server count. Without that evidence, the
audit remains `BLOCKED_NULL_START_SCOPE`; any appended null-start target is a
buffer with indeterminate incident edges. An authorized-only file likewise
fails the completeness audit because contradictory matched rows could have
been omitted. Duplicate and null IDs are context-only and block a
production-ready result; the harness does not guess whether they are duplicated
publication rows or distinct transactions.

The buffer-envelope calculation optionally uses a maximum transaction-duration
bound. Its basis is explicit: `operator_verified`, `externally_validated`, or
`analyst_assumption`. Every nonnull bound requires a structured authority,
effective-scope enum, and artifact SHA-256; arbitrary reference text is neither
accepted nor echoed. An analyst assumption is locked to `sensitivity_only` and
cannot be presented as a City field. The audit also computes each row's minimum
possible duration after rounding,
\(\max\{0,\hat e_i-\hat s_i-2\delta\}\), and fails if even that lower bound
exceeds the declared maximum. The observed maximum is never promoted to a
logical bound.
With no declared bound, a partner can have started arbitrarily earlier, so
neighboring-day buffers cannot certify temporal support. Even an
operator-verified bound changes only the boundary-support label; it does not
reveal the hidden run.

The harness validates the evidence object's structure and digest, not the
substantive contents of the hashed artifact. Accordingly, even operator and
external statuses say `PASS_UNDER_DECLARED_...`; the artifact must be reviewed
separately before interpreting the declared authority as established fact.

## Heuristics are a separate graph

Pickup/dropoff radii, route-direction cosine, and deterministic greedy degree
caps are applied only to `heuristic_sensitivity`. Their deletions and cover
feasibility are reported separately. They never alter
`logical_necessary`, and the report classifies them as
`ANALYST_HEURISTIC_NOT_A_NECESSARY_SUPERGRAPH`. The synthetic fixture
deliberately shows a pickup-radius rule deleting a logical cross-midnight edge
and making a core node isolated.

Exact backtracking certifies small declared graphs. Larger graphs use
SciPy/HiGHS only as a numerical feasibility audit. A returned incumbent is
rounded and independently replayed against every core/buffer constraint; even
after a successful replay its production status remains explicitly
`NUMERICAL_UNCERTIFIED`. A feasible cover establishes only that the declared
constraints are mutually satisfiable; it is not evidence that any selected
edge is the actual partner.

## Run

Copy `templates/contract.template.json`, fill the pinned revision, server/local
row count, null-start selection evidence, extraction window, and any
duration-bound provenance. The input pin is the SHA-256 of canonical JSON rows
(all input columns, input order, `sort_keys=true`, compact separators), labelled
`canonical_json_rows_v1`. The library API always recomputes this digest from
the supplied rows and has no caller override. An unfilled or mismatched hash
fails completeness. Then run:

```bash
python code/ai_pilot/data_pipeline/production_audit/chicago_k2_audit.py \
  --input /secure/path/chicago_all_rows_with_buffers.csv \
  --contract /secure/path/production_contract.json \
  --report /secure/path/production_audit_report.json
```

For a new file, an initial run with the zero placeholder intentionally fails
but reports `actual_input_sha256`; pin that value in the contract and rerun.

The templates and JSON Schemas are machine-readable. The committed fixture can
be reproduced with:

```bash
python -m unittest discover \
  -s code/ai_pilot/data_pipeline/production_audit/tests -v

python code/ai_pilot/data_pipeline/production_audit/chicago_k2_audit.py \
  --input code/ai_pilot/data_pipeline/production_audit/fixtures/synthetic_cross_midnight.csv \
  --contract code/ai_pilot/data_pipeline/production_audit/fixtures/synthetic_contract.json \
  --report /tmp/chicago-k2-production-audit.json
```

The report's strongest possible conclusion remains conditional: a pinned row
slice can be complete, the declared buffer can support all temporal candidates
under a stated duration basis, and the declared graph can admit a cover. Public
rows alone do not identify true partner coverage or actual run closure.
