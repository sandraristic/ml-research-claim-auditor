import io
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import generic_import as mod

CSV = b'dataset,protocol,target,split,model,recall,fpr\nTON,corrected,MITM,1,baseline,0.80,0.005\nTON,corrected,MITM,1,weighting,0.95,0.007\nTON,corrected,MITM,2,baseline,0.80,0.005\nTON,corrected,MITM,2,weighting,0.70,0.007\n'

class GenericImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.original = mod.STORAGE
        mod.STORAGE = Path(self.temp.name)
        app = FastAPI()
        app.include_router(mod.router)
        self.client = TestClient(app)

    def tearDown(self):
        mod.STORAGE = self.original
        self.temp.cleanup()

    def load(self, payload=CSV, filename='results.csv'):
        res = self.client.post('/api/v1/generic/preview', files={'file': (filename, payload)})
        self.assertEqual(res.status_code, 200, res.text)
        data = res.json()
        committed = self.client.post('/api/v1/generic/import', json={'preview_id': data['preview_id'], 'mapping': data['suggested_mapping']})
        return committed

    def test_csv_import_and_compare(self):
        res = self.load()
        self.assertEqual(res.status_code, 200, res.text)
        self.assertEqual(res.json()['rows'], 4)
        result = self.client.post('/api/v1/generic/evaluate', json={'import_id': res.json()['import_id'], 'dataset_id': 'TON', 'protocol_id': 'corrected', 'target_class': 'MITM', 'baseline_method': 'baseline', 'challenger_method': 'weighting', 'fpr_limit': 0.01})
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual((result.json()['wins'], result.json()['losses'], result.json()['jointly_feasible']), (1, 1, 2))
        self.assertEqual(result.json()['statistical_superiority'], 'NOT_ESTABLISHED')

    def test_zip(self):
        content = io.BytesIO()
        with zipfile.ZipFile(content, 'w') as archive:
            archive.writestr('results.csv', CSV)
        self.assertEqual(self.load(content.getvalue(), 'results.zip').status_code, 200)

    def test_invalid_metric(self):
        result = self.load(CSV.replace(b'0.95', b'1.95'))
        self.assertEqual(result.status_code, 422)

    def test_duplicate_rejected(self):
        result = self.load(CSV + b'TON,corrected,MITM,1,baseline,0.80,0.005\n')
        self.assertEqual(result.status_code, 422)

    def test_invalid_zip_multiple_csv(self):
        content = io.BytesIO()
        with zipfile.ZipFile(content, 'w') as archive:
            archive.writestr('a.csv', CSV)
            archive.writestr('b.csv', CSV)
        response = self.client.post('/api/v1/generic/preview', files={'file': ('two.zip', content.getvalue())})
        self.assertEqual(response.status_code, 422)

    def test_no_comparison_across_protocols(self):
        res = self.load(CSV.replace(b'2,weighting', b'2,weighting').replace(b'corrected,MITM,2,weighting', b'stability,MITM,2,weighting'))
        self.assertEqual(res.status_code, 200)
        result = self.client.post('/api/v1/generic/evaluate', json={'import_id': res.json()['import_id'], 'dataset_id': 'TON', 'protocol_id': 'corrected', 'target_class': 'MITM', 'baseline_method': 'baseline', 'challenger_method': 'weighting', 'fpr_limit': 0.01})
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()['jointly_feasible'], 1)
        self.assertEqual(result.json()['evidence'][1]['outcome'], 'MISSING_PAIR')

if __name__ == '__main__': unittest.main()
