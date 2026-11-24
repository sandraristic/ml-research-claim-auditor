import argparse
import csv
import io
import json
import math
import mimetypes
import sys
import uuid
import zipfile
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

SCHEMAS = {
    'corrected': {'csv': 'corrected_per_split_metrics.csv', 'split': 'seed', 'fpr': 'test_fpr'},
    'stability': {'csv': 'per_split_metrics.csv', 'split': 'split_seed', 'fpr': 'test_actual_fpr'},
}
FIELDNAMES = ['dataset_id', 'protocol_id', 'target_class', 'split_id', 'method', 'recall', 'fpr']
TOLERANCE = 1e-10


def read_rows(archive, protocol, target_fpr):
    spec = SCHEMAS[protocol]
    with zipfile.ZipFile(archive) as zf:
        member = spec['csv']
        if member not in zf.namelist() or 'protocol_and_splits.json' not in zf.namelist():
            raise ValueError(f'{archive.name}: missing {member} or protocol_and_splits.json')
        reader = csv.DictReader(io.StringIO(zf.read(member).decode('utf-8-sig')))
        required = {'dataset', 'method', 'target_fpr', spec['split'], spec['fpr'], 'test_mitm_recall'}
        if not reader.fieldnames or required - set(reader.fieldnames):
            raise ValueError(f'{archive.name}: missing columns {required - set(reader.fieldnames or [])}')
        output = []
        seen = set()
        for line, raw in enumerate(reader, 2):
            try:
                selected = float(raw['target_fpr'])
            except (TypeError, ValueError) as e:
                raise ValueError(f'Line {line}: invalid target FPR') from e
            if not math.isfinite(selected):
                raise ValueError(f'Line {line}: nonfinite target FPR')
            if not math.isclose(selected, target_fpr, abs_tol=1e-10, rel_tol=0):
                continue
            dataset, method, split = (str(raw[k]).strip() for k in ('dataset', 'method', spec['split']))
            try:
                recall, fpr = float(raw['test_mitm_recall']), float(raw[spec['fpr']])
            except (TypeError, ValueError) as e:
                raise ValueError(f'Line {line}: invalid metric') from e
            if not all((dataset, method, split)) or any(not math.isfinite(x) or not 0 <= x <= 1 for x in (recall, fpr)):
                raise ValueError(f'Line {line}: invalid key or metric')
            key = (dataset, protocol, 'MITM', split, method)
            if key in seen:
                raise ValueError(f'Line {line}: duplicate canonical key {key}')
            seen.add(key)
            output.append(dict(zip(FIELDNAMES, (*key, repr(recall), repr(fpr)))))
    if not output:
        raise ValueError(f'No records selected for {protocol} at target FPR={target_fpr}')
    return output


