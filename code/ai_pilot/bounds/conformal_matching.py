#!/usr/bin/env python3
"""Split-conformal calibration for score-restricted matching sets.

The functions in this module are deliberately learner agnostic.  A model may
assign any finite additive score to a feasible matching.  On markets for which
the hidden matching is known, its normalized score regret is a scalar
nonconformity score.  A split-conformal order statistic then calibrates a
matching set for a new exchangeable market.

For a matching-only scorer, calibration markets need their true matchings to
evaluate nonconformity.  Coverage additionally requires exchangeable augmented
markets and almost-sure membership of each true full world in the frozen
reference feasible set.  At a smaller reported candidate-omission budget, a
separate full-world eligibility failure bound ``alpha_G`` yields query coverage
at least ``1 - alpha_S - alpha_G``.  The module does not make synthetic
calibration transferable to a different real-data population.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from decimal import Decimal
from fractions import Fraction
from typing import Any, Iterable, Sequence

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


def _declared_rational(value: Any, name: str) -> Fraction:
    """Return the exact rational declared by a scalar.

    A float declares its shortest round-trippable decimal spelling.  This is
    the same convention used by the exact path solver: a scorer output printed
    as ``0.1`` means the rational 1/10, rather than the hidden binary64 dyadic
    approximation to 0.1.  Passing ``Fraction`` or ``Decimal`` avoids any
    a float declaration altogether.
    """

    if isinstance(value, (bool, np.bool_)):
        raise ValueError(f"{name} must be a finite rational, not bool")
    if isinstance(value, Fraction):
        return value
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError(f"{name} must be finite")
        return Fraction(value)
    if isinstance(value, (int, np.integer)):
        return Fraction(int(value))
    if isinstance(value, (float, np.floating)):
        converted = float(value)
        if not math.isfinite(converted):
            raise ValueError(f"{name} must be finite")
        return Fraction(str(converted))
    if isinstance(value, str):
        try:
            return Fraction(value)
        except (ValueError, ZeroDivisionError) as exc:
            raise ValueError(f"{name} must be a finite rational") from exc
    try:
        result = Fraction(value)
    except (TypeError, ValueError, ZeroDivisionError) as exc:
        raise ValueError(f"{name} must be a finite rational") from exc
    return result


def exact_additive_score(components: Iterable[Any]) -> Fraction:
    """Sum scorer outputs under the exact path solver's declaration rule.

    Convert every additive component before summing.  Converting an already
    rounded float total is not equivalent: for example, Python evaluates
    ``0.1 + 0.1 + 0.1`` as ``0.30000000000000004``, while the exact solver
    declares the three scorer outputs separately and obtains 3/10.  Components
    must be repeated with the same incidence multiplicity used by the solver.
    """

    if isinstance(components, (str, bytes)):
        raise ValueError("score components must be an iterable of scalars")
    total = Fraction(0)
    for index, component in enumerate(components):
        total += _declared_rational(component, f"score component {index}")
    return total


def _round_declared_up(value: Fraction) -> float:
    """Return a float whose declared decimal rational is not below ``value``."""

    rounded = float(value)
    while Fraction(str(rounded)) < value:
        rounded = math.nextafter(rounded, math.inf)
    return rounded


def _round_declared_down(value: Fraction) -> float:
    """Return a float whose declared decimal rational is not above ``value``."""

    try:
        rounded = float(value)
    except OverflowError as exc:
        raise ValueError(
            "score floor is not representable as a finite float; use "
            "exact_score_floor_from_radius"
        ) from exc
    if not math.isfinite(rounded):
        raise ValueError(
            "score floor is not representable as a finite float; use "
            "exact_score_floor_from_radius"
        )
    while Fraction(str(rounded)) > value:
        rounded = math.nextafter(rounded, -math.inf)
    return rounded


@dataclass(frozen=True)
class FixedScoreRange:
    """One immutable normalization range for a nested restriction path.

    Construct this object once from a declared ambient feasible family (for
    example the largest audited ``Gamma``) and reuse it at every smaller
    ``Gamma``.  Although the feasible-world families may be nested, rebuilding
    their score minima and maxima at each ``Gamma`` changes the score floor and
    can make the score-restricted families non-nested.

    Endpoints are stored as exact rationals under the same input convention as
    the exact path solver.  ``exact_floor`` can therefore be passed directly to
    that solver without a float round trip.
    """

    minimum: Fraction
    maximum: Fraction

    def __post_init__(self) -> None:
        lower = _declared_rational(self.minimum, "minimum_feasible_score")
        upper = _declared_rational(self.maximum, "maximum_feasible_score")
        if lower > upper:
            raise ValueError("minimum feasible score exceeds maximum feasible score")
        object.__setattr__(self, "minimum", lower)
        object.__setattr__(self, "maximum", upper)

    def normalized_regret(
        self,
        matching_score: Any,
        *,
        tolerance: float = 1e-10,
    ) -> float:
        """Return conservatively rounded normalized regret in ``[0, 1]``."""

        tol = _finite(tolerance, "tolerance")
        if tol < 0:
            raise ValueError("tolerance must be nonnegative")
        score = _declared_rational(matching_score, "matching_score")
        if score < self.minimum or score > self.maximum:
            raise ValueError("matching score lies outside the feasible score range")
        if self.minimum == self.maximum:
            return 0.0
        exact_regret = (self.maximum - score) / (
            self.maximum - self.minimum
        )
        return _round_declared_up(exact_regret)

    def exact_floor(self, tau: Any) -> Fraction:
        """Return the exact rational score floor for radius ``tau``."""

        radius = _declared_rational(tau, "tau")
        if not 0 <= radius <= 1:
            raise ValueError("tau must lie in [0, 1]")
        return (1 - radius) * self.maximum + radius * self.minimum

    def float_floor(self, tau: Any) -> float:
        """Return an outward-rounded float version of ``exact_floor``."""

        return _round_declared_down(self.exact_floor(tau))


def normalized_matching_regret(
    matching_score: Any,
    minimum_feasible_score: Any,
    maximum_feasible_score: Any,
    *,
    tolerance: float = 1e-10,
) -> float:
    """Return positive-affine-invariant regret in ``[0, 1]``.

    The normalization is within one market and one score map.  It therefore
    avoids comparing raw score fractions across models with different origins
    or units.  A score map is treated as constant only when its two endpoints
    are exactly equal under the declared rational input semantics.  The legacy
    ``tolerance`` argument is validated for API compatibility but deliberately
    does not alter interval membership or collapse a nonzero score range.

    This exact-degeneracy convention is important for coverage.  Treating a
    nonzero range as constant can assign zero regret during calibration and
    then translate that radius back to the strict maximum-score floor, thereby
    excluding a lower-scoring calibration or target matching.
    """

    return FixedScoreRange(
        minimum_feasible_score,
        maximum_feasible_score,
    ).normalized_regret(matching_score, tolerance=tolerance)


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
    minimum_feasible_score: Any,
    maximum_feasible_score: Any,
    tau: Any,
) -> float:
    """Translate a normalized regret radius into an additive score floor.

    This compatibility wrapper returns a float whose decimal-spelling rational
    is no larger than the exact floor.  Use
    :func:`exact_score_floor_from_radius` when the consumer accepts exact
    rationals, as the path-frontier DP does.
    """

    return FixedScoreRange(
        minimum_feasible_score,
        maximum_feasible_score,
    ).float_floor(tau)


def exact_score_floor_from_radius(
    minimum_feasible_score: Any,
    maximum_feasible_score: Any,
    tau: Any,
) -> Fraction:
    """Return a score floor without a float round trip.

    The returned ``Fraction`` uses the exact same decimal-spelling convention
    as float scores consumed by the exact path solver.
    """

    return FixedScoreRange(
        minimum_feasible_score,
        maximum_feasible_score,
    ).exact_floor(tau)


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
