import os
import unittest
from unittest.mock import patch
from scripts.benchmark_api import dataset,fingerprint,run

class MeasurementTests(unittest.TestCase):
    def test_invalid_or_unconfirmed_workloads_never_open_database(self):
        with patch('scripts.benchmark_api.psycopg.connect') as connect:
            for kwargs in ({},{'disposable':True,'rows':201},{'disposable':True,'rows':True},{'disposable':True,'repeats':0},{'disposable':True,'requests':26},{'disposable':True,'port':0}):
                with self.assertRaises(ValueError):run(**kwargs)
            with patch.dict(os.environ,{'PGHOST':'outside.invalid'}):
                with self.assertRaises(ValueError):run(disposable=True)
            connect.assert_not_called()

    def test_fixture_is_deterministic_disjoint_and_bounded(self):
        rows=dataset(10)
        self.assertEqual(len(rows),20);self.assertEqual(len({row['id'] for row in rows}),20)
        self.assertEqual(fingerprint(rows),fingerprint(dataset(10)))
        self.assertNotEqual(fingerprint(rows),fingerprint(dataset(11)))
        self.assertEqual(sum(row['status']=='open' for row in rows),10)
        self.assertEqual({row['created_by'] for row in rows},{'alice','sam'})
