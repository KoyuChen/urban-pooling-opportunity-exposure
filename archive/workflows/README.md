# Disabled historical workflows

These files are exact copies of GitHub Actions workflows that produced or tested
one-off evidence during development. The `.disabled` suffix prevents GitHub
from treating them as active workflows.

Current active workflows are limited to:

- `.github/workflows/build-paper.yml` (`ci`): deterministic tests, locked solver
  checks, and paper build;
- `.github/workflows/chicago-live-audits.yml`: manually dispatched Chicago live
  release and boundary audits.

The 24-window NYC decision panel and the current branch-and-price scale lattice
have already been frozen and pinned in `ARTIFACT_MANIFEST.md`. Restore an old
workflow only for an explicit same-estimand rerun.
