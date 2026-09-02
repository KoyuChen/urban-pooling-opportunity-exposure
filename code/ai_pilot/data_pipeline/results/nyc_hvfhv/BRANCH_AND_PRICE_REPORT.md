# NYC exact integer ordered-run branch-and-price audit

Generated UTC: `2026-09-02T13:51:13+00:00`  
Source workflow run: `33637896306`  
Source commit: `5435331243b56400a53724d963b040e1199ed97f`

The audit holds fixed the same outcome-blind public cohort used by the exact-time
column-generation Gate: four core rows and the twelve nearest complete temporal
buffers for provider `HV0005`. Every displayed integer optimum is independently
matched by complete small-instance run-column enumeration.

| C | Full run columns | Root LP upper bound | Certified integer optimum | Nodes | Buffer/pair branches | Maximum depth | Oracle LP solves | Pricing cases | Seconds |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2 | 54 | 4.000 | 4 | 1 | 0 / 0 | 0 | 450 | 8 | 0.75 |
| 3 | 394 | 8.000 | 8 | 4 | 0 / 3 | 2 | 6,552 | 127 | 10.53 |
| 4 | 1,719 | 12.000 | 12 | 2 | 0 / 1 | 1 | 5,400 | 96 | 9.28 |

At `C=3` and `C=4`, the root LP bound already equals the eventual integer
optimum, but the root restricted integer masters from ordinary column generation
were only 7 and 10. Ryan--Foster branching changes the pricing restrictions and
reveals columns needed to certify integer values 8 and 12. Thus the integer
layer is not equivalent to simply solving the root restricted master.

## Locked nonintegrality witness

The deterministic capacity-two witness has:

- full root LP value `4`;
- certified integer value `3`;
- 17 processed branch nodes;
- 1 buffer-usage branch and 7 Ryan--Foster pair branches;
- maximum depth 5;
- 1,030 interval-oracle LP solves across nodes.

This closes a genuine one-unit integrality gap and verifies that the branching
layer is substantive rather than cosmetic.

## Exactness boundary

The algorithm branches first on a fractional optional-buffer usage and then on
a fractional pair co-membership value. A together child requires the pair to
occur in the same selected run; a separate child forbids any run containing
both. At each node, all accumulated pair decisions are expanded into a finite
collection of forced-in/forced-out cases. Every case is solved by the same
fixed-span integral interval LP, and a node is closed only after no negative
reduced-cost column remains.

Global integer optimality is certified when the branch queue closes. The number
of branch-compatible pricing cases may grow exponentially with branch depth;
there is no claim that the full integer decomposition is polynomial-time.

## Claim boundary

This is exact algorithm validation on one small fixed public cohort plus a
deterministic exhaustive battery. It does not recover co-riders or vehicle runs,
does not identify realized capacity or production matching logic, and does not
establish city-scale runtime. No raw row, identifier, generated run column, or
selected-run witness is published.
