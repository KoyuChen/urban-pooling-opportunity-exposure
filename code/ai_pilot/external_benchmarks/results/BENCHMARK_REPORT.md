# External relation-truth benchmark result

Generated deterministically on 2026-08-27. No source records,
registry IDs, FEBRL IDs, pair labels, or endpoint witnesses are stored here.
The observed end-to-end runtime was 1.393
seconds (1.304 UCI,
0.090 FEBRL4) in the recorded environment.

## UCI Krebsregister block 1: real adjudicated boundary test

- Input hash: `a3d79e066fb08a066c89bb4034007434a16ea6fc883b9331216a0cb31de66548` (5,643,935 bytes).
- Candidate table: 574,913 unique pairs over
  94,758 records; 323
  components, including one 94,060-record component.
- Adjudicated positives: 2,093 edges over
  4,028 records. The relation is **not a matching**:
  152 records have positive degree above one,
  maximum degree is 3, and positive components
  reach 5 records.
- Conditional eligibility is 100.0% only because labels
  are attached to rows already selected by UCI's blocking. This says nothing
  about true pairs omitted before release.

The matching reduction is explicitly truth-conditioned. It starts from
1,800 two-record positive components,
drops 4 whose true edge
lacks the predeclared query value, and retains 1,796
truth dyads plus 741 negative alternative edges.
The induced candidate graph has 205 ambiguous
components; its deterministic source/calibration/test partition has no record
or edge overlap, but those components are not claimed iid.

The coherent matching-only query is the share of selected links with exact
postal-code agreement. The score-free numerical frontier is
**[0.918151, 0.954900]**; adjudicated
truth is **0.954900** and lies at the upper endpoint.
`NUMERICALLY_OPTIMAL` is a numerical HiGHS result, not an exact certificate.

## FEBRL4: external synthetic positive method-fit test

FEBRL4 has 5,000 originals,
5,000 duplicates, and a complete one-to-one
truth. All 5,000
source ID pairs directly encode their partner number, so source IDs and returned
links are isolated before public candidate, score, or query construction.
Market membership is truth-conditioned and disclosed.

- `dataset4a.csv` SHA-256: `07c7cb3f0a8d88180e80317f2a60499dee4e8324a44c38059f4e7fed0a8b4488`
- `dataset4b.csv` SHA-256: `2eed76c99fa2237be3ec013a123427926d4158abcb3a8f65874d6c7f1358cf2c`

| Market | True pairs | Complete candidate edges | True same-known-decade share | Score-free frontier | Uncalibrated score-optimum frontier | Point true-edge recovery | Exhaustive oracle |
|---|---:|---:|---:|---:|---:|---:|:---:|
| small_exact | 6 | 36 | 0.833333 | [0.000000, 0.833333] | [0.833333, 0.833333] | 1.000000 | yes |
| medium_numerical | 20 | 400 | 0.800000 | [0.000000, 0.850000] | [0.800000, 0.800000] | 1.000000 | no |

The score uses only coarsened Soundex/length/initial fields and excludes the
birth-decade query. The score-optimum column is a sensitivity analysis, not a
confidence set. The six-pair result exhausts all 720 bipartite matchings and
agrees with the numerical solver; the 20-pair result is numerical.

## Claim boundary

- UCI validates real adjudicated relation topology and a conditional dyad
  frontier; it does not validate UCI blocking recall or independent markets.
- FEBRL4 validates a clean complete-matching path, but it is synthetic and its
  two markets are constructed using truth.
- Neither benchmark calibrates a learned restriction, validates latent node
  attributes, or licenses transfer to Chicago.
