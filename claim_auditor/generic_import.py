from __future__ import annotations

import csv
import io
import json
import math
import re
import uuid
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from .claim_report_builder import build_claim_markdown
from .comparability import assess_comparability

router = APIRouter(prefix="/api/v1/generic", tags=["Generic experimental data"])
generic_router = router
STORAGE = Path(__file__).resolve().parent / "generic_storage"
MAX_UPLOAD = 8 * 1024 * 1024
MAX_UNCOMPRESSED = 24 * 1024 * 1024
MAX_ROWS = 100_000
REQUIRED = ("dataset_id", "protocol_id", "target_class", "split_id", "method", "recall", "fpr")
ALIASES = {
    "dataset_id": {"dataset", "dataset_name", "dataset_id"},
    "protocol_id": {"protocol", "protocol_id", "evaluation_protocol"},
    "target_class": {"target", "target_class", "positive_class", "attack_class"},
    "split_id": {"split", "fold", "seed", "split_id", "fold_id"},
    "method": {"method", "model", "algorithm", "classifier"},
    "recall": {"recall", "tpr", "sensitivity", "true_positive_rate"},
    "fpr": {"fpr", "false_positive_rate", "false_positive_ratio"},
}


def _fail(message: str, status: int = 422):
    raise HTTPException(status, message)


def _read_csv_from_bytes(payload: bytes, filename: str):
    if len(payload) > MAX_UPLOAD:
        _fail("Upload exceeds 8 MiB.", 413)
    if filename.lower().endswith(".csv"):
        data = payload
    elif filename.lower().endswith(".zip"):
        try:
            with zipfile.ZipFile(io.BytesIO(payload)) as archive:
                members = [item for item in archive.infolist() if not item.is_dir()]
                if any(item.flag_bits & 0x1 for item in members):
                    _fail("Encrypted archives are not supported.")
                if any(item.file_size > MAX_UNCOMPRESSED for item in members):
                    _fail("Archive contains oversized content.", 413)
                if sum(item.file_size for item in members) > MAX_UNCOMPRESSED:
                    _fail("Uncompressed archive exceeds 24 MiB.", 413)
                csvs = [item for item in members if item.filename.lower().endswith(".csv")]
                if len(csvs) != 1:
                    _fail("Generic ZIP archives must contain exactly one CSV file.")
                data = archive.read(csvs[0])
        except (zipfile.BadZipFile, RuntimeError, OSError, ValueError):
            _fail("Invalid ZIP archive.")
    else:
        _fail("Only CSV and ZIP files are supported.")
    try:
        content = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        _fail("The CSV must use UTF-8 encoding.")
    try:
        reader = csv.DictReader(io.StringIO(content, newline=""), strict=True)
        headers = reader.fieldnames
        if not headers or any(not h or not h.strip() for h in headers):
            _fail("CSV header row is missing or contains empty columns.")
        if len(headers) != len(set(headers)):
            _fail("CSV headers must be unique.")
        records = []
        for line_number, record in enumerate(reader, start=2):
            if line_number > MAX_ROWS + 1:
                _fail("CSV exceeds the 100,000 row limit.", 413)
            if None in record:
                _fail(f"CSV line {line_number} has more fields than headers.")
            records.append(record)
    except csv.Error as exc:
        _fail(f"Malformed CSV: {exc}")
    if not records:
        _fail("CSV contains no data rows.")
    return headers, records


def _suggest(headers):
    suggestions = {}
    for key, candidates in ALIASES.items():
        for column in headers:
            norm = re.sub(r"[^a-z0-9]+", "_", column.lower()).strip("_")
            if norm in candidates:
                suggestions[key] = column
                break
    return suggestions


class CommitRequest(BaseModel):
    preview_id: str
    mapping: dict[str, str]
    # User confirmation, not an automatic statistical claim.
    comparison_metadata_confirmed: bool = False


class EvaluateRequest(BaseModel):
    import_id: str
    dataset_id: str
    protocol_id: str
    target_class: str
    baseline_method: str
    challenger_method: str
    fpr_limit: float = Field(ge=0, le=1)
    recall_margin: float = Field(default=0, ge=0, le=1)
    baseline_metadata: dict[str, str] | None = None
    challenger_metadata: dict[str, str] | None = None



