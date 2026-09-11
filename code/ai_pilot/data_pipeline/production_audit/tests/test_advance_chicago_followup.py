import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import advance_chicago_followup as advance


class CampaignTests(unittest.TestCase):
    def rows(self, through=47):
        return [{'window_index': i, 'status': 'COMPLETED' if i <= through else 'UNSTARTED',
                 'computationally_unresolved_endpoint_pairs': 1 if i == 2 else 0}
                for i in range(96)]

    def test_advance_keeps_unresolved_and_preserves_input(self):
        rows = self.rows(); old = copy.deepcopy(rows)
        plan = advance.decide(rows, 3, 0)
        self.assertEqual(plan['selected_indices'], list(range(48, 60)))
        self.assertEqual(plan['retry_attempt'], 0)
        self.assertEqual(rows, old)

    def test_only_failed_transport_retried_and_limit_is_bounded(self):
        rows = self.rows()
        rows[38]['status'] = 'ATTEMPTED_NO_ARTIFACT'
        rows[39].update(status='EXECUTION_FAILED', failure_type='LiveDataError',
                        failure_message='request failed after retries')
        for retry in [0, 1]:
            plan = advance.decide(rows, 3, retry)
            self.assertEqual(plan['selected_indices'], [38, 39])
            self.assertEqual(plan['batch_index'], 3)
            self.assertEqual(plan['retry_attempt'], retry + 1)
        self.assertEqual(advance.decide(rows, 3, 2)['action'], 'STOP')

    def test_unstarted_failure_and_broken_predecessor_stop(self):
        for index, status in [(36, 'UNSTARTED'), (36, 'EXECUTION_FAILED'),
                              (4, 'ATTEMPTED_NO_ARTIFACT')]:
            rows = self.rows(); rows[index]['status'] = status
            self.assertEqual(advance.decide(rows, 3, 0)['action'], 'STOP')

    def test_ineligible_reused_without_replacement(self):
        rows = self.rows(); rows[40]['status'] = 'INELIGIBLE_FIXED_CORE'
        self.assertEqual(advance.decide(rows, 3, 0)['selected_indices'], list(range(48, 60)))

    def test_final_batch_stops_even_with_unresolved_endpoints(self):
        plan = advance.decide(self.rows(95), 7, 0)
        self.assertEqual(plan['reason'], 'CALENDAR_EXECUTION_COMPLETE')
        self.assertIn('not all-endpoint', plan['claim'])

    def test_duplicate_denominator_stale_seed_and_invalid_budget(self):
        rows = self.rows(); rows[95]['window_index'] = 94
        with self.assertRaises(ValueError): advance.decide(rows, 3, 0)
        self.assertEqual(advance.decide(self.rows(50), 3, 0)['action'], 'STOP')
        for batch, retry in [(8, 0), (3, -1), (3, 3)]:
            with self.assertRaises(ValueError): advance.decide(self.rows(), batch, retry)
