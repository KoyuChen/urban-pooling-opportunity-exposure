# KDD 2027 research-track checklist

The live KDD call and submission form remain authoritative. This checklist
covers the current EventFrontier paper only.

## Paper format

- [x] English manuscript in anonymous ACM review layout.
- [x] One canonical source at `paper/main.tex`.
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
- [x] Abstract, introduction, and conclusion use this chain without reviving
  superseded learning or partner-recovery claims.

## Correctness and reproducibility

- [x] Exact small instances agree with exhaustive/reference comparators.
- [x] Witness replay, MIP gaps, unresolved cells, and technical errors are
  reported separately.
- [x] Controlled-truth evaluation separates scalar coverage, true-world
  representability, and existence of an alternative frontier.
- [x] Expensive live audits are manually dispatched rather than restarted on
  every manuscript commit.
- [x] Frozen evidence files record workflow, artifact, and SHA-256 pins for the
  NYC panel, scale lattice, and Chicago run 164.

## Controlled validation

- [x] 3,000 controlled-truth instances cover `C=2,3,4`.
- [x] Full candidate support covers the generated true aggregate in every
  instance.
- [x] Feasible point-rule threshold errors are quantified and shown to lie in
  the frontier's ambiguity region.
- [x] Candidate truncation reports retained true members and complete-world
  representability separately.
- [x] Generator mechanics, baselines, conditioning on true support count, and
  evaluation denominators are explicit in the appendix and code.

## NYC public evidence

- [x] Frozen 24-window design is outcome-blind and spans seasons, dayparts, and
  weekday/weekend regimes.
- [x] Twenty-one eligible, three scientifically ineligible, zero technical
  failures, and all 24 terminal reports are disclosed.
- [x] The manuscript reports 101/126 exact endpoint pairs, 125 ambiguous median
  decisions, and one unresolved decision.
- [x] The 19.0% statistic is correctly described as disagreement among four
  feasible point methods, not error against unobserved truth.
- [x] The scale lattice reports 14/18 exact closures and all four valid open
  intervals.
- [x] Public NYC rows are explicitly stated to contain no membership truth.

## Chicago public evidence

- [x] Live extraction is snapshot-stable and count-closed for 60 cores, 611
  candidates, and 50,405 endpoint-bin contributors.
- [x] Full rows are fetched through exact start/end-bin shards after a narrow
  overlap index; broad `OR` and full-row cross-column range queries are absent.
- [x] The two positive-length graph covers and their 60/60 assignment change are
  reported as graph-cover multiplicity only.
- [x] Fail-closed assertions preserve
  `PARTIAL_DOCUMENTED_PUBLIC_CONSISTENCY`.
- [x] No private implementation, null-cause, finite-radius, hidden-run closure,
  or partner-recall claim is made.

## Claim boundary

- [x] Endpoint claims are conditional on the declared candidate universe,
  timestamp support, capacity, support count, and solver status.
- [x] A nonempty frontier is not treated as evidence that the true joint world
  survived candidate construction.
- [x] No partner-recovery, realized-capacity, population, causal, or proprietary
  implementation claim appears in the title, abstract, introduction, or
  conclusion.
- [ ] Complete the final sentence-by-sentence theorem/artifact citation audit.

## Extension and repository hygiene

- [x] Compact code, paired records, summary, default decision and claim boundary
  are mutually hash-checked.
- [x] Only unified CI and manual Chicago auditing remain active workflows.
- [x] Selective disclosure is explicitly separated from the frozen manuscript.
- [ ] Revisit integration only after real membership truth or a closed
  unknown-support/noisy-answer extension.

## Submission decision

- [ ] **GO** only after the integrated manuscript passes CI, the visual PDF
  inspection is clean, and the live KDD 2027 rules are revalidated.
- [ ] If candidate-support assumptions carry an unconditional conclusion,
  revise the claim rather than hiding the condition.
- [ ] If an expensive cell remains unresolved, report the valid gap; never
  relabel it infeasible or exact.