def _location(identifier: str, suffix: str):
    if not re.fullmatch(r"[0-9a-f]{32}", identifier):
        _fail("Invalid identifier.", 404)
    return STORAGE / (identifier + suffix)


@router.post("/preview")
async def preview(file: UploadFile = File(...)):
    payload = await file.read(MAX_UPLOAD + 1)
    headers, records = _read_csv_from_bytes(payload, file.filename or "")
    preview_id = uuid.uuid4().hex
    STORAGE.mkdir(exist_ok=True)
    _location(preview_id, ".preview.json").write_text(
        json.dumps({"headers": headers, "rows": records}), encoding="utf-8"
    )
    return {
        "preview_id": preview_id,
        "row_count": len(records),
        "columns": headers,
        "suggested_mapping": _suggest(headers),
        "sample_rows": records[:5],
        "required_fields": list(REQUIRED),
        "notes": ["Each row must represent one method evaluated on one defined split.",
                  "Matching split IDs alone do not prove independence or comparability."],
    }


@router.post("/import")
def commit_import(request: CommitRequest):
    path = _location(request.preview_id, ".preview.json")
    if not path.is_file():
        _fail("Preview not found. Upload the file again.", 404)
    raw = json.loads(path.read_text(encoding="utf-8"))
    mapping = request.mapping
    if set(mapping) != set(REQUIRED):
        _fail("Map every required field exactly once.")
    if len(set(mapping.values())) != len(mapping):
        _fail("A source column cannot be mapped to multiple required fields.")
    if any(column not in raw["headers"] for column in mapping.values()):
        _fail("Mapping references an unknown CSV column.")
    clean = []
    errors = []
    duplicates = set()
    for i, record in enumerate(raw["rows"], start=2):
        row = {field: str(record.get(source) or "").strip() for field, source in mapping.items()}
        missing = [field for field in REQUIRED if not row[field]]
        if missing:
            errors.append(f"Row {i}: missing {', '.join(missing)}")
            continue
        try:
            recall, fpr = float(row["recall"]), float(row["fpr"])
            if any(not math.isfinite(v) or not 0 <= v <= 1 for v in (recall, fpr)):
                raise ValueError()
        except ValueError:
            errors.append(f"Row {i}: recall and FPR must be finite numbers in [0, 1]")
            continue
        row["recall"], row["fpr"] = recall, fpr
        key = tuple(row[field] for field in REQUIRED[:5])
        if key in duplicates:
            errors.append(f"Row {i}: duplicate dataset/protocol/class/split/method")
        duplicates.add(key)
        clean.append(row)
        if len(errors) >= 30:
            break
    if errors:
        _fail({"message": "Import failed validation", "errors": errors})
    group_members = defaultdict(set)
    for row in clean:
        group_members[(row["dataset_id"], row["protocol_id"], row["target_class"], row["split_id"])].add(row["method"])
    warnings = ["Statistical superiority and independence of experimental splits are not established."]
    if not request.comparison_metadata_confirmed:
        warnings.append("Protocol, split semantics, preprocessing and test-set comparability are not independently verified.")
    if any(len(methods) == 1 for methods in group_members.values()):
        warnings.append("Some splits contain only one method and may not permit paired comparisons.")
    import_id = uuid.uuid4().hex
    _location(import_id, ".json").write_text(json.dumps({"rows": clean, "warnings": warnings}), encoding="utf-8")
    return {"import_id": import_id, "rows": len(clean), "status": "PASS_WITH_WARNINGS" if warnings else "PASS", "warnings": warnings,
            "datasets": sorted({r["dataset_id"] for r in clean}),
            "methods": sorted({r["method"] for r in clean}),
            "protocols": sorted({r["protocol_id"] for r in clean}),
            "target_classes": sorted({r["target_class"] for r in clean})}


