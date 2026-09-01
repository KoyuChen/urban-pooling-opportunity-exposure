import importlib.util
import json
import sys
import unittest
from dataclasses import replace
from datetime import datetime
from pathlib import Path


MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "live_chicago_release_operator_audit.py"
)
SPEC = importlib.util.spec_from_file_location("live_release_operator_audit", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
AUDIT = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = AUDIT
SPEC.loader.exec_module(AUDIT)


def public_row(
    trip_id,
    start="2026-01-13T17:30:00.000",
    end="2026-01-13T18:00:00.000",
    *,
    matched="true",
    pooled="2",
    pickup_tract="17031010100",
    dropoff_tract="17031010200",
    pickup_area="8",
    dropoff_area="32",
    pickup_lat="41.9",
    pickup_lon="-87.6",
    dropoff_lat="41.8",
    dropoff_lon="-87.7",
):
    return {
        "trip_id": trip_id,
        "trip_start_timestamp": start,
        "trip_end_timestamp": end,
        "pickup_census_tract": pickup_tract,
        "dropoff_census_tract": dropoff_tract,
        "pickup_community_area": pickup_area,
        "dropoff_community_area": dropoff_area,
        "pickup_centroid_latitude": pickup_lat,
        "pickup_centroid_longitude": pickup_lon,
        "dropoff_centroid_latitude": dropoff_lat,
        "dropoff_centroid_longitude": dropoff_lon,
        "shared_trip_match": matched,
        "trips_pooled": pooled,
    }


def snapshot():
    return AUDIT.Snapshot(
        dataset_id=AUDIT.DATASET_ID,
        rows_updated_at=1,
        view_last_modified=2,
        publication_date=3,
        schema_sha256="a" * 64,
        required_column_descriptions_sha256="b" * 64,
        revision_fingerprint_sha256="c" * 64,
        public_column_count=24,
    )


class LiveChicagoReleaseOperatorAuditTests(unittest.TestCase):
    def test_snapshot_requires_public_fields_and_omits_linkage_keys(self):
        metadata = {
            "id": AUDIT.DATASET_ID,
            "rowsUpdatedAt": 1,
            "viewLastModified": 2,
            "publicationDate": 3,
            "columns": [
                {
                    "position": index,
                    "fieldName": field,
                    "dataTypeName": "text",
                    "description": f"description-{field}",
                }
                for index, field in enumerate(AUDIT.PUBLIC_FIELDS)
            ],
        }
        result = AUDIT.snapshot_from_metadata(metadata)
        self.assertEqual(result.dataset_id, AUDIT.DATASET_ID)
        self.assertEqual(result.public_column_count, len(AUDIT.PUBLIC_FIELDS))
        self.assertEqual(len(result.schema_sha256), 64)

        missing = json.loads(json.dumps(metadata))
        missing["columns"] = missing["columns"][:-1]
        with self.assertRaisesRegex(AUDIT.AuditError, "required public fields"):
            AUDIT.snapshot_from_metadata(missing)

        forbidden = json.loads(json.dumps(metadata))
        forbidden["columns"].append(
            {"position": 999, "fieldName": "shared_trip_id", "dataTypeName": "text"}
        )
        with self.assertRaisesRegex(AUDIT.AuditError, "linkage fields"):
            AUDIT.snapshot_from_metadata(forbidden)

    def test_timestamp_integrity_fails_closed(self):
        with self.assertRaisesRegex(AUDIT.AuditError, "duplicate"):
            AUDIT.parse_rows([public_row("same"), public_row("same")])
        with self.assertRaisesRegex(AUDIT.AuditError, "off-grid"):
            AUDIT.parse_rows(
                [public_row("off-grid", start="2026-01-13T17:31:00.000")]
            )
        with self.assertRaisesRegex(AUDIT.AuditError, "DST-ambiguous"):
            AUDIT.parse_rows(
                [
                    public_row(
                        "fall-back",
                        start="2026-11-01T01:00:00.000",
                        end="2026-11-01T01:15:00.000",
                    )
                ]
            )
        with self.assertRaisesRegex(AUDIT.AuditError, "precedes"):
            AUDIT.parse_rows(
                [
                    public_row(
                        "reverse",
                        start="2026-01-13T18:00:00.000",
                        end="2026-01-13T17:45:00.000",
                    )
                ]
            )

    def test_strict_positive_overlap_separates_boundary_touch(self):
        rows = AUDIT.parse_rows(
            [
                public_row(
                    "left",
                    start="2026-01-13T10:00:00.000",
                    end="2026-01-13T10:15:00.000",
                ),
                public_row(
                    "right",
                    start="2026-01-13T10:30:00.000",
                    end="2026-01-13T10:45:00.000",
                ),
            ]
        )
        self.assertTrue(AUDIT.temporal_compatible(rows[0], rows[1], strict=False))
        self.assertFalse(AUDIT.temporal_compatible(rows[0], rows[1], strict=True))
        closed = AUDIT.build_candidate_edges(rows, (0,), strict=False)
        strict = AUDIT.build_candidate_edges(rows, (0,), strict=True)
        self.assertEqual(len(closed), 1)
        self.assertEqual(len(strict), 0)

    def test_two_strict_core_covers_change_core_assignments_without_world_claim(self):
        rows = AUDIT.parse_rows(
            [public_row("core-a"), public_row("core-b"), public_row("buffer-a"), public_row("buffer-b")]
        )
        certificate = AUDIT.pairing_certificate(
            rows, (0, 1), solver_time_limit=10.0
        )
        self.assertEqual(certificate["strict_graph_cover_status"], AUDIT.OPTIMAL_MILP)
        self.assertEqual(
            certificate["alternative_strict_cover_status"], AUDIT.OPTIMAL_MILP
        )
        self.assertEqual(
            certificate["strict_core_cover_multiplicity_status"],
            "CERTIFIED_TWO_DISTINCT_STRICT_CORE_COVERS",
        )
        self.assertGreater(certificate["cores_changed_between_displayed_covers"], 0)
        self.assertTrue(
            certificate["release_map_pairing_invariant_under_documented_abstraction"]
        )
        self.assertFalse(certificate["full_hidden_worlds_constructed"])
        self.assertFalse(certificate["shared_exact_timestamp_witness_constructed"])
        self.assertFalse(certificate["remaining_buffer_run_completion_constructed"])
        self.assertEqual(certificate["hidden_partner_identification_claim"], "NONE")
        self.assertEqual(certificate["release_prunable_unmeasured_edges"], 0)
        self.assertFalse(certificate["witnesses_serialized"])

    def test_endpoint_masks_do_not_invert_blank_cause(self):
        rows = AUDIT.parse_rows(
            [
                public_row(
                    "tract-centroid",
                    pickup_tract="17031010100",
                    pickup_area="8",
                    pickup_lat="41.9",
                    pickup_lon="-87.6",
                ),
                public_row(
                    "area-centroid",
                    pickup_tract="",
                    pickup_area="8",
                    pickup_lat="41.9",
                    pickup_lon="-87.6",
                ),
                public_row(
                    "unknown-null",
                    pickup_tract="",
                    pickup_area="",
                    pickup_lat="",
                    pickup_lon="",
                ),
                public_row(
                    "partial",
                    pickup_tract="",
                    pickup_area="8",
                    pickup_lat="41.9",
                    pickup_lon="",
                ),
            ]
        )
        summary = AUDIT.summarize_endpoint_masks(rows, "pickup")
        self.assertEqual(summary["partial_lat_lon_rows"], 1)
        self.assertEqual(summary["area_without_coordinates_rows"], 1)
        self.assertFalse(summary["area_coordinate_presence_masks_equal"])
        self.assertEqual(sum(summary["cross_tab"].values()), 4)

    def test_live_report_is_count_closed_redacted_and_nonidentifying(self):
        core = [public_row("core-a"), public_row("core-b")]
        candidates = core + [public_row("buffer-a"), public_row("buffer-b")]
        contributors = candidates + [
            public_row("ordinary-trip", matched="false", pooled="1")
        ]
        result = AUDIT.build_report(
            snapshot_before=snapshot(),
            snapshot_after=snapshot(),
            core_start=datetime(2026, 1, 13, 17, 30),
            core_raw=core,
            candidate_raw=candidates,
            contributor_raw=contributors,
            expected_candidate_count=4,
            confirmed_candidate_count=4,
            expected_contributor_count=5,
            confirmed_contributor_count=5,
            candidate_api_paths=("mock",),
            contributor_api_paths=("mock",),
            generated_at_utc="2026-09-01T00:00:00+00:00",
            solver_time_limit=10.0,
        )
        self.assertEqual(result["overall_status"], AUDIT.STATUS_PARTIAL)
        self.assertTrue(result["extraction"]["candidate_count_closed"])
        self.assertTrue(
            result["extraction"]["all_public_contributors_count_closed"]
        )
        self.assertEqual(result["documentation"]["low_literals_emitted"], 0)
        self.assertFalse(result["documentation"]["city_implementation_validated"])
        self.assertFalse(result["documentation"]["converse_licensed"])
        self.assertEqual(
            result["candidate_support_consequence"]["release_prunable_unmeasured_edges"],
            0,
        )
        serialized = json.dumps(result, sort_keys=True)
        for raw_id in ("core-a", "core-b", "buffer-a", "buffer-b", "ordinary-trip"):
            self.assertNotIn(raw_id, serialized)
        markdown = AUDIT.render_markdown(result)
        self.assertIn("not two fully constructed", markdown)
        self.assertIn("CERTIFIED_TWO_DISTINCT_STRICT_CORE_COVERS", markdown)

    def test_snapshot_or_count_drift_fails_closed(self):
        core = [public_row("core-a"), public_row("core-b")]
        candidates = core + [public_row("buffer-a"), public_row("buffer-b")]
        kwargs = dict(
            snapshot_before=snapshot(),
            snapshot_after=snapshot(),
            core_start=datetime(2026, 1, 13, 17, 30),
            core_raw=core,
            candidate_raw=candidates,
            contributor_raw=candidates,
            expected_candidate_count=4,
            confirmed_candidate_count=4,
            expected_contributor_count=4,
            confirmed_contributor_count=4,
            candidate_api_paths=("mock",),
            contributor_api_paths=("mock",),
            generated_at_utc="2026-09-01T00:00:00+00:00",
            solver_time_limit=10.0,
        )
        with self.assertRaisesRegex(AUDIT.AuditError, "snapshot changed"):
            AUDIT.build_report(
                **{
                    **kwargs,
                    "snapshot_after": replace(snapshot(), rows_updated_at=999),
                }
            )
        with self.assertRaisesRegex(AUDIT.AuditError, "candidate server count"):
            AUDIT.build_report(
                **{**kwargs, "confirmed_candidate_count": 3}
            )
        with self.assertRaisesRegex(AUDIT.AuditError, "contributor server count"):
            AUDIT.build_report(
                **{**kwargs, "confirmed_contributor_count": 3}
            )

    def test_abstract_witness_changes_only_confidential_pairing(self):
        witness = AUDIT.documentary_nonidentification_certificate()
        self.assertEqual(witness["minimum_abstract_witness_nodes"], 4)
        self.assertTrue(witness["same_documented_public_release"])
        self.assertTrue(witness["different_hidden_pairing"])
        self.assertIn(
            "Shared Trip ID assignment",
            witness["confidential_linkages_allowed_to_change"],
        )
        self.assertEqual(
            witness["scope"], "ABSTRACT_FOUR_ROW_CONSTRUCTION_NOT_COHORT_COMPLETION"
        )


if __name__ == "__main__":
    unittest.main()
