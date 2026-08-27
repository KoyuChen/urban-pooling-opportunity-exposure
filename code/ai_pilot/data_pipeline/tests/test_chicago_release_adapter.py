import sys
import unittest
from dataclasses import replace
from pathlib import Path


PIPELINE_DIR = Path(__file__).resolve().parents[1]
BOUNDS_DIR = PIPELINE_DIR.parent / "bounds"
for path in (PIPELINE_DIR, BOUNDS_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from chicago_release_adapter import (  # noqa: E402
    DATASET_ID,
    DROPOFF_END,
    INTERNAL_TRACT,
    OTHER_NULL,
    OUTSIDE_CITY,
    PICKUP_START,
    PRIVACY_COARSENING,
    SOURCE_MISSING,
    UNKNOWN_NULL,
    ChicagoCountFactor,
    ChicagoReleaseMetadata,
    DeclaredChicagoTrip,
    DeclaredTripUniversePin,
    EndpointReleaseObservation,
    LabelSupportDeclaration,
    PrivacyCauseEvidencePin,
    PrivacyEvidenceAuthorityContract,
    SupportEvidenceAuthorityContract,
    TractSupportPin,
    build_chicago_compiler_inputs,
    canonical_label_support_sha256,
    canonical_string_set_sha256,
    chicago_release_context,
    compile_chicago_release_problem,
)
from path_frontier_dp import (  # noqa: E402
    CountConstraint,
    EdgeSpec,
    ExactPathProblem,
    NodeSpec,
    solve_path_frontier_endpoints,
)


class ChicagoReleaseAdapterTests(unittest.TestCase):
    TRACTS = ("17031010100", "17031010200")
    LABEL = "declared-label"
    PARTITION = "declared-citywide-partition"
    AUTHORITY = "fixture-independent-adjudicator"
    SUPPORT_AUTHORITY = "fixture-independent-support-auditor"

    def authority(self):
        return PrivacyEvidenceAuthorityContract(
            authority_id=self.AUTHORITY,
            contract_reference="fixture://authority-contract/v1",
            contract_sha256="2" * 64,
            permitted_states=(
                "paired_threshold_verified",
                "known_low_endpoints",
                "privacy_only_no_low",
            ),
            independent_of_released_tract=True,
        )

    def support_authority(self):
        return SupportEvidenceAuthorityContract(
            authority_id=self.SUPPORT_AUTHORITY,
            contract_reference="fixture://support-authority-contract/v1",
            contract_sha256="5" * 64,
            certifies_complete_label_support=True,
            independent_of_candidate_builder=True,
        )

    def metadata(
        self,
        node_ids,
        *,
        support_hash=None,
        snapshot_hash=None,
        authorities=None,
    ):
        support_hash = support_hash or canonical_string_set_sha256(self.TRACTS)
        snapshot_hash = snapshot_hash or "1" * 64
        if authorities is None:
            authorities = (self.authority(),)
        return ChicagoReleaseMetadata(
            dataset_id=DATASET_ID,
            dataset_snapshot_sha256=snapshot_hash,
            operator_id="chicago-declared-one-way-k2-v2",
            methodology_reference="fixture://city-methodology/versioned",
            endpoint_clarification_reference=(
                "fixture://city-endpoint-clarification/versioned"
            ),
            tract_support=TractSupportPin(
                vintage="fixture-2020-tracts",
                support_id="fixture://tract-support/v1",
                tract_ids=self.TRACTS,
                tract_ids_sha256=support_hash,
            ),
            trip_universe=DeclaredTripUniversePin(
                universe_id="fixture://all-contributors/v1",
                node_count=len(node_ids),
                node_ids_sha256=canonical_string_set_sha256(tuple(node_ids)),
                all_cell_contributors_declared=True,
            ),
            partition_ids=(self.PARTITION,),
            partition_definition="fixture declared partition; not a City-code claim",
            time_bin_definition="fixture resolved 15-minute bin IDs",
            privacy_evidence_authorities=tuple(authorities),
            support_evidence_authorities=(self.support_authority(),),
        )

    def context(self, *, snapshot_hash=None):
        return chicago_release_context(
            self.metadata(("context-placeholder",), snapshot_hash=snapshot_hash)
        )

    def internal_factor(self, endpoint, tract=None, *, context=None):
        return ChicagoCountFactor(
            release_context=context or self.context(),
            endpoint=endpoint,
            factor_kind=INTERNAL_TRACT,
            time_bin_id="2026-01-20T08:00:00-06:00[fold=0]",
            partition_id=self.PARTITION,
            tract_id=tract or self.TRACTS[0],
        )

    def cause_factor(self, endpoint, cause, *, context=None):
        return ChicagoCountFactor(
            release_context=context or self.context(),
            endpoint=endpoint,
            factor_kind=cause,
            time_bin_id="2026-01-20T08:00:00-06:00[fold=0]",
            partition_id=self.PARTITION,
        )

    def support_declaration(
        self, bindings, *, completeness="analyst_declared_conditional"
    ):
        if completeness == "externally_verified":
            return LabelSupportDeclaration(
                bindings_sha256=canonical_label_support_sha256(bindings),
                completeness=completeness,
                authority_id=self.SUPPORT_AUTHORITY,
                evidence_reference="fixture://label-support-audit/v1",
                evidence_sha256="4" * 64,
            )
        return LabelSupportDeclaration(
            bindings_sha256=canonical_label_support_sha256(bindings),
            completeness=completeness,
        )

    def evidence(self, node_id, state, known_low_endpoints=()):
        return PrivacyCauseEvidencePin(
            subject_node_id=node_id,
            authority_id=self.AUTHORITY,
            evidence_id=f"fixture-evidence-{node_id}",
            evidence_sha256="3" * 64,
            state=state,
            known_low_endpoints=known_low_endpoints,
        )

    def trip(
        self,
        node_id,
        *,
        role="context_only",
        pickup=None,
        dropoff=None,
        pickup_factor=None,
        dropoff_factor=None,
        evidence=None,
        label=None,
        support_completeness="analyst_declared_conditional",
    ):
        pickup = pickup or EndpointReleaseObservation(None, UNKNOWN_NULL)
        dropoff = dropoff or EndpointReleaseObservation(None, UNKNOWN_NULL)
        pickup_factor = pickup_factor or self.internal_factor(PICKUP_START)
        dropoff_factor = dropoff_factor or self.internal_factor(
            DROPOFF_END, self.TRACTS[1]
        )
        bindings = {
            self.LABEL if label is None else label: {
                PICKUP_START: pickup_factor,
                DROPOFF_END: dropoff_factor,
            }
        }
        return DeclaredChicagoTrip(
            node_id=node_id,
            analysis_role=role,
            pickup=pickup,
            dropoff=dropoff,
            endpoint_factors_by_label=bindings,
            label_support=self.support_declaration(
                bindings, completeness=support_completeness
            ),
            privacy_cause_evidence=evidence,
        )

    def inputs(self, trips, *, metadata=None):
        metadata = metadata or self.metadata(
            tuple(trip.node_id for trip in trips)
        )
        return build_chicago_compiler_inputs(metadata=metadata, trips=trips)

    def source_problem(self, trips, *, edges=(), constraints=(), nodes=None):
        if nodes is None:
            nodes = tuple(
                NodeSpec(
                    trip.node_id,
                    trip.analysis_role,
                    tuple(trip.endpoint_factors_by_label),
                )
                for trip in trips
            )
        return ExactPathProblem(tuple(nodes), tuple(edges), tuple(constraints))

    def compile_problem(self, trips, inputs):
        edges = (EdgeSpec("core-buffer", "visible-core", "buffer-trip"),)
        return compile_chicago_release_problem(
            self.source_problem(trips, edges=edges),
            inputs=inputs,
            forget_order=tuple(trip.node_id for trip in trips),
        )

    def test_all_roles_count_and_handoff_freezes_nested_bindings(self):
        pickup_cell = self.internal_factor(PICKUP_START)
        dropoff_cell = self.internal_factor(DROPOFF_END, self.TRACTS[1])
        self.assertNotEqual(pickup_cell, dropoff_cell)
        trips = (
            self.trip(
                "visible-core",
                role="core",
                pickup=EndpointReleaseObservation(self.TRACTS[0], None),
                dropoff=EndpointReleaseObservation(self.TRACTS[1], None),
                pickup_factor=pickup_cell,
                dropoff_factor=dropoff_cell,
            ),
            self.trip(
                "buffer-trip",
                role="buffer",
                pickup_factor=pickup_cell,
                dropoff_factor=dropoff_cell,
            ),
            self.trip(
                "context-trip",
                pickup_factor=pickup_cell,
                dropoff_factor=dropoff_cell,
            ),
        )
        inputs = self.inputs(trips)
        self.assertEqual(
            dict(inputs.diagnostics.analysis_role_counts),
            {"buffer": 1, "context_only": 1, "core": 1},
        )
        self.assertEqual(
            inputs.diagnostics.label_support_scope,
            "analyst_declared_conditional",
        )
        self.assertFalse(
            inputs.diagnostics.label_support_outer_claim_licensed
        )
        with self.assertRaises(TypeError):
            inputs.rows[0].endpoint_factors_by_label["new"] = {}  # type: ignore[index]
        with self.assertRaises(TypeError):
            inputs.rows[0].endpoint_factors_by_label[self.LABEL][PICKUP_START] = (
                dropoff_cell  # type: ignore[index]
            )
        with self.assertRaisesRegex(ValueError, "changed after adapter validation"):
            compile_chicago_release_problem(
                self.source_problem(trips),
                inputs=replace(inputs, count_constraints=()),
                forget_order=tuple(trip.node_id for trip in trips),
            )

        handoff = self.compile_problem(trips, inputs)
        self.assertTrue(handoff.audit.exact_node_set_verified)
        self.assertTrue(handoff.audit.source_chicago_factor_maps_absent)
        compilation = handoff.compilation
        compiled_visible = next(
            node
            for node in compilation.problem.nodes
            if node.node_id == "visible-core"
        )
        compiled_label = compiled_visible.label_support[0]
        with self.assertRaises(TypeError):
            compiled_visible.factor_contributions[compiled_label][pickup_cell] = 0
        result = solve_path_frontier_endpoints(
            compilation.problem, schedule=compilation.schedule
        )
        self.assertEqual(result.status, "EXACT_OPTIMAL")
        counts = dict(result.lower_solution.witness.factor_counts)
        self.assertEqual(counts[pickup_cell], 3)
        self.assertEqual(counts[dropoff_cell], 3)

    def test_blank_true_but_paired_threshold_evidence_adds_low_or_low(self):
        pickup_cell = self.internal_factor(PICKUP_START)
        dropoff_cell = self.internal_factor(DROPOFF_END, self.TRACTS[1])
        trips = (
            self.trip(
                "visible-core",
                role="core",
                pickup=EndpointReleaseObservation(self.TRACTS[0], None),
                dropoff=EndpointReleaseObservation(self.TRACTS[1], None),
                pickup_factor=pickup_cell,
                dropoff_factor=dropoff_cell,
            ),
            self.trip(
                "buffer-trip",
                role="buffer",
                pickup_factor=pickup_cell,
                dropoff_factor=dropoff_cell,
            ),
            self.trip(
                "context-trip",
                pickup_factor=pickup_cell,
                dropoff_factor=dropoff_cell,
            ),
        )
        inputs = self.inputs(trips)
        blank_observation = inputs.rows[1].observation
        blank_implication = next(
            item
            for item in inputs.operator.implications
            if item.observation == blank_observation
        )
        self.assertEqual(blank_implication.alternatives[0].requirements, ())
        plain_handoff = self.compile_problem(trips, inputs)
        self.assertEqual(
            solve_path_frontier_endpoints(
                plain_handoff.compilation.problem,
                schedule=plain_handoff.compilation.schedule,
            ).status,
            "EXACT_OPTIMAL",
        )

        privacy_trip = self.trip(
            "buffer-trip",
            role="buffer",
            pickup=EndpointReleaseObservation(None, PRIVACY_COARSENING),
            dropoff=EndpointReleaseObservation(None, PRIVACY_COARSENING),
            pickup_factor=pickup_cell,
            dropoff_factor=dropoff_cell,
            evidence=self.evidence(
                "buffer-trip", "paired_threshold_verified"
            ),
        )
        privacy_trips = (trips[0], privacy_trip, trips[2])
        privacy_inputs = self.inputs(privacy_trips)
        implication = next(
            item
            for item in privacy_inputs.operator.implications
            if item.observation == privacy_inputs.rows[1].observation
        )
        self.assertEqual(
            {
                tuple(
                    (atom.endpoint, atom.requirement)
                    for atom in clause.requirements
                )
                for clause in implication.alternatives
            },
            {((PICKUP_START, "LOW"),), ((DROPOFF_END, "LOW"),)},
        )
        evidence_audit = privacy_inputs.diagnostics.privacy_evidence_audits[0]
        self.assertEqual(evidence_audit.evidence_sha256, "3" * 64)
        self.assertEqual(evidence_audit.authority_contract_sha256, "2" * 64)
        privacy_handoff = self.compile_problem(privacy_trips, privacy_inputs)
        self.assertEqual(
            solve_path_frontier_endpoints(
                privacy_handoff.compilation.problem,
                schedule=privacy_handoff.compilation.schedule,
            ).status,
            "EXACT_INFEASIBLE",
        )

    def test_privacy_evidence_states_preserve_single_endpoint_semantics(self):
        known = self.trip(
            "known-pickup-low",
            pickup=EndpointReleaseObservation(None, PRIVACY_COARSENING),
            dropoff=EndpointReleaseObservation(None, PRIVACY_COARSENING),
            evidence=self.evidence(
                "known-pickup-low",
                "known_low_endpoints",
                (PICKUP_START,),
            ),
        )
        known_inputs = self.inputs((known,))
        known_clause = known_inputs.operator.implications[0].alternatives[0]
        self.assertEqual(
            tuple(
                (atom.endpoint, atom.requirement)
                for atom in known_clause.requirements
            ),
            ((PICKUP_START, "LOW"),),
        )

        privacy_only = self.trip(
            "privacy-only",
            pickup=EndpointReleaseObservation(None, PRIVACY_COARSENING),
            dropoff=EndpointReleaseObservation(None, PRIVACY_COARSENING),
            evidence=self.evidence(
                "privacy-only", "privacy_only_no_low"
            ),
        )
        privacy_only_inputs = self.inputs((privacy_only,))
        self.assertEqual(
            privacy_only_inputs.operator.implications[0]
            .alternatives[0]
            .requirements,
            (),
        )
        self.assertEqual(
            privacy_only_inputs.diagnostics.privacy_evidence_audits[0].state,
            "privacy_only_no_low",
        )

    def test_evidence_requires_subject_authority_contract_and_digest(self):
        privacy = self.trip(
            "privacy",
            pickup=EndpointReleaseObservation(None, PRIVACY_COARSENING),
            dropoff=EndpointReleaseObservation(None, PRIVACY_COARSENING),
            evidence=self.evidence("privacy", "paired_threshold_verified"),
        )
        with self.subTest("authority"):
            foreign = replace(
                privacy,
                privacy_cause_evidence=replace(
                    privacy.privacy_cause_evidence,
                    authority_id="undeclared-authority",
                ),
            )
            with self.assertRaisesRegex(ValueError, "not declared in metadata"):
                self.inputs((foreign,))
        with self.subTest("subject"):
            wrong_subject = replace(
                privacy,
                privacy_cause_evidence=replace(
                    privacy.privacy_cause_evidence,
                    subject_node_id="other",
                ),
            )
            with self.assertRaisesRegex(ValueError, "subject"):
                self.inputs((wrong_subject,))
        with self.subTest("digest"):
            bad_digest = replace(
                privacy,
                privacy_cause_evidence=replace(
                    privacy.privacy_cause_evidence,
                    evidence_sha256="not-a-digest",
                ),
            )
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                self.inputs((bad_digest,))

    def test_visible_outside_and_release_context_namespace(self):
        trip = self.trip(
            "visible-one-side",
            pickup=EndpointReleaseObservation(self.TRACTS[0], None),
            dropoff=EndpointReleaseObservation(None, OUTSIDE_CITY),
            pickup_factor=self.internal_factor(PICKUP_START),
            dropoff_factor=self.cause_factor(DROPOFF_END, OUTSIDE_CITY),
        )
        inputs = self.inputs((trip,))
        requirements = inputs.operator.implications[0].alternatives[0].requirements
        self.assertEqual(
            tuple((atom.endpoint, atom.requirement) for atom in requirements),
            ((PICKUP_START, "HIGH"),),
        )
        constraints = {item.factor: item for item in inputs.count_constraints}
        pickup = trip.endpoint_factors_by_label[self.LABEL][PICKUP_START]
        dropoff = trip.endpoint_factors_by_label[self.LABEL][DROPOFF_END]
        self.assertEqual(
            (constraints[pickup].low_upper, constraints[pickup].high_lower),
            (2, 3),
        )
        self.assertEqual(
            (constraints[dropoff].low_upper, constraints[dropoff].high_lower),
            (None, None),
        )

        other_context = self.context(snapshot_hash="9" * 64)
        self.assertNotEqual(pickup, replace(pickup, release_context=other_context))
        cross_version = replace(
            trip,
            endpoint_factors_by_label={
                self.LABEL: {
                    PICKUP_START: replace(
                        pickup, release_context=other_context
                    ),
                    DROPOFF_END: dropoff,
                }
            },
        )
        cross_version = replace(
            cross_version,
            label_support=self.support_declaration(
                cross_version.endpoint_factors_by_label
            ),
        )
        with self.assertRaisesRegex(ValueError, "release context"):
            self.inputs((cross_version,))

    def test_outside_missing_and_null_causes_are_true_clauses(self):
        trips = (
            self.trip(
                "outside-missing",
                pickup=EndpointReleaseObservation(None, OUTSIDE_CITY),
                dropoff=EndpointReleaseObservation(None, SOURCE_MISSING),
                pickup_factor=self.cause_factor(PICKUP_START, OUTSIDE_CITY),
                dropoff_factor=self.cause_factor(DROPOFF_END, SOURCE_MISSING),
            ),
            self.trip(
                "other-unknown",
                pickup=EndpointReleaseObservation(None, OTHER_NULL),
                dropoff=EndpointReleaseObservation(None, UNKNOWN_NULL),
                pickup_factor=self.cause_factor(PICKUP_START, OTHER_NULL),
                dropoff_factor=self.cause_factor(DROPOFF_END, UNKNOWN_NULL),
            ),
        )
        inputs = self.inputs(trips)
        self.assertEqual(
            dict(inputs.diagnostics.blank_cause_counts),
            {
                OTHER_NULL: 1,
                OUTSIDE_CITY: 1,
                SOURCE_MISSING: 1,
                UNKNOWN_NULL: 1,
            },
        )
        for implication in inputs.operator.implications:
            self.assertEqual(implication.alternatives[0].requirements, ())
        for constraint in inputs.count_constraints:
            self.assertIsNone(constraint.low_upper)
            self.assertIsNone(constraint.high_lower)

    def test_verified_support_is_required_for_label_support_outer_flag(self):
        conditional_inputs = self.inputs((self.trip("conditional"),))
        self.assertEqual(
            conditional_inputs.diagnostics.label_support_scope,
            "analyst_declared_conditional",
        )
        self.assertFalse(
            conditional_inputs.diagnostics.label_support_outer_claim_licensed
        )

        verified = self.trip(
            "verified", support_completeness="externally_verified"
        )
        verified_inputs = self.inputs((verified,))
        self.assertEqual(
            verified_inputs.diagnostics.label_support_scope,
            "externally_verified",
        )
        self.assertTrue(
            verified_inputs.diagnostics.label_support_outer_claim_licensed
        )
        without_authority = replace(
            self.metadata(("verified",)),
            support_evidence_authorities=(),
        )
        with self.assertRaisesRegex(ValueError, "not declared in metadata"):
            self.inputs((verified,), metadata=without_authority)

    def test_ambiguous_or_unpinned_declared_inputs_fail_closed(self):
        base = self.trip("one")
        with self.subTest("tract support digest"):
            with self.assertRaisesRegex(ValueError, "tract support SHA-256"):
                self.inputs(
                    (base,),
                    metadata=self.metadata(("one",), support_hash="0" * 64),
                )
        with self.subTest("blank cause"):
            with self.assertRaisesRegex(ValueError, "explicit blank cause"):
                self.inputs(
                    (replace(base, pickup=EndpointReleaseObservation(None, None)),)
                )
        with self.subTest("privacy without evidence pin"):
            unsupported = replace(
                base,
                pickup=EndpointReleaseObservation(None, PRIVACY_COARSENING),
            )
            with self.assertRaisesRegex(ValueError, "evidence pin"):
                self.inputs((unsupported,))
        with self.subTest("label support digest"):
            wrong = replace(
                base,
                label_support=replace(
                    base.label_support, bindings_sha256="0" * 64
                ),
            )
            with self.assertRaisesRegex(ValueError, "label-support digest"):
                self.inputs((wrong,))
        with self.subTest("contributor universe"):
            metadata = self.metadata(("one",))
            wrong_metadata = replace(
                metadata,
                trip_universe=replace(
                    metadata.trip_universe,
                    node_ids_sha256=canonical_string_set_sha256(("other",)),
                ),
            )
            with self.assertRaisesRegex(ValueError, "pinned contributor universe"):
                self.inputs((base,), metadata=wrong_metadata)

    def test_informative_label_dependent_applicability_fails_closed(self):
        bindings = {
            "internal": {
                PICKUP_START: self.internal_factor(PICKUP_START),
                DROPOFF_END: self.internal_factor(
                    DROPOFF_END, self.TRACTS[1]
                ),
            },
            "outside": {
                PICKUP_START: self.internal_factor(PICKUP_START),
                DROPOFF_END: self.cause_factor(DROPOFF_END, UNKNOWN_NULL),
            },
        }
        trip = DeclaredChicagoTrip(
            node_id="one",
            analysis_role="context_only",
            pickup=EndpointReleaseObservation(self.TRACTS[0], None),
            dropoff=EndpointReleaseObservation(None, UNKNOWN_NULL),
            endpoint_factors_by_label=bindings,
            label_support=self.support_declaration(bindings),
        )
        with self.assertRaisesRegex(ValueError, "label-dependent endpoint applicability"):
            self.inputs((trip,))

    def test_sanitized_handoff_rejects_red_team_source_mismatches(self):
        trips = (self.trip("a"), self.trip("b"))
        inputs = self.inputs(trips)
        normal_nodes = tuple(
            NodeSpec(
                trip.node_id,
                trip.analysis_role,
                tuple(trip.endpoint_factors_by_label),
            )
            for trip in trips
        )
        pickup_factor = trips[0].endpoint_factors_by_label[self.LABEL][
            PICKUP_START
        ]

        def handoff(nodes=normal_nodes, constraints=()):
            return compile_chicago_release_problem(
                ExactPathProblem(tuple(nodes), (), tuple(constraints)),
                inputs=inputs,
                forget_order=("a", "b"),
            )

        with self.subTest("preloaded Chicago contribution"):
            polluted = replace(
                normal_nodes[0],
                factor_contributions={self.LABEL: {pickup_factor: 1}},
            )
            with self.assertRaisesRegex(ValueError, "preloads a Chicago factor"):
                handoff((polluted, normal_nodes[1]))
        with self.subTest("preloaded Chicago requirement"):
            polluted = replace(
                normal_nodes[0],
                factor_requirements={self.LABEL: {pickup_factor: "HIGH"}},
            )
            with self.assertRaisesRegex(ValueError, "preloads a Chicago factor"):
                handoff((polluted, normal_nodes[1]))
        with self.subTest("role mismatch"):
            with self.assertRaisesRegex(ValueError, "role"):
                handoff((replace(normal_nodes[0], role="buffer"), normal_nodes[1]))
        with self.subTest("support mismatch"):
            with self.assertRaisesRegex(ValueError, "label support"):
                handoff(
                    (
                        replace(normal_nodes[0], label_support=("rogue-label",)),
                        normal_nodes[1],
                    )
                )
        with self.subTest("rogue node"):
            rogue = NodeSpec("rogue", "context_only", (self.LABEL,))
            with self.assertRaisesRegex(ValueError, "rogue"):
                handoff(normal_nodes + (rogue,))
        with self.subTest("preloaded Chicago constraint"):
            with self.assertRaisesRegex(ValueError, "preloads a Chicago count"):
                handoff(constraints=(CountConstraint(pickup_factor, 0, 2),))
        with self.subTest("non-Chicago factors require an explicit allowlist"):
            other_factor = "declared-non-Chicago-factor"
            declared = replace(
                normal_nodes[0],
                factor_contributions={self.LABEL: {other_factor: 1}},
            )
            other_constraint = CountConstraint(other_factor, 0, 2)
            with self.assertRaisesRegex(ValueError, "undeclared source factor"):
                handoff((declared, normal_nodes[1]), (other_constraint,))
            allowed = compile_chicago_release_problem(
                ExactPathProblem(
                    (declared, normal_nodes[1]), (), (other_constraint,)
                ),
                inputs=inputs,
                forget_order=("a", "b"),
                allowed_source_factors=(other_factor,),
            )
            self.assertEqual(
                allowed.audit.declared_non_chicago_factor_count, 1
            )
            self.assertEqual(
                allowed.audit.preserved_non_chicago_constraint_count, 1
            )


if __name__ == "__main__":
    unittest.main()
