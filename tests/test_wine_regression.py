import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient

from claim_auditor.api import app
from claim_auditor.comparability import REQUIRED


def find_wine_import():
    storage = ROOT / "claim_auditor" / "generic_storage"
    if not storage.is_dir():
        raise AssertionError(f"Import storage not found: {storage}")

    candidates = sorted(
        storage.glob("*.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for path in candidates:
        # Imported data use <32 hex chars>.json; previews use .preview.json.
        if not re.fullmatch(r"[0-9a-f]{32}\.json", path.name):
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        rows = data.get("rows", [])
        groups = {}
        for row in rows:
            if "wine" not in str(row.get("dataset_id", "")).lower():
                continue
            key = (row.get("dataset_id"), row.get("protocol_id"), row.get("target_class"))
            groups.setdefault(key, set()).add(row.get("method"))
        for (dataset_id, protocol_id, target_class), methods in groups.items():
            if {"LogisticRegression", "RandomForest"}.issubset(methods):
                return path.stem, dataset_id, protocol_id, target_class
    raise AssertionError(
        "Wine import with LogisticRegression and RandomForest was not found "
        "in claim_auditor/generic_storage."
    )


def main():
    import_id, dataset_id, protocol_id, target_class = find_wine_import()
    print(f"Found Wine import: {import_id}", flush=True)
    print(f"Dataset: {dataset_id} | Protocol: {protocol_id}", flush=True)

    payload = {
        "import_id": import_id,
        "dataset_id": dataset_id,
        "protocol_id": protocol_id,
        "target_class": target_class,
        "baseline_method": "LogisticRegression",
        "challenger_method": "RandomForest",
        "fpr_limit": 0.05,
        "recall_margin": 0,
    }
    # Synthetic metadata ONLY for testing API behavior; not research evidence.
    metadata = {field: f"test-{field}" for field in REQUIRED}
    cases = [
        ("UNVERIFIED", "NOT_VERIFIED", None, None),
        ("DECLARED_COMPATIBLE", "NOT_SUPPORTED_AS_STATED", metadata, metadata),
        (
            "INCOMPATIBLE",
            "BLOCKED_INCOMPATIBLE",
            metadata,
            {**metadata, "test_set_fingerprint": "different-test-set"},
        ),
    ]

    results = []
    with TestClient(app) as client:
        for comparability_status, scientific_status, baseline_meta, challenger_meta in cases:
            response = client.post(
                "/api/v1/generic/evaluate",
                json={
                    **payload,
                    "baseline_metadata": baseline_meta,
                    "challenger_metadata": challenger_meta,
                },
            )
            assert response.status_code == 200, (
                f"HTTP {response.status_code}: {response.text}"
            )
            result = response.json()
            assert result["comparability"]["status"] == comparability_status, result
            assert result["scientific_claim_status"] == scientific_status, result
            assert result["claim_support"] == "NOT_SUPPORTED_AS_STATED", result
            assert result["statistical_superiority"] == "NOT_ESTABLISHED", result
            assert result["expected_splits"] == 5, result
            assert result["jointly_feasible"] == 5, result
            assert (result["wins"], result["losses"], result["ties"]) == (1, 1, 3), result

            report = result["markdown_report"]
            assert "## Experimental Comparability Assessment" in report
            assert f"**Comparability status:** `{comparability_status}`" in report
            assert f"**Scientific claim status:** `{scientific_status}`" in report

            results.append(result)
            print(f"PASS: {comparability_status} / {scientific_status}", flush=True)

    unchanged_fields = (
        "claim_support", "finding", "statistical_superiority",
        "expected_splits", "jointly_feasible", "wins", "losses", "ties", "evidence",
    )
    reference = {field: results[0][field] for field in unchanged_fields}
    for result in results[1:]:
        actual = {field: result[field] for field in unchanged_fields}
        assert actual == reference, f"Numerical output changed: {actual} != {reference}"

    print("PASS: NUMERICAL RESULTS UNCHANGED", flush=True)
    print("PASS: MARKDOWN REPORT CONTENT", flush=True)
    print("ALL WINE REGRESSION CHECKS PASSED", flush=True)


if __name__ == "__main__":
    main()
