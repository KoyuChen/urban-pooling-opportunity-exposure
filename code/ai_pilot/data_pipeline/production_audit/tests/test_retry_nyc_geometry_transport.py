import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import nyc_geometry_census as census
import retry_nyc_geometry_transport as retry


class TransportAmendmentTests(unittest.TestCase):
    def make_record(self,status):
        p=json.loads(census.PROTOCOL.read_text())
        return {'window':p['windows'][9],'status':status,'provenance':census.provenance(),'aggregate_only':True}

    def test_amendment_changes_only_execution_and_retains_failed_attempt(self):
        original=json.loads(census.PROTOCOL.read_text())
        previous=self.make_record('TRANSPORT_FAILURE')
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            census.write_json(root/'report.json',previous)
            census.write_json(root/'attempt_001.json',previous)
            def run(window,protocol,output):
                self.assertEqual({k:v for k,v in protocol.items() if k!='execution'},
                                 {k:v for k,v in original.items() if k!='execution'})
                self.assertEqual(protocol['execution']['request_timeout_seconds'],120)
                self.assertEqual(protocol['execution']['window_deadline_seconds'],1800)
                return self.make_record('TRANSPORT_DEADLINE')
            with patch.object(census,'run_window',side_effect=run):
                result=retry.retry(9,root)
            self.assertEqual(json.loads((root/'attempt_001.json').read_text()),previous)
            self.assertEqual(result['transport_amendment']['prior_report_sha256'],census.sha(previous))
            self.assertTrue((root/'attempt_002.json').exists())
            self.assertTrue((root/'transport_amendment_002.json').exists())

    def test_completed_exclusion_reused_and_active_attempt_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            census.write_json(root/'report.json',self.make_record('INELIGIBLE_NO_QUALIFIED_CORE'))
            with patch.object(census,'run_window',side_effect=AssertionError('must reuse')):
                self.assertEqual(retry.retry(9,root)['status'],'INELIGIBLE_NO_QUALIFIED_CORE')
            census.write_json(root/'report.json',self.make_record('IN_PROGRESS'))
            with self.assertRaisesRegex(ValueError,'recorded transport failures'):
                retry.retry(9,root)


if __name__=='__main__':unittest.main()
