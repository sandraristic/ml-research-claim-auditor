import contextlib
import io
import math
import tempfile
import threading
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

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
    request: Request,
    corrected: UploadFile = File(...),
    stability: UploadFile = File(...),
    target_fpr: float = Form(0.01),
):
    if not math.isfinite(target_fpr) or not (0 < target_fpr <= 1):
        raise HTTPException(
            status_code=422,
            detail='target_fpr must be within (0, 1].',
        )

    # Internal localhost-only API calls; no user-controlled destination.
    port = request.url.port or 80

    if port not in (8000, 8001):
        raise HTTPException(
            status_code=400,
            detail='Start the local API on port 8000 or 8001.',
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

            lines = io.StringIO()
            records = []
            errors = []

            for protocol in SCHEMAS:
                try:
                    with contextlib.redirect_stdout(lines):
                        failures, count = run(
                            f'http://127.0.0.1:{port}',
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

            # Generate the Markdown report from regression results.
            result['markdown_report'] = build_regression_markdown(
                result
            )

            return result

    finally:
        _lock.release()
