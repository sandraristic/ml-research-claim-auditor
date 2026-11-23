import unittest
from claim_auditor.comparability import REQUIRED, assess_comparability


class ComparabilityTests(unittest.TestCase):
    def setUp(self):
        self.metadata = {key: 'sha256:sample' for key in REQUIRED}

    def test_declared_match(self):
        self.assertEqual(assess_comparability(self.metadata, self.metadata)['status'], 'DECLARED_COMPATIBLE')

    def test_explicit_conflict(self):
        changed = dict(self.metadata, test_set_fingerprint='sha256:different')
        result = assess_comparability(self.metadata, changed)
        self.assertEqual(result['status'], 'INCOMPATIBLE')
        self.assertIn('test_set_fingerprint', result['conflicts'])

    def test_missing(self):
        result = assess_comparability(self.metadata, {})
        self.assertEqual(result['status'], 'UNVERIFIED')
        self.assertEqual(set(result['missing']), set(REQUIRED))

    def test_conflict_takes_precedence_over_missing(self):
        changed = {'test_set_fingerprint': 'other'}
        self.assertEqual(assess_comparability(self.metadata, changed)['status'], 'INCOMPATIBLE')

    def test_no_metadata(self):
        self.assertEqual(assess_comparability(None, None)['status'], 'UNVERIFIED')


if __name__ == '__main__':
    unittest.main()
