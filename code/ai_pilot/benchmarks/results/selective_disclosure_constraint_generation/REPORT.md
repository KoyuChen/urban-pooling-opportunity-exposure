# Selective-disclosure constraint generation

Usage certificates: **900/900** exact agreements.
Pair certificates: **90/90** exact agreements.

| Interface | Mean iterations | Median | Maximum | Mean cuts | Median cuts | Maximum cuts | Mean separation seconds | Maximum seconds |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Row usage | 4.37 | 2 | 44 | 3.37 | 1 | 43 | 0.2023 | 3.9295 |
| Pair co-membership | 6.90 | 4 | 17 | 5.90 | 3 | 16 | 0.0356 | 0.1516 |

The certificate master starts with no opposite-world cuts. At each iteration it
solves the current hitting set, then solves an integer EventFrontier separation
problem subject to the proposed disclosed answers. A discovered opposite-
decision world contributes its disagreement set; absence of such a world
certifies the current certificate.

The separation layer uses the complete small event-column master but does not
enumerate feasible worlds. Explicit feasible-world enumeration is used only as
an audit oracle. Every one of the 990 tested certificates agrees with that
oracle.

HiGHS reports some successful integer solves with residual relative gaps on the
order of `1e-7`; this run uses a declared separation tolerance of `1e-6`. The
discrete certificate size is nevertheless checked cell-by-cell against the
exact explicit oracle. This is an exact small-instance algorithmic audit, not
yet a branch-and-price scale claim.
