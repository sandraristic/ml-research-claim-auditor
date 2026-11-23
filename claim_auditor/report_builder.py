from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping


def _clean(value: Any) -> str:
    """Keep external values on a single Markdown table line."""
    return str(value).replace('|', r'\|').replace('\r', ' ').replace('\n', ' ')


def build_regression_markdown(result: Mapping[str, Any]) -> str:
    """Format an API /api/v1/regression/run response as Markdown."""
    if not isinstance(result, Mapping):
        raise TypeError('Regression result must be a mapping')

    protocols = result.get('protocols', [])
    if not isinstance(protocols, list):
        raise ValueError('protocols must be a list')

    status = str(result.get('status', 'UNKNOWN'))
    target_fpr = result.get('target_fpr')
    total = result.get('comparisons', 0)
    generated = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')

    lines = [
        '# ML Research Claim Auditor — Regression Audit Report',
        '',
        f'**Generated:** {generated}  ',
        f'**Overall regression result:** `{_clean(status)}`  ',
        f'**Comparisons executed:** {_clean(total)}  ',
        f'**Target FPR:** {_clean(target_fpr)}',
        '',
        '## Purpose and scope',
        '',
        'This report checks whether the existing MITM auditor and Generic Import '
        'produce consistent outputs for the same uploaded experimental evidence '
        'and comparison settings. Corrected and stability protocols are evaluated '
        'separately, not compared against each other.',
        '',
        '## Protocol summary',
        '',
        '| Protocol | Comparisons | Result |',
        '|---|---:|---|',
    ]
    for item in protocols:
        if not isinstance(item, Mapping):
            raise ValueError('each protocol entry must be a mapping')
        lines.append(
            f"| {_clean(item.get('protocol', 'UNKNOWN'))} | "
            f"{_clean(item.get('comparisons', 0))} | "
            f"`{_clean(item.get('status', 'UNKNOWN'))}` |"
        )

    differences = result.get('differences', []) or []
    if not isinstance(differences, list):
        raise ValueError('differences must be a list')
    lines += ['', '## Reported differences', '']
    if differences:
        for issue in differences:
            lines.append(f'- {_clean(issue)}')
    else:
        lines.append('No differences were reported by the regression checks.')

    log = result.get('log', '') or ''
    lines += ['', '## Detailed comparison log', '']
    if log:
        # Indented code rather than fenced blocks, to handle arbitrary log text.
        lines.extend('    ' + line for line in str(log).rstrip().splitlines())
    else:
        lines.append('No detailed log was provided.')

    lines += [
        '',
        '## Scientific and methodological limitations',
        '',
        '- A passing regression check demonstrates consistency only for the tested inputs and rules.',
        '- It does not independently verify ground-truth labels, data provenance, or preprocessing equivalence.',
        '- Repeated IP-pair splits are not independent collection sessions.',
        '- Corrected and stability protocols must not be interpreted as directly comparable.',
        '- Descriptive support for a claim is not evidence of statistical or causal superiority.',
        '',
        '## Conclusion',
        '',
    ]
    if status == 'PASS':
        lines.append(
            'All executed comparisons were reported as passing by the regression system. '
            'This supports implementation consistency for the examined cases, '
            'not scientific validity beyond those cases.'
        )
    else:
        lines.append(
            f'The regression system reported `{_clean(status)}`. Review the listed '
            'differences or errors before treating the implementations as consistent.'
        )
    return '\n'.join(lines) + '\n'