@router.post("/evaluate")
def evaluate(request: EvaluateRequest):
    if request.baseline_method == request.challenger_method:
        _fail("Select two different methods.")
    path = _location(request.import_id, ".json")
    if not path.is_file():
        _fail("Import not found.", 404)
    result = json.loads(path.read_text(encoding="utf-8"))
    rows = [r for r in result["rows"] if r["dataset_id"] == request.dataset_id
            and r["protocol_id"] == request.protocol_id and r["target_class"] == request.target_class]
    by_split = defaultdict(dict)
    for r in rows:
        by_split[r["split_id"]][r["method"]] = r
    if not by_split:
        _fail("No records match the requested dataset/protocol/class.")
    evidence = []
    wins = losses = ties = jointly_feasible = 0
    for split_id in sorted(by_split):
        methods = by_split[split_id]
        b, c = methods.get(request.baseline_method), methods.get(request.challenger_method)
        if not b or not c:
            outcome, delta = "MISSING_PAIR", None
        elif b["fpr"] > request.fpr_limit or c["fpr"] > request.fpr_limit:
            outcome, delta = "FPR_INFEASIBLE", c["recall"] - b["recall"]
        else:
            jointly_feasible += 1
            delta = c["recall"] - b["recall"]
            if delta > request.recall_margin + 1e-12:
                outcome = "WIN"; wins += 1
            elif delta < -request.recall_margin - 1e-12:
                outcome = "LOSS"; losses += 1
            else:
                outcome = "TIE"; ties += 1
        evidence.append({"split_id": split_id, "baseline_fpr": b["fpr"] if b else None,
                         "challenger_fpr": c["fpr"] if c else None,
                         "baseline_recall": b["recall"] if b else None,
                         "challenger_recall": c["recall"] if c else None,
                         "recall_delta": delta, "outcome": outcome})
    if wins > 0 and losses > 0:
        finding = "MIXED"
    elif wins > 0:
        finding = "POSITIVE_ALL_ELIGIBLE" if ties == 0 else "POSITIVE_OR_TIED"
    elif losses > 0:
        finding = "NEGATIVE_ALL_ELIGIBLE" if ties == 0 else "NEGATIVE_OR_TIED"
    else:
        finding = "TIED_ONLY" if jointly_feasible > 0 else "NO_JOINTLY_FEASIBLE_SPLITS"
    comparability = assess_comparability(
        baseline=request.baseline_metadata,
        challenger=request.challenger_metadata,
    )
    audit = {
        "audit_id": uuid.uuid4().hex,
        "status": "DESCRIPTIVE_ONLY",
        "comparability": comparability,
        "finding": finding,
        "claim_type": "conditional_recall_advantage",
        "dataset_id": request.dataset_id,
        "protocol_id": request.protocol_id,
        "target_class": request.target_class,
        "baseline_method": request.baseline_method,
        "challenger_method": request.challenger_method,
        "fpr_limit": request.fpr_limit,
        "recall_margin": request.recall_margin,
        "claim_support": (
            "OBSERVED_CONDITIONAL_SUPPORT"
            if jointly_feasible > 0 and wins > 0 and losses == 0
            else "NOT_SUPPORTED_AS_STATED"
        ),
        "statistical_superiority": "NOT_ESTABLISHED",
        "expected_splits": len(by_split),
        "jointly_feasible": jointly_feasible,
        "wins": wins,
        "losses": losses,
        "ties": ties,
        "evidence": evidence,
        "limitations": result["warnings"],
    }
    comparability_status = comparability["status"]

    if comparability_status == "INCOMPATIBLE":
        scientific_claim_status = "BLOCKED_INCOMPATIBLE"
    elif comparability_status == "UNVERIFIED":
        scientific_claim_status = "NOT_VERIFIED"
    elif audit["claim_support"] == "OBSERVED_CONDITIONAL_SUPPORT":
        scientific_claim_status = "DESCRIPTIVE_SUPPORT_ONLY"
    else:
        scientific_claim_status = "NOT_SUPPORTED_AS_STATED"

    audit["scientific_claim_status"] = scientific_claim_status
    audit["markdown_report"] = build_claim_markdown(audit)
    return audit

@router.get("/imports/{import_id}/csv")
def download_normalized(import_id: str):
    path = _location(import_id, ".json")
    if not path.is_file():
        _fail("Import not found.", 404)
    rows = json.loads(path.read_text(encoding="utf-8"))["rows"]
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=REQUIRED)
    writer.writeheader(); writer.writerows(rows)
    return StreamingResponse(iter([stream.getvalue()]), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="normalized_{import_id}.csv"'})