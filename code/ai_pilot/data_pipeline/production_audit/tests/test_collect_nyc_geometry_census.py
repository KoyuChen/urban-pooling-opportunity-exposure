import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import nyc_geometry_census as census
import collect_nyc_geometry_census as collector


class CollectorTests(unittest.TestCase):
    def test_missing_records_use_observed_job_states(self):
        p=json.loads(census.PROTOCOL.read_text())
        jobs=[{'id':i,'name':f'geometry-window ({i})','status':s,'conclusion':c}
              for i,(s,c) in enumerate([('queued',None),('in_progress',None),('completed','success'),('completed','failure')])]
        report=collector.annotate(census.aggregate(p,[]),jobs)
        self.assertEqual([r['status'] for r in report['ledger'][:5]],
                         ['QUEUED','IN_PROGRESS_REMOTE','AWAITING_ARTIFACT_RETRIEVAL','MISSING_REPORT_AFTER_JOB','NO_OBSERVED_RECORD_OR_JOB'])
        self.assertEqual(sum(report['summary']['status_counts'].values()),24)
        self.assertEqual(report['summary']['full']['eligible_views'],0)

    def test_scientific_exclusion_is_not_overwritten_by_green_job(self):
        p=json.loads(census.PROTOCOL.read_text())
        row={'window':p['windows'][0],'status':'INELIGIBLE_NO_QUALIFIED_CORE',
             'provenance':census.provenance(),'aggregate_only':True}
        report=collector.annotate(census.aggregate(p,[row]),[
            {'id':1,'name':'geometry-window (0)','status':'completed','conclusion':'success'}])
        self.assertEqual(report['ledger'][0]['status'],'INELIGIBLE_NO_QUALIFIED_CORE')
        self.assertNotIn('workflow_job', row)
        self.assertNotIn('collector_sha256', row['provenance'])


if __name__=='__main__': unittest.main()