def http_json(base, method, path, payload=None, filename=None, form_fields=None):
    # In-process mode for the secured regression endpoint. The outer endpoint
    # has already been authorized by the production demo-auth middleware.
    # This makes NO network calls, and does not forward or embed credentials.
    if not isinstance(base, str):
        if filename is not None:
            file_path = Path(filename)
            with file_path.open('rb') as handle:
                response = base.request(
                    method, path,
                    data=form_fields or {},
                    files={'file': (file_path.name, handle, 'application/octet-stream')},
                )
        else:
            response = base.request(method, path, json=payload)
        if response.status_code >= 400:
            raise RuntimeError(
                f'{method} {path}: HTTP {response.status_code}: '
                f'{response.text[:1500]}'
            )
        return response.json()

    url = base.rstrip('/') + path
    headers = {}
    body = None
    if filename is not None:
        boundary = '----auditor-' + uuid.uuid4().hex
        chunks = []
        for key, val in (form_fields or {}).items():
            chunks.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{val}\r\n'.encode())
        data = Path(filename).read_bytes()
        chunks += [f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{Path(filename).name}"\r\nContent-Type: application/octet-stream\r\n\r\n'.encode(), data, f'\r\n--{boundary}--\r\n'.encode()]
        body = b''.join(chunks)
        headers['Content-Type'] = f'multipart/form-data; boundary={boundary}'
    elif payload is not None:
        body = json.dumps(payload).encode('utf-8')
        headers['Content-Type'] = 'application/json'
    request = Request(url, data=body, headers=headers, method=method)
    try:
        with urlopen(request, timeout=60) as response:
            return json.loads(response.read().decode('utf-8'))
    except HTTPError as e:
        raise RuntimeError(f'{method} {path}: HTTP {e.code}: {e.read().decode("utf-8", errors="replace")[:1500]}') from e
    except URLError as e:
        raise RuntimeError(f'{method} {path}: connection failed: {e.reason}') from e


def to_csv_bytes(rows):
    sink = io.StringIO(newline='')
    writer = csv.DictWriter(sink, fieldnames=FIELDNAMES)
    writer.writeheader()
    writer.writerows(rows)
    return sink.getvalue().encode('utf-8')


def normalize_outcome(value):
    label = str(value or '').upper().replace(' ', '_').replace('-', '_')
    if label in {'FPR_INFEASIBLE', 'NOT_JOINTLY_ELIGIBLE', 'NOT_JOINTLY_FEASIBLE', 'INELIGIBLE'}:
        return 'FPR_INFEASIBLE'
    return label


def canonical_evidence(data):
    items = data.get('evidence')
    if not isinstance(items, list):
        raise ValueError('Audit response has no evidence list')
    result = {}
    for ev in items:
        sid = str(ev['split_id'])
        if sid in result:
            raise ValueError(f'Duplicate evidence split: {sid}')
        result[sid] = {
            'baseline_fpr': ev.get('baseline_fpr'),
            'challenger_fpr': ev.get('challenger_fpr'),
            'baseline_recall': ev.get('baseline_recall'),
            'challenger_recall': ev.get('challenger_recall'),
            'recall_delta': ev.get('recall_delta'),
            'outcome': normalize_outcome(ev.get('outcome')),
        }
    return result


def summary(audit, legacy=False):
    if legacy:
        ops, comp = audit['operational'], audit['comparison']
        return {'jointly_feasible': ops['jointly_feasible'], 'wins': comp['wins'],
                'losses': comp['losses'], 'ties': comp['ties']}
    return {key: audit[key] for key in ('jointly_feasible', 'wins', 'losses', 'ties')}


def compare_audits(legacy, generic):
    failures = []
    x, y = canonical_evidence(legacy), canonical_evidence(generic)
    if set(x) != set(y):
        failures.append(f'Split IDs differ: only legacy={sorted(set(x)-set(y))}; only generic={sorted(set(y)-set(x))}')
    for sid in sorted(set(x) & set(y)):
        for field in x[sid]:
            a, b = x[sid][field], y[sid][field]
            if field == 'outcome':
                if a != b:
                    failures.append(f'Split {sid} {field}: {a} != {b}')
            elif (a is None) != (b is None):
                # Older MITM audits may omit separate recall values; in that
                # case compare the supplied recall delta, FPR and outcome.
                if field not in {'baseline_recall', 'challenger_recall'}:
                    failures.append(f'Split {sid} {field}: {a} != {b}')
            elif a is not None and not math.isclose(float(a), float(b), rel_tol=0, abs_tol=TOLERANCE):
                failures.append(f'Split {sid} {field}: {a} != {b}')
    a, b = summary(legacy, True), summary(generic)
    for key in a:
        if a[key] != b[key]:
            failures.append(f'Summary {key}: {a[key]} != {b[key]}')
    if legacy.get('statistical_superiority') != generic.get('statistical_superiority'):
        failures.append('Statistical-superiority status differs')
    legacy_support = legacy.get('claim_support')
    generic_support = generic.get('claim_support')
    if legacy_support != generic_support:
        failures.append(
            f'Claim-support status differs: '
            f'M5={legacy_support!r}, Generic={generic_support!r}'
        )
    return failures


def import_generic(base, rows):
    import tempfile
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / 'mitm_generic.csv'
        path.write_bytes(to_csv_bytes(rows))
        preview = http_json(base, 'POST', '/api/v1/generic/preview', filename=path)
    if preview['row_count'] != len(rows):
        raise AssertionError('Generic preview row count mismatch')
    imported = http_json(base, 'POST', '/api/v1/generic/import', {
        'preview_id': preview['preview_id'], 'mapping': {field: field for field in FIELDNAMES},
        'comparison_metadata_confirmed': False,
    })
    if imported['rows'] != len(rows):
        raise AssertionError('Generic import row count mismatch')
    return imported['import_id']


def run(base, archive, protocol, target):
    rows = read_rows(archive, protocol, target)
    print(f'\n[{protocol}] {len(rows)} rows at target FPR={target:g}')
    legacy_import = http_json(base, 'POST', '/api/v1/datasets/import', filename=archive, form_fields={'protocol': protocol})
    manifest = http_json(base, 'GET', f'/api/v1/datasets/{legacy_import["import_id"]}/manifest')
    generic_id = import_generic(base, rows)
    combos = sorted({(r['dataset_id'], r['method']) for r in rows if r['method'] != 'baseline'})
    failures = []
    for dataset, challenger in combos:
        expected = [str(s) for s in manifest['expected_splits'][dataset]]
        claim = {'claim_type': 'conditional_recall_advantage', 'dataset_id': dataset,
                 'protocol_id': manifest['protocol_id'], 'target_class': manifest['target_class'],
                 'baseline_method': 'baseline', 'challenger_method': challenger,
                 'fpr_limit': target, 'recall_margin': 0.0, 'expected_split_ids': expected}
        legacy = http_json(base, 'POST', '/api/v1/claims/evaluate',
                           {'import_id': legacy_import['import_id'], 'claim': claim})
        generic = http_json(base, 'POST', '/api/v1/generic/evaluate', {
            'import_id': generic_id, 'dataset_id': dataset, 'protocol_id': protocol,
            'target_class': 'MITM', 'baseline_method': 'baseline', 'challenger_method': challenger,
            'fpr_limit': target, 'recall_margin': 0.0})
        problems = compare_audits(legacy, generic)
        label = f'{protocol}/{dataset}/baseline-vs-{challenger}'
        if problems:
            print(f'  FAIL {label} ({len(problems)} differences)')
            failures.extend(f'{label}: {p}' for p in problems)
        else:
            print(f'  PASS {label} — {summary(generic)}; {len(generic["evidence"])} splits')
    return failures, len(combos)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', default='http://127.0.0.1:8001')
    parser.add_argument('--corrected', type=Path, required=True)
    parser.add_argument('--stability', type=Path, required=True)
    parser.add_argument('--target-fpr', type=float, default=0.01)
    args = parser.parse_args()
    if not (math.isfinite(args.target_fpr) and 0 <= args.target_fpr <= 1):
        parser.error('--target-fpr must be in [0,1]')
    failed, total = [], 0
    try:
        for protocol in SCHEMAS:
            problems, count = run(args.base_url, getattr(args, protocol), protocol, args.target_fpr)
            failed.extend(problems)
            total += count
    except (RuntimeError, ValueError, KeyError, TypeError, AssertionError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 2
    if failed:
        print('\nREGRESSION FAILED:')
        for issue in failed:
            print(f' - {issue}')
        return 1
    print(f'\nALL {total} COMPARISONS PASSED (FPR, recall, split outcomes, summaries).')
    print('This checks software consistency, not statistical significance or protocol comparability.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
