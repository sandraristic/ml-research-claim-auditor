from __future__ import annotations

from typing import Any, Mapping

REQUIRED = (
    'test_set_fingerprint',
    'preprocessing_fingerprint',
    'label_definition_fingerprint',
    'split_definition_fingerprint',
    'metric_definition_fingerprint',
)


def assess_comparability(
    baseline: Mapping[str, Any] | None,
    challenger: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Compare *declared* method-level metadata for one paired evaluation.

    Returns INCOMPATIBLE for explicit conflicts, UNVERIFIED for missing/invalid
    evidence, and DECLARED_COMPATIBLE when every required value agrees.
    DECLARED_COMPATIBLE is NOT independent proof of comparability.
    """
    if not isinstance(baseline, Mapping) or not isinstance(challenger, Mapping):
        return {
            'status': 'UNVERIFIED',
            'conflicts': [],
            'missing': list(REQUIRED),
            'limitations': ['Method-level comparability metadata is missing.'],
        }

    conflicts: list[str] = []
    missing: list[str] = []
    for key in REQUIRED:
        left = baseline.get(key)
        right = challenger.get(key)
        left_valid = isinstance(left, str) and bool(left.strip())
        right_valid = isinstance(right, str) and bool(right.strip())
        if not left_valid or not right_valid:
            missing.append(key)
        elif left.strip() != right.strip():
            conflicts.append(key)

    status = (
        'INCOMPATIBLE' if conflicts else
        'UNVERIFIED' if missing else
        'DECLARED_COMPATIBLE'
    )
    limitations = [
        'Matching metadata is a declaration, not independent verification of '
        'the underlying samples, preprocessing, labels, or metric implementation.',
        'This assessment does not establish independence of experimental splits '
        'or statistical superiority.',
    ]
    if conflicts:
        limitations.insert(0, 'Explicit metadata conflicts prevent treating this pair as comparable.')
    elif missing:
        limitations.insert(0, 'Required comparability metadata are incomplete or invalid.')

    return {
        'status': status,
        'conflicts': conflicts,
        'missing': missing,
        'limitations': limitations,
    }
