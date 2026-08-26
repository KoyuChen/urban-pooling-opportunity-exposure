#!/usr/bin/env python3
"""Split-conformal calibration for score-restricted matching sets.

The functions in this module are deliberately learner agnostic.  A model may
assign any finite additive score to a feasible matching.  On markets for which
the hidden matching is known, its normalized score regret is a scalar
nonconformity score.  A split-conformal order statistic then calibrates a
matching set for a new exchangeable market.

If the new market's true matching belongs to the declared candidate graph,
the calibrated matching set contains it with marginal probability at least
``1 - alpha``.  Consequently, the minimum and maximum of any downstream
matching functional over that set cover the functional evaluated at the true
matching with the same probability.  The statement is conditional on
candidate support and exact endpoint optimization; it does not make synthetic
calibration transferable to a different real-data population.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Iterable, Sequence

import numpy as np


@dataclass(frozen=True)
class ConformalRadius:
    """Finite-sample split-conformal radius and its audit metadata."""

    alpha: float
    calibration_size: int
    order_rank: int
    tau: float
    calibration_coverage: float

    def to_dict(self) -> dict:
        return asdict(self)


def _finite(value: float, name: str) -> float:
    converted = float(value)
    if not math.isfinite(converted):
        raise ValueError(f"{name} must be finite")
    return converted


def normalized_matching_regret(
    matching_score: float,
    minimum_feasible_score: float,
    maximum_feasible_score: float,
    *,
    tolerance: float = 1e-10,
) -> float:
    """Return positive-affine-invariant regret in ``[0, 1]``.

    The normalization is within one market and one score map.  It therefore
    avoids comparing raw score fractions across models with different origins
    or units.  A constant score map assigns regret zero to every matching.
    """

    score = _finite(matching_score, "matching_score")
    lower = _finite(minimum_feasible_score, "minimum_feasible_score")
    upper = _finite(maximum_feasible_score, "maximum_feasible_score")
    tol = _finite(tolerance, "tolerance")
    if tol < 0:
        raise ValueError("tolerance must be nonnegative")
    if lower > upper + tol:
        raise ValueError("minimum feasible score exceeds maximum feasible score")
    scale = max(1.0, abs(lower), abs(upper), abs(score))
    if score < lower - tol * scale or score > upper + tol * scale:
        raise ValueError("matching score lies outside the feasible score range")
    if abs(upper - lower) <= tol * scale:
        return 0.0
    regret = (upper - score) / (upper - lower)
    return float(np.clip(regret, 0.0, 1.0))


def split_conformal_radius(
    calibration_regrets: Sequence[float] | np.ndarray,
    alpha: float,
) -> ConformalRadius:
    """Calibrate a finite-sample matching-set radius.

    With ``m`` exchangeable calibration markets, the order rank is
    ``ceil((m + 1) * (1 - alpha))``.  If this rank is ``m + 1``, the known
    support bound one is returned.  This is conservative and is necessary
    when the requested miscoverage is smaller than ``1 / (m + 1)``.
    """

    level = _finite(alpha, "alpha")
    if not 0.0 < level < 1.0:
        raise ValueError("alpha must lie strictly between zero and one")
    regrets = np.asarray(calibration_regrets, dtype=float).reshape(-1)
    if len(regrets) == 0:
        raise ValueError("at least one calibration regret is required")
    if not np.isfinite(regrets).all():
        raise ValueError("calibration regrets must be finite")
    if ((regrets < 0.0) | (regrets > 1.0)).any():
        raise ValueError("calibration regrets must lie in [0, 1]")

    rank = int(math.ceil((len(regrets) + 1) * (1.0 - level)))
    tau = 1.0 if rank > len(regrets) else float(np.sort(regrets)[rank - 1])
    calibration_coverage = float(np.mean(regrets <= tau))
    return ConformalRadius(
        alpha=level,
        calibration_size=len(regrets),
        order_rank=rank,
        tau=tau,
        calibration_coverage=calibration_coverage,
    )


def score_floor_from_radius(
    minimum_feasible_score: float,
    maximum_feasible_score: float,
    tau: float,
) -> float:
    """Translate a normalized regret radius into an additive score floor."""

    lower = _finite(minimum_feasible_score, "minimum_feasible_score")
    upper = _finite(maximum_feasible_score, "maximum_feasible_score")
    radius = _finite(tau, "tau")
    if lower > upper:
        raise ValueError("minimum feasible score exceeds maximum feasible score")
    if not 0.0 <= radius <= 1.0:
        raise ValueError("tau must lie in [0, 1]")
    return upper - radius * (upper - lower)


def combined_miscoverage_bound(*component_alphas: Iterable[float] | float) -> float:
    """Return the union-bound miscoverage for separately audited components."""

    flattened: list[float] = []
    for component in component_alphas:
        if isinstance(component, (float, int, np.floating, np.integer)):
            flattened.append(float(component))
        else:
            flattened.extend(float(value) for value in component)
    if not flattened:
        raise ValueError("at least one component alpha is required")
    if any(not math.isfinite(value) or value < 0.0 or value > 1.0 for value in flattened):
        raise ValueError("component alphas must lie in [0, 1]")
    return min(1.0, float(sum(flattened)))

