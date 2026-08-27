# Chicago data-pipeline boundary

This directory contains two deliberately separate layers:

1. `fetch_complete_authorized_days.py` prepares a snapshot-pinned City download
   when the API is reachable. It has not produced a complete-day artifact in
   the current environment; see `ACCESS_BLOCKER.md`.
2. `chicago_release_adapter.py` converts already-normalized, declared inputs
   into `ReleaseOperatorSpec`, `ReleaseRowSpec`, and `CountConstraint` objects
   for the generic release compiler. It performs no network request and does
   not infer City semantics from column names or blank values.

## Safe one-way rule

The adapter encodes only the currently documented direction:

- a visible fine tract requires every applicable endpoint-marginal cell for
  that row to be `HIGH`;
- pickup/start and dropoff/end cells are distinct factors, even when their
  tract and time-bin labels happen to match;
- a blank becomes `LOW(pickup) OR LOW(dropoff)` only under content-addressed
  `paired_threshold_verified` evidence from a metadata-pinned independent
  authority contract;
- `known_low_endpoints` evidence constrains exactly the named endpoints (a
  one-sided culprit means one `LOW`, not a two-sided disjunction), while
  `privacy_only_no_low` evidence produces no `LOW` literal;
- all other blanks compile to a TRUE clause. Outside-city, source-missing,
  other-null, and unknown-null causes remain explicit and never become `LOW`
  by converse reasoning.

The factor threshold is pinned to the declared at-most-two rule: `LOW <= 2`
and `HIGH >= 3`, in 15-minute cells. Internal cells are checked against a
caller-supplied tract-vintage support and canonical SHA-256. Every factor key
also embeds a release-context namespace containing the dataset snapshot,
operator, tract vintage/support, partition-definition digest, and time-bin
definition digest. Identically named cells from different releases therefore
cannot alias. Cell partitions and the public snapshot are mandatory metadata,
not hidden defaults.

## Count universe

Every supplied trip is bound to both endpoint factors regardless of whether
its analysis role is `core`, `buffer`, or `context_only`. The adapter verifies
the count and canonical node-ID hash against a declared all-contributor
universe, so a caller cannot silently pass only the matched/core cohort while
claiming to use the pinned declaration. This is an interface guarantee, not
proof that the declaration itself contains every City trip.

For each substantive label, the caller supplies the pickup/start and
dropoff/end factor. An `unknown_null` may enumerate internal-cell and null-cause
alternatives, but a row carrying visible or independently confirmed privacy
evidence must have the same set of applicable endpoints across its labels.
The adapter fails closed if that implication would otherwise depend on a
label-specific applicability choice.

Each row also carries a canonical digest of its complete label-to-factor map
and a support-completeness status. An externally verified status requires a
content-addressed artifact and a metadata-pinned authority contract that is
independent of the candidate builder. Unless every support passes that
contract, diagnostics report
`label_support_scope = analyst_declared_conditional` and
`label_support_outer_claim_licensed = False`. This flag covers only the
declared per-node label supports; even when true, it never licenses a claim
about candidate-edge coverage. A TRUE clause for `unknown_null` says only that
the release observation imposes no LOW/HIGH literal; it never claims that the
analyst supplied every latent label or candidate.

## Compiler handoff

```python
inputs = build_chicago_compiler_inputs(metadata=metadata, trips=trips)
handoff = compile_chicago_release_problem(
    ExactPathProblem(nodes=nodes, edges=edges),
    inputs=inputs,
    forget_order=forget_order,
)
compilation = handoff.compilation
```

Directly attaching `inputs.count_constraints` and calling the generic compiler
is not a supported Chicago handoff. `compile_chicago_release_problem` first
requires exact equality of source node IDs, roles, and ordered label supports;
rejects rogue or missing nodes; rejects every preloaded Chicago contribution,
requirement, or constraint; and freezes a sanitized source copy. Unrelated
source factors are rejected by default and must be named explicitly in
`allowed_source_factors` before their maps and constraints are preserved.

The emitted row bindings are nested read-only mappings. A compiler-input
contract digest is replayed immediately before compilation, so replacement or
post-build semantic drift fails closed. That digest covers the adapter inputs,
not the source graph, query, or forget order, and is not a full-compilation
digest.

`inputs.diagnostics` records the pinned support and universe, role/cause/factor
counts, label-support scope, authority/evidence digests, and a row-level
implication audit. It always reports
`city_implementation_validated = False` and
`live_extraction_performed = False`. Documentary provenance therefore cannot
be promoted into a City transformation-code validation claim.

## Local tests

```bash
python -m unittest discover -s code/ai_pilot/data_pipeline/tests -v
```

The adapter tests include two release counterexamples: three all-role trips are
needed to satisfy a visible `HIGH/HIGH` row, and the same high-count world
remains feasible for an unaudited blank but becomes infeasible under pinned
paired-threshold evidence. Further tests cover a one-sided known culprit,
privacy-only evidence, immutable bindings, cross-snapshot factor separation,
conditional support scope, rogue nodes, source role/support drift, preloaded
Chicago counts, factor allowlists, null-cause buckets, and metadata hashes.

## Remaining production gates

This adapter does not verify provider partitions, the cause of any real blank,
DST-fold handling, late-row recomputation, tract-vintage choice, run closure,
or completeness of a City extraction. A production Chicago result still
requires those independent audits plus a complete candidate support and solver
run; none is claimed here.
