#!/usr/bin/env python3
"""Exact, dependency-free counterexamples and repair checks for the audit.

The examples are deliberately four-node constructions so every feasible
matching can be inspected without trusting an optimizer.
"""

from __future__ import annotations

import itertools
import math


NODES = (0, 1, 2, 3)
M_A = ((0, 1), (2, 3))
M_B = ((1, 2), (3, 0))
MATCHINGS = (M_A, M_B)


def edge_key(edge: tuple[int, int]) -> tuple[int, int]:
    return tuple(sorted(edge))


def matching_sum(
    matching: tuple[tuple[int, int], ...],
    edge_values: dict[tuple[int, int], float],
) -> float:
    return sum(edge_values[edge_key(edge)] for edge in matching)


def check_node_marginal_nonidentification() -> None:
    """The same noisy-OR node marginals permit opposite edge rankings."""

    total_hazard = 2.0
    for t in (0.25, 1.75):
        hazards = {
            edge_key((0, 1)): t,
            edge_key((1, 2)): total_hazard - t,
            edge_key((2, 3)): t,
            edge_key((3, 0)): total_hazard - t,
        }
        node_probabilities = []
        for node in NODES:
            incident_sum = sum(
                hazard for edge, hazard in hazards.items() if node in edge
            )
            node_probabilities.append(1.0 - math.exp(-incident_sum))
        expected = 1.0 - math.exp(-total_hazard)
        assert all(abs(probability - expected) < 1e-12 for probability in node_probabilities)

        edge_probabilities = {
            edge: 1.0 - math.exp(-hazard) for edge, hazard in hazards.items()
        }
        difference = matching_sum(M_A, edge_probabilities) - matching_sum(
            M_B, edge_probabilities
        )
        assert (difference < 0.0) if t < total_hazard / 2.0 else (difference > 0.0)


def check_product_of_node_marginals_is_not_joint() -> None:
    """One latent edge forces its two endpoint labels to agree."""

    q = 0.4
    product_model_probability_y10 = q * (1.0 - q)
    coherent_latent_edge_probability_y10 = 0.0
    assert product_model_probability_y10 > coherent_latent_edge_probability_y10


def check_endpoint_range_is_not_attainable_interval() -> None:
    """Two matchings can attain only 0 and 1, not the interval between them."""

    target = {M_A: 0.0, M_B: 1.0}
    attainable = {target[matching] for matching in MATCHINGS}
    lower, upper = min(attainable), max(attainable)
    assert attainable == {0.0, 1.0}
    assert lower < 0.5 < upper
    assert 0.5 not in attainable


def retained_matchings(
    edge_scores: dict[tuple[int, int], float], rho: float
) -> set[tuple[tuple[int, int], ...]]:
    totals = {matching: matching_sum(matching, edge_scores) for matching in MATCHINGS}
    threshold = rho * max(totals.values())
    return {matching for matching, total in totals.items() if total >= threshold - 1e-12}


def check_raw_fractional_floor_is_scale_dependent() -> None:
    """Rank-preserving score changes alter the raw rho ambiguity set."""

    scores = {
        edge_key((0, 1)): 0.9,
        edge_key((2, 3)): 0.1,
        edge_key((1, 2)): 0.6,
        edge_key((3, 0)): 0.6,
    }
    squared = {edge: value**2 for edge, value in scores.items()}
    shifted = {edge: value + 10.0 for edge, value in scores.items()}

    assert retained_matchings(scores, rho=0.90) == {M_B}
    assert retained_matchings(squared, rho=0.90) == {M_A}
    assert retained_matchings(shifted, rho=0.90) == {M_A, M_B}


def normalized_regret(
    matching: tuple[tuple[int, int], ...],
    edge_scores: dict[tuple[int, int], float],
) -> float:
    totals = [matching_sum(candidate, edge_scores) for candidate in MATCHINGS]
    value = matching_sum(matching, edge_scores)
    if max(totals) == min(totals):
        return 0.0
    return (max(totals) - value) / (max(totals) - min(totals))


def check_normalized_regret_is_positive_affine_invariant() -> None:
    """For fixed-cardinality exact covers, normalized regret survives aw+b."""

    scores = {
        edge_key((0, 1)): 0.9,
        edge_key((2, 3)): 0.1,
        edge_key((1, 2)): 0.6,
        edge_key((3, 0)): 0.6,
    }
    transformed = {edge: 7.0 * value + 11.0 for edge, value in scores.items()}
    for matching in MATCHINGS:
        assert abs(
            normalized_regret(matching, scores)
            - normalized_regret(matching, transformed)
        ) < 1e-12


def same_bin(left: int, right: int) -> int:
    return int(left == right)


