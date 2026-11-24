"""Regression endpoint: compare legacy MITM and Generic Import implementations.

The external route is protected by the production middleware installed in api.py.
Comparison requests execute against a private in-process test ASGI app so they
never depend on Render's port, public HTTP calls, or demo credentials.
"""
import contextlib
import io
import math
import tempfile
import threading
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.testclient import TestClient

from .regression_compare import SCHEMAS, run
from .report_builder import build_regression_markdown

regression_router = APIRouter(
    prefix='/api/v1/regression',
    tags=['Regression tests'],
)

_lock = threading.Lock()
MAX_ARCHIVE_BYTES = 8 * 1024 * 1024


def _save_zip(upload, dest):
    if not upload.filename or not upload.filename.lower().endswith('.zip'):
        raise HTTPException(
            status_code=422,
            detail='Please upload a ZIP file for each protocol.',
        )
    length = 0
    with dest.open('wb') as handle:
        while True:
            chunk = upload.file.read(1024 * 1024)
            if not chunk:
                break
            length += len(chunk)
            if length > MAX_ARCHIVE_BYTES:
                raise HTTPException(
                    status_code=413,
                    detail='ZIP archive exceeds 8 MiB.',
                )
            handle.write(chunk)
    if not length:
        raise HTTPException(
            status_code=422,
            detail='Empty ZIP archive.',
        )


@regression_router.post('/run')
def run_regression(
    corrected: UploadFile = File(...),
    stability: UploadFile = File(...),
    target_fpr: float = Form(0.01),
):
    if not math.isfinite(target_fpr) or not (0 < target_fpr <= 1):
        raise HTTPException(
            status_code=422,
            detail='target_fpr must be within (0, 1].',
        )

    if not _lock.acquire(blocking=False):
        raise HTTPException(
            status_code=409,
            detail='A regression check is already running.',
        )

    try:
        with tempfile.TemporaryDirectory(
            prefix='claim-auditor-regression-'
        ) as temp:
            p = Path(temp)
            paths = {
                'corrected': p / 'corrected.zip',
                'stability': p / 'stability.zip',
            }
            for name, archive in [
                ('corrected', corrected),
                ('stability', stability),
            ]:
                _save_zip(archive, paths[name])

            # Lazy import prevents circular import: api.py imports this router.
            from .api import create_app
            from .generic_import import generic_router

            internal_app = create_app(storage_dir=p / 'api_storage')
            internal_app.include_router(generic_router)

            lines = io.StringIO()
            records = []
            errors = []
            with TestClient(internal_app) as internal_client:
                for protocol in SCHEMAS:
                    try:
                        with contextlib.redirect_stdout(lines):
                            failures, count = run(
                                internal_client,
                                paths[protocol],
                                protocol,
                                target_fpr,
                            )
                        errors.extend(failures)
                        records.append({
                            'protocol': protocol,
                            'comparisons': count,
                            'status': 'FAIL' if failures else 'PASS',
                            'differences': failures,
                        })
                    except Exception as exc:
                        errors.append(
                            f'{protocol}: {type(exc).__name__}: {exc}'
                        )
                        records.append({
                            'protocol': protocol,
                            'comparisons': 0,
                            'status': 'ERROR',
                            'differences': [str(exc)],
                        })

            result = {
                'status': 'PASS' if not errors else 'FAIL',
                'target_fpr': target_fpr,
                'comparisons': sum(
                    record['comparisons'] for record in records
                ),
                'protocols': records,
                'differences': errors,
                'log': lines.getvalue(),
                'note': (
                    'Checks implementation consistency only; '
                    'no statistical superiority is established.'
                ),
            }
            result['markdown_report'] = build_regression_markdown(result)
            return result
    finally:
        _lock.release()
