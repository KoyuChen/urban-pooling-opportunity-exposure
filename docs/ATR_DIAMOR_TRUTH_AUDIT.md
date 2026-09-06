# ATR DIAMOR truth audit

This transfer study uses ATR pedestrian trajectories with manually coded
social groups. It tests EventFrontier against an annotated row-to-row relation
after membership labels are masked from candidate edge scoring.

## Claim boundary

The audit considers only two-person groups in DIAMOR and conditions on the true
number `q` of visible dyads at each fixed snapshot. Candidate edges use only
simultaneous position and direction. Group labels nevertheless assist cohort
exclusion, snapshot eligibility, disclosure of `q`, and final evaluation. It
is therefore an **oracle-assisted, q-conditioned masked-label audit**, not a
fully label-blind inference experiment. It does not identify friendship,
recover population group rates, or validate Chicago's operator.

DIAMOR-1 is the development/pilot day. DIAMOR-2 is the confirmatory day. The
expanded v2 follow-up uses a deterministic two-minute grid fixed before reading
any of its additional cells; because the day had already been used by the v1
sparse audit, it is labeled a predeclared follow-up rather than a pristine new
holdout. Their roles must remain distinguishable.

The v4 evidence protocol conservatively parses the ATR record grammar. Members
of standard reciprocal groups larger than two are excluded. All recoverable
positive IDs in partial/nonpositive, multiple-ID, one-sided, or conflicting
annotations are quarantined; conflicts close over every affected group and are
never silently treated as singletons. Documented mobility-aid prefixes are
parsed before recoverable positive partners are quarantined.
The source labels were produced by one coder and are an annotated reference,
not error-free physical truth.

## Endpoints and checks

For each snapshot and candidate radius, a binary MILP computes minimum and
maximum mean separation over cardinality-`q` matchings. A numerical optimum is
accepted only with optimal solver status, zero reported relative gap, and a
replayed witness satisfying index, degree, cardinality, and objective checks.
The raw solver vector is also checked for integrality, cardinality, degree,
solver-objective agreement, and primal--dual agreement.
For graphs with at most 12 vertices, a separate subset-recursion oracle checks
both endpoints or infeasibility. Full local reports retain index-based lower
and upper witnesses, primal/dual diagnostics, hashes, and solver versions.
Public summaries contain no raw pedestrian IDs or recovered relation assignment.

Candidate misspecification is not repaired using truth. `INFEASIBLE` is a
closed result; a time limit or solver failure is `UNRESOLVED` and forces HOLD.
Computational closure, endpoint consistency, witness replay, independent-oracle
agreement, and conditional truth coverage are reported separately.

## Run

After downloading and unpacking a DIAMOR archive from ATR:

```bash
python code/ai_pilot/benchmarks/atr_diamor_dyad_truth.py \
  --trajectory /path/to/person_DIAMOR-1_all.csv \
  --groups /path/to/groups_DIAMOR-1.dat \
  --audit-role pilot \
  --output /path/to/results
```

ATR data are research-use-only and are not redistributed here.
