# KDD 2027 research-track checklist

The live KDD call and submission form remain authoritative. This checklist
covers the current EventFrontier paper only.

## Paper format

- [x] English manuscript in anonymous ACM review layout.
- [x] One canonical source at `paper/main.tex`.
- [x] Main text currently fits the eight-page research-paper boundary before
  references and appendix.
- [x] CI compiles and checks the PDF; generated PDFs are not committed by a bot.
- [ ] Revalidate the official 2027 template, dates, page policy, disclosure
  language, artifact policy, and supplementary-material rules.
- [ ] Run the final visual audit for fonts, clipping, overfull boxes, references,
  and figure readability.

## Contribution chain

- [x] General problem is row-complete, relation-incomplete temporal event data;
  Chicago and NYC are applications rather than the definition of the method.
- [x] Feasible worlds distinguish core rows, optional buffers, positive-overlap
  connectivity, set-valued time, selected support, and simultaneous capacity.
- [x] Timestamp-support expansion and capacity relaxation give a proved nesting
  result.
- [x] Fixed-root/fixed-span pricing has a consecutive-ones formulation and an
  integral LP oracle.
- [x] Dantzig--Wolfe column generation closes the full LP after exact pricing.
- [x] Master nonintegrality is demonstrated, and row-usage plus Ryan--Foster
  branching preserves branch-compatible exact pricing.
- [x] Integer status is fail-closed: exact only when the node queue closes;
  otherwise report an incumbent and open-node upper bound.
- [ ] Ensure the abstract, theorem statements, and contribution paragraph use
  exactly this chain and do not revive superseded matching/learning claims.

## Correctness and reproducibility

- [x] Exact small instances agree with exhaustive/reference comparators.
- [x] Witness replay, MIP gaps, unresolved cells, and technical errors are
  reported separately.
- [x] Controlled-truth evaluation separates scalar coverage, true-world
  representability, and existence of an alternative frontier.
- [x] CI runs deterministic unit tests, adversarial counterexamples, locked
  solver audits, and the paper build.
- [x] Expensive live audits are manually dispatched rather than restarted on
  every manuscript commit.
- [ ] Freeze one final evidence manifest with commit, run, artifact, and hash
  pins for every headline number.

## Controlled validation

- [x] 3,000 controlled-truth instances cover `C=2,3,4`.
- [x] Full candidate support covers the generated true aggregate in every
  instance.
- [x] Feasible point-rule threshold errors are quantified and shown to lie in
  the frontier's ambiguity region.
- [x] Candidate truncation reports retained true members and complete-world
  representability separately.
- [ ] Keep generator mechanics, parameter ranges, baselines, and all evaluation
  denominators explicit in the appendix and artifact.

## NYC public evidence

- [x] Frozen 24-window design is outcome-blind and spans seasons, dayparts, and
  weekday/weekend regimes.
- [x] Scientific ineligibility is distinct from technical failure.
- [x] Outcome-capacity cells report exact, bounded, and unresolved statuses
  without coercion.
- [x] Branch-and-price scale lattice reports 14/18 exact closures and valid gaps
  for the remainder.
- [ ] Replace the obsolete six-window and 4+12-only exposition in the manuscript
  with the frozen panel and scale-lattice evidence.
- [ ] State throughout that public NYC rows provide no event-membership truth.

## Chicago public evidence

- [x] Current live extraction is snapshot-stable and count-closed for 60 cores,
  611 candidates, and 50,405 all-trip endpoint-bin contributors.
- [x] Full rows are fetched through exact start/end-bin shards after a narrow
  overlap index; broad `OR` and full-row cross-column range queries are absent.
- [x] Fail-closed assertions preserve the status
  `PARTIAL_DOCUMENTED_PUBLIC_CONSISTENCY`.
- [x] Boundary-padding and candidate-support sensitivity are retained as
  separate audits.
- [ ] Do not convert documented one-way release semantics into a claim about the
  City's private implementation.
- [ ] Do not infer null causes, finite spatial exclusions for unmeasured
  centroids, hidden-run closure, or partner recall.

## Claim boundary

- [x] Endpoint claims are conditional on the declared candidate universe,
  timestamp support, capacity, support count, and solver status.
- [x] A nonempty frontier is not treated as evidence that the true joint world
  survived candidate construction.
- [ ] Every headline sentence must be supported by a theorem, a controlled-truth
  result, or a pinned public-data artifact.
- [ ] No partner-recovery, realized-capacity, population, causal, or proprietary
  implementation claim appears in the title, abstract, introduction, or
  conclusion.

## Submission decision

- [ ] **GO** only after the latest frozen evidence is integrated, the manuscript
  and artifact manifest agree numerically, and all format/claim checks pass.
- [ ] If candidate-support assumptions carry an unconditional conclusion,
  revise the claim rather than hiding the condition.
- [ ] If an expensive cell remains unresolved, report the valid gap; never
  relabel it infeasible or exact.
