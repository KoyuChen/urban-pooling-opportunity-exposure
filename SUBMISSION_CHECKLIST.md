# KDD 2027 AI for Sciences formatting and content checklist

This checklist implements the requirements in the supplied CFP snapshot. The
conference submission site remains authoritative if its instructions change.

## Format

- [x] English full paper.
- [x] ACM `acmart` review layout with
  `\documentclass[sigconf,review]{acmart}`.
- [x] Single-blind author and affiliation shown.
- [x] Main paper limited to eight pages.
- [x] References begin after the eight-page main paper.
- [x] Optional reproducibility appendix follows the references.
- [x] Double-column letter-size PDF.
- [x] No overfull boxes, missing citations, or undefined references in the
  verified local build.

## Mandatory main-paper sections

- [x] `Limitations and Ethical Considerations` appears on page 8.
- [x] `Generative AI Usage` appears on page 8.

## Track fit

- [x] Urban transportation system as the scientific domain.
- [x] Domain-specific public TNP and ACS data design.
- [x] AI component is structural inference under a privacy observation
  process, not a generic downstream classifier.
- [x] Interdisciplinary estimand links machine learning, operations research,
  urban mobility, and socioeconomic opportunity.
- [x] Human-experiment-free design.
- [x] Reproducibility appendix, code, design lock, solver tests, and known-truth
  benchmark included.

## Evidence gates before submission

- [ ] Replace every red `TBD` in the paper with a measured complete-day result,
  or delete the dependent claim.
- [ ] Run the complete-day Chicago extraction and frozen audit protocol.
- [ ] Pass or transparently fail the pre-declared calibration, support, bound-
  reduction, and sign-stability gates.
- [ ] Obtain and report the appropriate institutional ethics/human-subjects
  determination despite using public administrative records and no recruited
  participants.
- [ ] Recheck the live CFP, official template version, dates, submission URL,
  and any artifact-policy changes immediately before submission.
- [ ] Confirm author list, affiliations, acknowledgments, conflicts, funding,
  and disclosure text with all coauthors.
