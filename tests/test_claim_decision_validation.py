"""Controlled, synthetic decision-level validation for Generic Claim Auditor.

Run from repository root:
    .venv/bin/python -m unittest discover -s . -p 'test_claim_decision_validation.py' -v

This tests rule implementation, NOT independent scientific validity.
No real datasets or production credentials are needed.
"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from claim_auditor import generic_import
from claim_auditor.comparability import REQUIRED


class ClaimDecisionValidation(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.storage = Path(self.temp.name)
        storage_patch = patch.object(generic_import, 'STORAGE', self.storage)
        storage_patch.start()
        self.addCleanup(storage_patch.stop)
        self.import_id = 'a' * 32

    def run_case(self, pairs, baseline_meta=None, challenger_meta=None, fpr_limit=0.05):
        """pairs: (split, baseline_recall, baseline_fpr, challenger_recall, challenger_fpr), None means absent."""
        rows = []
        for split, br, bf, cr, cf in pairs:
            for method, recall, fpr in [('baseline', br, bf), ('challenger', cr, cf)]:
                if recall is not None:
                    rows.append({
                        'dataset_id': 'synthetic', 'protocol_id': 'controlled',
                        'target_class': 'positive', 'split_id': split,
                        'method': method, 'recall': recall, 'fpr': fpr,
                    })
        (self.storage / (self.import_id + '.json')).write_text(
            json.dumps({'rows': rows, 'warnings': ['Synthetic controlled case.']}),
            encoding='utf-8',
        )
        req = generic_import.EvaluateRequest(
            import_id=self.import_id, dataset_id='synthetic', protocol_id='controlled',
            target_class='positive', baseline_method='baseline', challenger_method='challenger',
            fpr_limit=fpr_limit, recall_margin=0,
            baseline_metadata=baseline_meta, challenger_metadata=challenger_meta,
        )
        return generic_import.evaluate(req)

    @staticmethod
    def metadata():
        return {key: f'sha256:controlled-{key}' for key in REQUIRED}

    def test_01_declared_comparable_supported(self):
        meta = self.metadata()
        result = self.run_case([('s1', .70, .02, .80, .02), ('s2', .65, .03, .71, .03)], meta, meta)
        self.assertEqual(result['comparability']['status'], 'DECLARED_COMPATIBLE')
        self.assertEqual(result['scientific_claim_status'], 'DESCRIPTIVE_SUPPORT_ONLY')
        self.assertEqual((result['wins'], result['losses'], result['ties']), (2, 0, 0))
        self.assertEqual(result['statistical_superiority'], 'NOT_ESTABLISHED')

    def test_02_declared_comparable_not_supported(self):
        meta = self.metadata()
        result = self.run_case([('s1', .85, .02, .75, .02)], meta, meta)
        self.assertEqual(result['scientific_claim_status'], 'NOT_SUPPORTED_AS_STATED')
        self.assertEqual(result['claim_support'], 'NOT_SUPPORTED_AS_STATED')
        self.assertEqual(result['losses'], 1)

    def test_03_conflicting_metadata_blocks_claim(self):
        meta = self.metadata()
        other = dict(meta, test_set_fingerprint='different-test-set')
        result = self.run_case([('s1', .70, .02, .80, .02)], meta, other)
        self.assertEqual(result['comparability']['status'], 'INCOMPATIBLE')
        self.assertEqual(result['scientific_claim_status'], 'BLOCKED_INCOMPATIBLE')
        self.assertIn('test_set_fingerprint', result['comparability']['conflicts'])

    def test_04_missing_metadata_unverified(self):
        result = self.run_case([('s1', .70, .02, .80, .02)])
        self.assertEqual(result['comparability']['status'], 'UNVERIFIED')
        self.assertEqual(result['scientific_claim_status'], 'NOT_VERIFIED')
        self.assertEqual(result['statistical_superiority'], 'NOT_ESTABLISHED')

    def test_05_missing_pair_reported(self):
        meta = self.metadata()
        result = self.run_case([('s1', .70, .02, None, None)], meta, meta)
        self.assertEqual(result['evidence'][0]['outcome'], 'MISSING_PAIR')
        self.assertEqual(result['jointly_feasible'], 0)
        self.assertEqual(result['claim_support'], 'NOT_SUPPORTED_AS_STATED')

    def test_06_fpr_infeasible_reported(self):
        meta = self.metadata()
        result = self.run_case([('s1', .70, .02, .90, .07)], meta, meta)
        self.assertEqual(result['evidence'][0]['outcome'], 'FPR_INFEASIBLE')
        self.assertEqual(result['jointly_feasible'], 0)
        self.assertEqual(result['wins'], 0)
        self.assertEqual(result['claim_support'], 'NOT_SUPPORTED_AS_STATED')

    def test_07_mixed_outcomes_do_not_support_claim(self):
        meta = self.metadata()
        result = self.run_case([('s1', .70, .02, .80, .02), ('s2', .85, .02, .75, .02)], meta, meta)
        self.assertEqual(result['finding'], 'MIXED')
        self.assertEqual((result['wins'], result['losses']), (1, 1))
        self.assertEqual(result['claim_support'], 'NOT_SUPPORTED_AS_STATED')

    def test_08_exact_threshold_is_feasible(self):
        meta = self.metadata()
        result = self.run_case([('s1', .70, .05, .80, .05)], meta, meta)
        self.assertEqual(result['evidence'][0]['outcome'], 'WIN')
        self.assertEqual(result['jointly_feasible'], 1)


if __name__ == '__main__':
    unittest.main()
