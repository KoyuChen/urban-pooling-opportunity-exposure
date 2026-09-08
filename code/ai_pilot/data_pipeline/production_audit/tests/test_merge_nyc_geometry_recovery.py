import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import nyc_geometry_census as census
import retry_nyc_geometry_transport as transport
import merge_nyc_geometry_recovery as merger


class GeometryRecoveryMergeTests(unittest.TestCase):
    def setup_records(self,status='TRANSPORT_FAILURE'):
        protocol=json.loads(census.PROTOCOL.read_text())
        base={'window':protocol['windows'][9],'status':status,'provenance':census.provenance(),'aggregate_only':True}
        retry=copy.deepcopy(base)
        retry['status']='INELIGIBLE_NO_QUALIFIED_CORE'
        retry['transport_amendment']={
            'prior_report_sha256':census.sha(base),
            'amendment_sha256':census.file_sha(transport.AMENDMENT),
            'execution_overrides':json.loads(transport.AMENDMENT.read_text())['execution_overrides'],
            'retry_launcher_sha256':census.file_sha(Path(transport.__file__)),
        }
        return protocol,base,retry

    def test_transport_recovery_keeps_full_denominator(self):
        p,b,r=self.setup_records()
        result=merger.merge({9:b},{9:r},p)
        self.assertEqual(result['summary']['status_counts'],{'NOT_STARTED':23,'INELIGIBLE_NO_QUALIFIED_CORE':1})
        self.assertEqual(result['ledger'][9]['transport_amendment']['prior_report_sha256'],census.sha(b))

    def test_bad_predecessor_and_changed_terminal_record_rejected(self):
        p,b,r=self.setup_records()
        r['transport_amendment']['prior_report_sha256']='wrong'
        with self.assertRaisesRegex(ValueError,'predecessor'):merger.merge({9:b},{9:r},p)
        p,b,r=self.setup_records('INELIGIBLE_NO_QUALIFIED_CORE')
        with self.assertRaisesRegex(ValueError,'completed scientific'):merger.merge({9:b},{9:r},p)


if __name__=='__main__':unittest.main()
