"""Import two existing MITM experiment formats without altering source ZIPs."""
from __future__ import annotations
import csv, hashlib, io, json, zipfile
from pathlib import Path
from collections import Counter
from ..schemas import Run, Manifest

FILE_BY_PROTOCOL={
    'corrected':'corrected_per_split_metrics.csv',
    'stability':'per_split_metrics.csv',
}

class ImportErrorDetail(ValueError):
    pass

def _int(x):
    return int(x)

def _record(r, protocol):
    common=dict(
        dataset_id=r['dataset'], protocol_id=protocol,
        split_id=str(r['seed'] if protocol=='corrected' else r['split_seed']),
        method_id=r['method'], target_class='MITM', fpr_limit=float(r['target_fpr']),
        test_recall=float(r['test_mitm_recall']))
    if protocol=='corrected':
        common.update(test_fpr=float(r['test_fpr']), test_positive_n=_int(r['mitm_test_n']),
            test_true_positives=_int(r['test_mitm_found']),test_negative_n=_int(r['normal_test_n']),
            test_false_positives=_int(r['test_false_alarms']))
    else:
        common.update(test_fpr=float(r['test_actual_fpr']), test_positive_n=_int(r['test_n_mitm']),
            test_negative_n=_int(r['test_n_normal']),test_false_positives=_int(r['test_false_alarms']))
    return Run.model_validate(common)

def import_zip(path: str | Path, protocol: str) -> tuple[list[Run], Manifest, list[str], str]:
    path=Path(path)
    if protocol not in FILE_BY_PROTOCOL: raise ImportErrorDetail(f'Unsupported protocol: {protocol}')
    filehash=hashlib.sha256(path.read_bytes()).hexdigest()
    try:
        with zipfile.ZipFile(path) as z:
            entries=z.infolist()
            if len(entries)>100: raise ImportErrorDetail('Too many archive entries')
            if len({item.filename for item in entries})!=len(entries):
                raise ImportErrorDetail('Duplicate archive entries')
            if sum(item.file_size for item in entries)>24_000_000:
                raise ImportErrorDetail('Archive uncompressed content exceeds 24 MB')
            for item in entries:
                name=Path(item.filename)
                if (item.file_size>20_000_000 or item.filename.startswith('/')
                    or '..' in name.parts or '\\' in item.filename):
                    raise ImportErrorDetail('Unsafe archive entry')
                if item.file_size>1_000_000 and item.compress_size and item.file_size/item.compress_size>500:
                    raise ImportErrorDetail('Suspicious ZIP compression ratio')
            by_name={item.filename:item for item in entries}
            if 'protocol_and_splits.json' not in by_name or FILE_BY_PROTOCOL[protocol] not in by_name:
                raise ImportErrorDetail('Missing required experiment files')
            if by_name['protocol_and_splits.json'].file_size>1_000_000:
                raise ImportErrorDetail('Oversized metadata')
            filename=FILE_BY_PROTOCOL[protocol]
            metadata=json.loads(z.read('protocol_and_splits.json'))
            raw=z.read(filename)
    except (KeyError, zipfile.BadZipFile, EOFError, RuntimeError, json.JSONDecodeError) as exc:
        raise ImportErrorDetail(f'Missing or invalid ZIP entry: {exc}') from exc
    if b'\x00' in raw:
        raise ImportErrorDetail('NUL bytes in metrics CSV')
    reader=csv.DictReader(io.StringIO(raw.decode('utf-8-sig')))
    if not reader.fieldnames or len(reader.fieldnames)!=len(set(reader.fieldnames)):
        raise ImportErrorDetail('Missing or duplicated CSV headers')
    try:
        runs=[]
        for index,row in enumerate(reader, start=1):
            if index>100_000:
                raise ImportErrorDetail('Too many metric rows')
            if None in row:
                raise ImportErrorDetail(f'Unexpected extra CSV fields on row {index}')
            runs.append(_record(row,protocol))
    except (ValueError, TypeError, KeyError) as exc:
        raise ImportErrorDetail(f'Invalid metric record: {exc}') from exc
    splits_meta=metadata.get('splits',{})
    expected_splits={dataset:[str(s['seed']) for s in entries] for dataset,entries in splits_meta.items()}
    # Metadata specifies known split identities, without deriving them from metric rows.
    manifest=Manifest(protocol_id=protocol,target_class='MITM', expected_splits=expected_splits,
        expected_methods=['baseline','mitm_smote','mitm_weighting'],
        fpr_limits=[float(v) for v in metadata['target_fpr_budgets']],
        split_independence='not_established',provenance=str(path.name))
    found=Counter((r.dataset_id,r.split_id,r.method_id,r.fpr_limit) for r in runs)
    expected={(ds,seed,method,limit) for ds,seeds in manifest.expected_splits.items()
             for seed in seeds for method in manifest.expected_methods for limit in manifest.fpr_limits}
    problems=[]
    for key in sorted(expected-set(found)): problems.append(f'MISSING {key}')
    for key in sorted(set(found)-expected): problems.append(f'UNEXPECTED {key}')
    for key, count in found.items():
        if count!=1: problems.append(f'DUPLICATE {key}: {count}')
    if problems: raise ImportErrorDetail('; '.join(problems[:12]))
    warnings=[]
    if protocol=='stability':
        warnings.append('MITM true-positive counts unavailable; recall cannot be independently recalculated.')
        warnings.append('Legacy stability protocol filtered label-dependent conflicts globally before split.')
    warnings.append('Repeated IP-pair splits do not establish independent capture sessions.')
    return runs,manifest,warnings,filehash
