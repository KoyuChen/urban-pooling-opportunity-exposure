# ATR DIAMOR cross-day candidate-support calibration v1

Status: **PASS**.

The protocol searches a fixed 8-by-6 radius--motion-angle grid on DIAMOR-1,
requires at least 95% snapshot-level relational coverage, and selects the
qualifying rule with the fewest mean candidate edges. DIAMOR-2 is evaluated
only after selection; it is not used to choose the rule.

The selected rule is a 3 m radius and 120 degree maximum motion angle. On the
pilot day it contains the complete annotated dyad world in 85/88 snapshots
(96.6%) with 4.52 candidate edges per snapshot. Frozen on the follow-up day, it
contains the annotated world in 81/82 snapshots (98.8%), but candidate density
rises to 12.17 edges per snapshot, 2.69 times the pilot value.

All 82 follow-up frontiers close exactly. Of 246 threshold decisions, 217 are
ambiguous and 29 are certified (11.8%). No false certificate occurs at these
three evaluated thresholds. This zero count is threshold-specific and does not
establish unconditional safety when the candidate graph omits the annotated
world.

The honest conclusion is that the pilot coverage target transfers to this
follow-up day, while sparsity and decision informativeness do not. The selected
physical rule is therefore not evidence for a universal candidate generator;
the density shift motivates calibration that reports both relational coverage
and downstream certification yield. DIAMOR-2 had already been touched by prior
audits, so this is a frozen cross-day follow-up rather than a pristine holdout.

