# Claim boundary

## Supported

The pinned Chicago public release yields a count-reconciled K=2 temporal
candidate universe for the selected 15-minute core under the declared nearest
15-minute timestamp-release model. All public rows with determinate timestamps
that can overlap the core are included, and every public literal K=2/match row
with a null start or end is globally checked and appended. The radius and Gamma
families are nested, and their resolved aggregate endpoints widen monotonically
as support is relaxed.

## Not supported

The public release does not expose Shared Trip ID, vehicle ID, or co-rider
identity. The analysis therefore does not establish actual hidden-run closure,
identify true partners, estimate candidate recall, validate conformal coverage
on Chicago, or license treating a geographic radius as a necessary support
condition.
