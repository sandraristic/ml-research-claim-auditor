from __future__ import annotations

import csv
import json
import os
import tempfile
import uuid
from claim_auditor.generic_import import generic_router
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict

from .adapters.mitm import ImportErrorDetail, import_zip
from .engine import EvidenceError, evaluate
from .schemas import Claim, Manifest, Run
from claim_auditor.regression_api import regression_router
from .report_builder import build_regression_markdown
from claim_auditor.demo_auth import install_demo_auth

MAX_UPLOAD = 8 * 1024 * 1024


class EvaluateRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    import_id: str
    claim: Claim


def _read_json(path: Path):
    return json.loads(path.read_text(encoding='utf-8'))


def _safe_uuid(value: str) -> str:
    try:
        parsed = uuid.UUID(value)
        if str(parsed) != value:
            raise ValueError
        return value
    except (ValueError, AttributeError):
        raise HTTPException(status_code=404, detail='Resource not found')


def _write_report(result: dict, out: Path):
    out.mkdir(parents=True, exist_ok=False)
    (out / 'audit.json').write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')
    evidence = result['evidence']
    with (out / 'split_evidence.csv').open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=list(evidence[0]))
        writer.writeheader()
        writer.writerows(evidence)
    claim = result['claim']
    lines = [
        '# Claim audit — descriptive only', '',
        f"Claim: {claim['challenger_method']} vs {claim['baseline_method']}",
        f"Dataset: {claim['dataset_id']}; protocol: {claim['protocol_id']}; target class: {claim['target_class']}",
        f"Test FPR limit: {claim['fpr_limit']:.2%}",
        f"Jointly feasible splits: {result['operational']['jointly_feasible']} / {result['operational']['expected_splits']}",
        f"Wins / losses / ties: {result['comparison']['wins']} / {result['comparison']['losses']} / {result['comparison']['ties']}",
        f"Finding: {result['comparison']['finding']}",
        f"Claim support: {result['claim_support']}",
        'Statistical superiority: NOT_ESTABLISHED', '',
        '## Limitations',
        *[f'- {x}' for x in result['limitations']],
    ]
    (out / 'audit.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')


def create_app(storage_dir: str | Path | None = None) -> FastAPI:
    root = Path(storage_dir or os.environ.get('CLAIM_AUDITOR_STORAGE', 'api_storage')).resolve()
    root.mkdir(parents=True, exist_ok=True)
    (root / 'imports').mkdir(exist_ok=True)
    (root / 'audits').mkdir(exist_ok=True)
    application = FastAPI(title='ML Research Claim Auditor', version='0.3.0',
                          description='Descriptive research-claim audits, not inferential superiority tests.')

    @application.get('/api/v1/health')
    def health():
        return {'status': 'ok', 'version': '0.3.0'}

    @application.post('/api/v1/datasets/import', status_code=201)
    async def import_dataset(protocol: str = Form(...), file: UploadFile = File(...)):
        if protocol not in ('corrected', 'stability'):
            raise HTTPException(status_code=422, detail='Supported protocols: corrected, stability')
        if not (file.filename or '').lower().endswith('.zip'):
            raise HTTPException(status_code=422, detail='A ZIP archive is required')
        payload = bytearray()
        try:
            while chunk := await file.read(65536):
                payload.extend(chunk)
                if len(payload) > MAX_UPLOAD:
                    raise HTTPException(status_code=413, detail='Archive is too large (8 MiB maximum)')
        finally:
            await file.close()
        if not payload:
            raise HTTPException(status_code=422, detail='Empty archive')
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / 'upload.zip'
            archive.write_bytes(payload)
            try:
                runs, manifest, warnings, sha = import_zip(archive, protocol)
            except (ImportErrorDetail, ValueError, KeyError, UnicodeError, OSError) as exc:
                raise HTTPException(status_code=422, detail=f'Invalid experiment archive: {exc}') from exc
        import_id = str(uuid.uuid4())
        folder = root / 'imports' / import_id
        folder.mkdir()
        with (folder / 'runs.csv').open('w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=list(Run.model_fields))
            writer.writeheader()
            writer.writerows([r.model_dump() for r in runs])
        (folder / 'manifest.json').write_text(manifest.model_dump_json(indent=2), encoding='utf-8')
        report = {'import_id': import_id, 'protocol': protocol, 'rows': len(runs),
                  'status': 'PASS_WITH_WARNINGS' if warnings else 'PASS',
                  'warnings': warnings, 'source_sha256': sha}
        (folder / 'import_report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        return report

    @application.get('/api/v1/datasets/{import_id}')
    def get_import(import_id: str):
        folder = root / 'imports' / _safe_uuid(import_id)
        if not (folder / 'import_report.json').is_file():
            raise HTTPException(status_code=404, detail='Import not found')
        return _read_json(folder / 'import_report.json')

    @application.get('/api/v1/datasets/{import_id}/manifest')
    def get_manifest(import_id: str):
        folder = root / 'imports' / _safe_uuid(import_id)
        file_path = folder / 'manifest.json'
        if not file_path.is_file():
            raise HTTPException(status_code=404, detail='Import not found')
        return _read_json(file_path)

    @application.post('/api/v1/claims/evaluate', status_code=201)
    def evaluate_claim(request: EvaluateRequest):
        folder = root / 'imports' / _safe_uuid(request.import_id)
        if not (folder / 'manifest.json').is_file():
            raise HTTPException(status_code=404, detail='Import not found')
        try:
            manifest = Manifest.model_validate_json((folder / 'manifest.json').read_text(encoding='utf-8'))
            with (folder / 'runs.csv').open(newline='', encoding='utf-8') as f:
                runs = [Run.model_validate({k: (None if v == '' else v) for k, v in row.items()})
                        for row in csv.DictReader(f)]
            result = evaluate(runs, manifest, request.claim)
        except (EvidenceError, ValueError, KeyError) as exc:
            raise HTTPException(status_code=422, detail=f'Evidence cannot be evaluated: {exc}') from exc
        audit_id = str(uuid.uuid4())
        _write_report(result, root / 'audits' / audit_id)
        return {'audit_id': audit_id, 'import_id': request.import_id, **result}

    @application.get('/api/v1/audits/{audit_id}')
    def get_audit(audit_id: str):
        file_path = root / 'audits' / _safe_uuid(audit_id) / 'audit.json'
        if not file_path.is_file():
            raise HTTPException(status_code=404, detail='Audit not found')
        return _read_json(file_path)

    @application.get('/api/v1/audits/{audit_id}/report')
    def get_report(audit_id: str):
        file_path = root / 'audits' / _safe_uuid(audit_id) / 'audit.md'
        if not file_path.is_file():
            raise HTTPException(status_code=404, detail='Audit not found')
        return FileResponse(file_path, media_type='text/markdown; charset=utf-8', filename='audit.md')

    @application.get('/api/v1/audits/{audit_id}/evidence')
    def get_evidence(audit_id: str):
        file_path = root / 'audits' / _safe_uuid(audit_id) / 'split_evidence.csv'
        if not file_path.is_file():
            raise HTTPException(status_code=404, detail='Audit not found')
        return FileResponse(file_path, media_type='text/csv; charset=utf-8', filename='split_evidence.csv')

    return application


app = create_app()
app.include_router(generic_router)
app.include_router(regression_router)
install_demo_auth(app)