# Repository policy

## One current scientific source

`paper/main.tex` and the files it imports are the only active manuscript source.
Unused or superseded sections belong in `archive/`, not beside the current
paper.

## Source, evidence, generated output

- **Source:** code, tests, manuscript text, protocols, and deterministic input
  specifications.
- **Evidence:** aggregate tables/manifests with a commit, workflow run, artifact
  ID, status, and hash. Evidence never contains raw identifiers or latent
  row-level assignments.
- **Generated output:** PDFs, logs, caches, downloaded public rows, temporary
  solver files, and workflow ZIPs. Generated output is ignored locally and
  uploaded through Actions rather than committed to active source paths.

A committed aggregate result is frozen. It is replaced only by a separately
pinned run with the same estimand and an explicit reason for supersession.

## CI policy

The `ci` workflow is the default truth source for deterministic correctness and
the paper build. Expensive external-data panels are manually dispatched and do
not restart on ordinary manuscript commits.

A solver status must remain one of exact/certified, bounded, unresolved,
infeasible with a valid certificate, or technical failure. Time limits and
transport errors are never relabeled as infeasibility or scientific
ineligibility.

## Archive policy

`archive/` is provenance only. Archived code is not imported by current CI;
archived prose is not cited as the current model or contribution statement.
Files are moved rather than silently deleted when they document a prior research
path, failed assumption, or exact historical workflow.

## Claim policy

Every public-data conclusion must distinguish:

1. correctness of endpoints conditional on the declared feasible-world set;
2. evidence that candidate construction retains the true latent world; and
3. facts observable in the public release.

No result may infer operational partner identities, proprietary release logic,
null causes, realized capacity, population prevalence, or causal effects unless
those objects are independently identified and audited.
