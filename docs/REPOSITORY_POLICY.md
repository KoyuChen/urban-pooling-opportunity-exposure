# Repository policy

## Active-tree rule

The repository keeps only files required by the current EventFrontier paper,
its reproducible algorithms, current public-data audits, and redacted evidence.
Historical experiments belong in Git history, not in active directories.

## Evidence rule

A headline empirical number must be tied to a commit, workflow run, artifact or
committed aggregate manifest, and solver status. Timeouts and transport failures
remain unresolved; they are never relabeled as infeasibility or optimality.

## Data rule

Do not commit raw public extracts, trip identifiers, event columns, latent
assignments, reconstructed partners, matching witnesses, or latent timestamps.
Only aggregate redacted outputs may enter `data_pipeline/results/`.

## Generated-output rule

PDFs, logs, caches, solver scratch files, downloads, and workflow ZIPs belong in
ignored directories or GitHub Actions artifacts. CI must not commit generated
PDFs back to the branch.

## Claim rule

Every result must distinguish:

1. endpoint correctness conditional on a declared feasible-world set;
2. evidence that candidate construction retains the true latent world; and
3. facts directly observable in the public release.

No result may infer operational partner identities, proprietary release logic,
blank-value causes, realized capacity, population prevalence, or causal effects
without independent identification and audit.
