# NYC HVFHV ordered-run outcome bounds

Frozen from workflow `33551028665`, artifact `9817489639`, digest `sha256:cf4f16f590deababc74ecad20be99d18e1e62994bb9acfa7e09ace6923475806`.

Source head: `d7fec3602514d80bfd99ad136674dfa92054f363`.

Time model: `rounded_15m_outer`. Ordered core: **8**; candidate rows: **437**.

Each outcome interval conditions on the maximum feasible number of selected buffer rows for that declared capacity `C`, then varies only the public composition of those selected buffers.

| C | Max buffers/core | Outcome | Lower | Upper | Width | Status |
|---:|---:|---|---:|---:|---:|---|
| 2 | 9.0000 | mean selected-buffer miles at max support | 3.4402 | 9.6792 | 6.2391 | `CERTIFIED_OPTIMAL_PAIR` |
| 2 | 9.0000 | mean selected-buffer trip minutes at max support | 17.7794 | 37.1475 | 19.3681 | `CERTIFIED_OPTIMAL_PAIR` |
| 3 | 14.1250 | mean selected-buffer miles at max support | 4.1479 | 8.5138 | 4.3658 | `CERTIFIED_OPTIMAL_PAIR` |
| 3 | 14.1250 | mean selected-buffer trip minutes at max support | 20.3288 | 34.1555 | 13.8267 | `CERTIFIED_OPTIMAL_PAIR` |
| 4 | 18.5000 | mean selected-buffer miles at max support | 4.6151 | 8.4108 | 3.7957 | `CERTIFIED_OPTIMAL_PAIR` |
| 4 | 18.5000 | mean selected-buffer trip minutes at max support | 21.9988 | 33.8120 | 11.8133 | `CERTIFIED_OPTIMAL_PAIR` |

All published endpoint pairs have zero reported MIP gap.

## Identification geometry

The maximum feasible support expands strongly with capacity: 72 selected buffers at `C=2`, 113 at `C=3`, and 148 at `C=4`. Yet the conditional composition intervals shrink: the miles width falls by **39.2%** from `C=2` to `C=4`, and the duration width falls by **39.0%**.

This is **not** evidence that increasing capacity tightens the same identified set. The conditioning event changes with `C`: each row uses that capacity's own maximum feasible buffer cardinality. A larger support obligation forces the latent world to include more public rows, reducing the ability to cherry-pick only extreme-mileage or extreme-duration buffers. The feasible-world set itself still expands with `C`.

A clean capacity comparison therefore requires a common support cardinality across `C`. That is the next audit stage.

## Claim boundary

Supported: root-invariant public-attribute composition bounds in maximum-support latent worlds under the declared 15-minute outer public-time model.

Not supported: actual co-rider composition, realized vehicle runs, true vehicle capacity, production matching logic, or any claim that the true NYC system operates at the displayed `C` values.