def check_missing_bin_completion_bounds() -> None:
    """Edgewise 0/1 envelopes are exact when missing bins are unrestricted."""

    # Nodes 0 and 2 are observed in bins 0 and 1; nodes 1 and 3 are missing.
    observed: dict[int, int | None] = {0: 0, 1: None, 2: 1, 3: None}
    feasible_totals: list[int] = []
    for missing_values in itertools.product((0, 1), repeat=2):
        completed = dict(observed)
        completed[1], completed[3] = missing_values
        for matching in MATCHINGS:
            feasible_totals.append(
                sum(same_bin(completed[i], completed[j]) for i, j in matching)
            )

    lower_edge = {
        edge_key(edge): (
            same_bin(observed[edge[0]], observed[edge[1]])
            if observed[edge[0]] is not None and observed[edge[1]] is not None
            else 0
        )
        for matching in MATCHINGS
        for edge in matching
    }
    upper_edge = {
        edge_key(edge): (
            same_bin(observed[edge[0]], observed[edge[1]])
            if observed[edge[0]] is not None and observed[edge[1]] is not None
            else 1
        )
        for matching in MATCHINGS
        for edge in matching
    }
    envelope_lower = min(matching_sum(matching, lower_edge) for matching in MATCHINGS)
    envelope_upper = max(matching_sum(matching, upper_edge) for matching in MATCHINGS)
    assert envelope_lower == min(feasible_totals)
    assert envelope_upper == max(feasible_totals)


def check_edge_linear_regression_identity() -> None:
    """A residualized linear coefficient is one matching objective, not daily endpoints."""

    residualized_treatment = (1.0, -0.5, 0.25, -0.75)
    treatment = (1.0, 0.0, 1.0, 0.0)
    denominator = sum(r * d for r, d in zip(residualized_treatment, treatment))
    edge_exposure = {
        edge_key((0, 1)): 0.2,
        edge_key((2, 3)): 0.8,
        edge_key((1, 2)): 0.6,
        edge_key((3, 0)): 0.1,
    }
    assert denominator != 0.0

    for matching in MATCHINGS:
        outcomes = [0.0] * len(NODES)
        for i, j in matching:
            value = edge_exposure[edge_key((i, j))]
            outcomes[i] = value
            outcomes[j] = value
        direct = sum(r * y for r, y in zip(residualized_treatment, outcomes)) / denominator
        edge_linear = sum(
            (residualized_treatment[i] + residualized_treatment[j])
            * edge_exposure[edge_key((i, j))]
            for i, j in matching
        ) / denominator
        assert abs(direct - edge_linear) < 1e-12


def check_strong_endpoint_marginal_operator_couples_assignments() -> None:
    """A conditional two-marginal paired-removal model couples assignments."""

    # This is a toy for the *strong* interpretation in which missing tracts mean
    # at least one assigned endpoint bucket is below three. All four rows have
    # missing tracts. Their drop-off supports are fixed to one bucket Z, whose
    # count is four and is therefore high. Each row's selected pickup bucket
    # must consequently be low. The example does not assert that this converse
    # or support configuration governs the current Chicago release.
    pickup_domains = {
        0: ("A", "B"),
        1: ("A", "C"),
        2: ("A", "D"),
        3: ("A", "E"),
    }
    pickup_bins = {"A": 0, "B": 1, "C": 2, "D": 1, "E": 2}
    dropoff_labels = ("Z",) * 4
    fixed_matching = ((0, 1), (2, 3))
    feasible_same_counts = []
    for pickup_labels in itertools.product(
        *(pickup_domains[node] for node in NODES)
    ):
        pickup_counts = {
            label: pickup_labels.count(label) for label in set(pickup_labels)
        }
        dropoff_counts = {
            label: dropoff_labels.count(label) for label in set(dropoff_labels)
        }
        released = tuple(
            pickup_counts[pickup_labels[node]] >= 3
            and dropoff_counts[dropoff_labels[node]] >= 3
            for node in NODES
        )
        if any(released):
            continue
        feasible_same_counts.append(
            sum(
                pickup_bins[pickup_labels[i]] == pickup_bins[pickup_labels[j]]
                for i, j in fixed_matching
            )
        )
    independent_edgewise_upper = 2
    coupled_upper = max(feasible_same_counts)
    assert independent_edgewise_upper == 2
    assert coupled_upper == 1


def main() -> None:
    checks = [
        check_node_marginal_nonidentification,
        check_product_of_node_marginals_is_not_joint,
        check_endpoint_range_is_not_attainable_interval,
        check_raw_fractional_floor_is_scale_dependent,
        check_normalized_regret_is_positive_affine_invariant,
        check_missing_bin_completion_bounds,
        check_edge_linear_regression_identity,
        check_strong_endpoint_marginal_operator_couples_assignments,
    ]
    for check in checks:
        check()
        print(f"PASS {check.__name__}")


if __name__ == "__main__":
    main()
