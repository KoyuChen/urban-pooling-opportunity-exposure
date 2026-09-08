import copy
import itertools
import json
from pathlib import Path
import random
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import nyc_geometry_census as census


class GeometryCensusTests(unittest.TestCase):
    def test_random_geometry_matches_independent_triple_enumeration(self):
        for seed in range(60):
            rng = random.Random(seed)
            rows = []
            for i in range(rng.randint(3, 11)):
                start = rng.randrange(10)
                rows.append(census.TimeRow(i, i == 0 or rng.random() < .3, start, start + rng.randint(1, 7)))
            result = census.geometry(rows)
            expected = 0
            for triple in itertools.combinations(rows, 3):
                edges = sum(a.start < b.end and b.start < a.end for a,b in itertools.combinations(triple,2))
                expected += edges == 2 and any(row.core for row in triple)
            self.assertEqual(result['core_incident_induced_p3_count'], expected)
            self.assertEqual(result['p3_witness_replayed'], expected > 0)

    def test_complete_clique_and_reduction_are_retained(self):
        rows = [census.TimeRow(i, i < 8, 0, 20+i) for i in range(25)]
        full, small = census.geometry(rows), census.small_view(rows)
        self.assertTrue(full['complete_clique'])
        self.assertTrue(small['complete_clique'])
        self.assertEqual(small['row_count'], 16)
        self.assertEqual(small['core_count'], 4)
        self.assertEqual(small['core_incident_induced_p3_count'], 0)

    def test_nonclique_event_does_not_claim_full_world_feasibility(self):
        rows = [census.TimeRow(0,True,0,2),census.TimeRow(1,False,1,4),
                census.TimeRow(2,False,3,5),census.TimeRow(3,True,10,11)]
        result = census.geometry(rows)
        self.assertEqual(result['core_incident_induced_p3_count'], 1)
        self.assertFalse(result['full_world_extendability_checked'])
        # An isolated compulsory core makes any world impossible despite the P3.
        self.assertEqual(result['core_component_count'], 2)

    def test_buffer_only_nonclique_component_does_not_qualify(self):
        rows = [census.TimeRow(0,True,10,12),census.TimeRow(1,False,0,2),
                census.TimeRow(2,False,1,4),census.TimeRow(3,False,3,5)]
        self.assertEqual(census.geometry(rows)['core_incident_induced_p3_count'], 0)

    def test_noninteger_time_rejected(self):
        with self.assertRaises(ValueError):
            census.geometry([census.TimeRow(0,True,0,.5)])

    def test_fixed_calendar_and_all_unstarted_denominator(self):
        protocol = json.loads(census.PROTOCOL.read_text())
        result = census.aggregate(protocol, [])
        self.assertEqual(len(result['ledger']), 24)
        self.assertEqual(result['summary']['distinct_scan_windows'], 20)
        self.assertEqual(result['summary']['status_counts'], {'NOT_STARTED':24})
        self.assertEqual(sum(w['core_count']==16 for w in protocol['windows']), 4)
        self.assertFalse(set(protocol['fields']) & {'trip_miles','trip_time','base_passenger_fare','driver_pay'})

    def test_transport_failure_is_retained_and_duplicate_rejected(self):
        protocol = json.loads(census.PROTOCOL.read_text())
        report = {'window':protocol['windows'][0], 'status':'TRANSPORT_DEADLINE',
                  'provenance':census.provenance(), 'aggregate_only':True}
        result = census.aggregate(protocol,[report])
        self.assertEqual(result['summary']['status_counts'], {'TRANSPORT_DEADLINE':1,'NOT_STARTED':23})
        with self.assertRaisesRegex(ValueError,'duplicate'):
            census.aggregate(protocol,[report,report])

    def test_deadline_is_not_scientific_ineligibility(self):
        protocol = json.loads(census.PROTOCOL.read_text())
        with tempfile.TemporaryDirectory() as folder, patch.object(census,'fetch_rows',side_effect=census.FetchDeadline()):
            result = census.run_window(protocol['windows'][0],protocol,Path(folder))
            self.assertEqual(result['status'],'TRANSPORT_DEADLINE')
            self.assertTrue((Path(folder)/'attempt_001.json').exists())

    def test_terminal_checkpoint_is_reused(self):
        protocol = json.loads(census.PROTOCOL.read_text())
        report={'window':protocol['windows'][0], 'status':'INELIGIBLE_NO_QUALIFIED_CORE',
                'provenance':census.provenance(),'aggregate_only':True}
        with tempfile.TemporaryDirectory() as folder:
            census.write_json(Path(folder)/'report.json',report)
            with patch.object(census,'fetch_rows',side_effect=AssertionError('should not fetch')):
                self.assertEqual(census.run_window(protocol['windows'][0],protocol,Path(folder)),report)


if __name__ == '__main__':
    unittest.main()
