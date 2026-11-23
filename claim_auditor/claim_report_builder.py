from __future__ import annotations

from datetime import datetime, timezone
from math import isfinite
from typing import Any, Mapping


def _cell(value: Any) -> str:
    if value is None:
        return 'N/A'
    return str(value).replace('|', r'\|').replace('\r', ' ').replace('\n', ' ')


def _number(value: Any) -> str:
    if value is None:
        return 'N/A'
    if isinstance(value, bool):
        return _cell(value)
    try:
        num = float(value)
    except (ValueError, TypeError):
        return _cell(value)
    return f'{num:.6f}' if isfinite(num) else 'INVALID'


def build_claim_markdown(audit: Mapping[str, Any]) -> str:
    """Create a reproducible descriptive report from an existing audit response.

    This function formats supplied evidence; it never fabricates unavailable
    metrics and never infers statistical significance.
    """
    if not isinstance(audit, Mapping):
        raise TypeError('audit must be a mapping')
    evidence = audit.get('evidence')
    if not isinstance(evidence, list):
        raise ValueError('audit.evidence must be a list')
    if any(not isinstance(entry, Mapping) for entry in evidence):
        raise ValueError('each evidence entry must be a mapping')

    claim = audit.get('claim') or {}
    if not isinstance(claim, Mapping):
        raise ValueError('audit.claim must be a mapping when present')
    comparison = audit.get('comparison') or {}
    operational = audit.get('operational') or {}
    if not isinstance(comparison, Mapping) or not isinstance(operational, Mapping):
        raise ValueError('comparison and operational must be mappings when present')

    def get(key: str, default: Any = None) -> Any:
        return claim.get(key, audit.get(key, default))

    generated = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
    claim_type = get('claim_type', 'conditional_recall_advantage')
    dataset = get('dataset_id')
    protocol = get('protocol_id')
    target = get('target_class')
    baseline = get('baseline_method')
    challenger = get('challenger_method')
    fpr_limit = get('fpr_limit')
    recall_margin = get('recall_margin', 0)
    joint = operational.get('jointly_feasible', audit.get('jointly_feasible'))
    expected = operational.get('expected_splits', audit.get('expected_splits'))
    wins = comparison.get('wins', audit.get('wins'))
    losses = comparison.get('losses', audit.get('losses'))
    ties = comparison.get('ties', audit.get('ties'))

    lines = [
        '# ML Research Claim Auditor — Research Claim Evidence Report',
        '',
        f'**Generated:** {generated}  ',
        f'**Audit ID:** `{_cell(audit.get("audit_id"))}`  ',
        f'**Scientific claim status:** `{_cell(audit.get("scientific_claim_status", "NOT_AVAILABLE"))}`  ',
        f'**Statistical superiority:** `{_cell(audit.get("statistical_superiority", "NOT_ESTABLISHED"))}`',
        '',
        '## Evaluated research claim',
        '',
        f'The evaluated claim is `{_cell(claim_type)}`: whether **{_cell(challenger)}** '
        f'has a recall advantage over **{_cell(baseline)}** on the **{_cell(target)}** '
        f'target class in **{_cell(dataset)}**, under protocol **{_cell(protocol)}**, '
        f'with maximum test FPR **{_number(fpr_limit)}** and recall margin **{_number(recall_margin)}**.',
        '',
        '## Descriptive result',
        '',
        '| Metric | Observed value |',
        '|---|---:|',
        f'| Expected splits | {_cell(expected)} |',
        f'| Jointly feasible splits | {_cell(joint)} |',
        f'| Wins | {_cell(wins)} |',
        f'| Losses | {_cell(losses)} |',
        f'| Ties | {_cell(ties)} |',
        f'| Finding | {_cell(comparison.get("finding", audit.get("finding", "Not provided")))} |',
        '',
        '## Split-level evidence',
        '',
        '| Split | Baseline test FPR | Challenger test FPR | Baseline recall | Challenger recall | Recall delta | Outcome |',
        '|---|---:|---:|---:|---:|---:|---|',
    ]
    for row in evidence:
        lines.append(
            f'| {_cell(row.get("split_id"))} | {_number(row.get("baseline_fpr"))} '
            f'| {_number(row.get("challenger_fpr"))} '
            f'| {_number(row.get("baseline_recall"))} '
            f'| {_number(row.get("challenger_recall"))} '
            f'| {_number(row.get("recall_delta"))} '
            f'| {_cell(row.get("outcome"))} |'
        )
    if not evidence:
        lines.append('| No evidence supplied | — | — | — | — | — | — |')

    comparability = audit.get("comparability") or {}
    comp_status = comparability.get("status", "UNVERIFIED")
    conflicts = comparability.get("conflicts") or []
    missing = comparability.get("missing") or []

    lines.extend([
        "",
        "## Experimental Comparability Assessment",
        "",
        f"**Comparability status:** `{_cell(comp_status)}`",
        "",
    ])

    if comp_status == "DECLARED_COMPATIBLE":
        lines.append(
            "The supplied experimental metadata are consistent. "
            "This does not establish independent verification, "
            "data provenance, or statistical superiority."
        )

    elif comp_status == "INCOMPATIBLE":
        lines.append(
            "**Methodological warning:** Conflicting experimental "
            "metadata were detected. The numerical comparison is "
            "descriptive only and must not be interpreted as a "
            "valid comparative scientific claim."
        )

    else:
        lines.append(
            "Experimental comparability could not be established "
            "from the supplied metadata. The numerical findings "
            "are descriptive and should not be treated as "
            "a validated comparative scientific claim."
        )

    if conflicts:
        lines.extend(["", "### Conflicting metadata", ""])
        for conflict in conflicts:
            lines.append(f"- {_cell(conflict)}")

    if missing:
        lines.extend(["", "### Missing metadata", ""])
        for field in missing:
            lines.append(f"- {_cell(field)}")

    limitations = audit.get('limitations') or []
    if not isinstance(limitations, list):
        raise ValueError('audit.limitations must be a list when present')
    lines.extend(['', '## Scientific and methodological limitations', ''])
    for item in limitations:
        lines.append(f'- {_cell(item)}')
    lines.extend([
        '- This is a descriptive evaluation, not a statistical significance test.',
        '- Matching software outputs does not independently establish data provenance or ground-truth validity.',
        '- If repeated splits overlap, they must not be presented as independent sessions.',
        '- Different experimental protocols should not be compared without a separate comparability assessment.',
        '',
        '## Conclusion',
        '',
        f'The audit reports **{_cell(audit.get("claim_support"))}** for the stated claim. '
        'Interpret this status only within the supplied protocol, FPR constraint and split-level evidence. '
        'No claim of statistical or causal superiority is established by this report.',
    ])
    return '\n'.join(lines) + '\n'
