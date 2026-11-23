import React, { useState } from 'react';
import { Download } from 'lucide-react';

const API = '/api/v1/generic';
const FIELDS = ['dataset_id', 'protocol_id', 'target_class', 'split_id', 'method', 'recall', 'fpr'];

async function request(path, options) {
  const response = await fetch(`${API}${path}`, options);
  const raw = await response.text();
  let body;
  try { body = JSON.parse(raw); } catch { body = { detail: raw }; }
  if (!response.ok) {
    const detail = body.detail ?? body;
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail, null, 2));
  }
  return body;
}

export default function GenericImportPanel() {
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [mapping, setMapping] = useState({});
  const [confirmed, setConfirmed] = useState(false);
  const [imported, setImported] = useState(null);
  const [baseline, setBaseline] = useState('');
  const [challenger, setChallenger] = useState('');
  const [dataset, setDataset] = useState('');
  const [protocol, setProtocol] = useState('');
  const [targetClass, setTargetClass] = useState('');
  const [fprLimit, setFprLimit] = useState('0.01');
  const [audit, setAudit] = useState(null);
  const [baselineMetadata, setBaselineMetadata] = useState('');
  const [challengerMetadata, setChallengerMetadata] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const mapped = FIELDS.every(field => mapping[field]) &&
    new Set(FIELDS.map(field => mapping[field])).size === FIELDS.length;

  async function previewFile(event) {
    event.preventDefault();
    if (!file) return;
    setBusy(true); setError(''); setPreview(null); setImported(null); setAudit(null);
    try {
      const form = new FormData();
      form.append('file', file);
      const data = await request('/preview', { method: 'POST', body: form });
      setPreview(data);
      setMapping(data.suggested_mapping ?? {});
      setConfirmed(false);
    } catch (e) { setError(e.message); }
    finally { setBusy(false); }
  }

  async function commit(event) {
    event.preventDefault();
    setBusy(true); setError('');
    try {
      const result = await request('/import', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ preview_id: preview.preview_id, mapping, comparison_metadata_confirmed: confirmed }),
      });
      setImported(result); setAudit(null);
      setDataset(result.datasets[0]); setProtocol(result.protocols[0]);
      setTargetClass(result.target_classes[0]);
      setBaseline(result.methods[0]); setChallenger(result.methods[1] ?? '');
    } catch (e) { setError(e.message); }
    finally { setBusy(false); }
  }

  async function evaluate(event) {
    event.preventDefault();
    setBusy(true);
    setError('');
    setAudit(null);

    try {
      const baselineMeta = parseMetadata(
        baselineMetadata,
        'Baseline metadata',
      );

      const challengerMeta = parseMetadata(
        challengerMetadata,
        'Challenger metadata',
      );

      const result = await request('/evaluate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          import_id: imported.import_id,
          dataset_id: dataset,
          protocol_id: protocol,
          target_class: targetClass,
          baseline_method: baseline,
          challenger_method: challenger,
          fpr_limit: Number(fprLimit),
          recall_margin: 0,
          baseline_metadata: baselineMeta,
          challenger_metadata: challengerMeta,
        }),
      });

      setAudit(result);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  function downloadClaimReport() {
    if (!audit?.markdown_report) return;

    const blob = new Blob([audit.markdown_report], {
      type: 'text/markdown;charset=utf-8',
    });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = 'research_claim_report.md';
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  function parseMetadata(value, label) {
    if (!value.trim()) return null;

    let parsed;

    try {
      parsed = JSON.parse(value);
    } catch {
      throw new Error(`${label} must contain valid JSON.`);
    }

    if (
      !parsed ||
      typeof parsed !== 'object' ||
      Array.isArray(parsed) ||
      Object.values(parsed).some(value => typeof value !== 'string')
    ) {
      throw new Error(`${label} must be a JSON object with string values.`);
    }

    return parsed;
  }

  return (
    <section className="panel generic-import">
      <div className="section-head"><div><h2>Generic Experimental Data Import</h2>
        <p>Upload CSV or ZIP, map columns, validate records, and run a descriptive comparison.</p></div></div>
      <div className="content">
        {error && <div role="alert" className="error"><strong>Request failed:</strong> <pre>{error}</pre></div>}
        <form onSubmit={previewFile} className="generic-form generic-upload-form">
          <label htmlFor="generic-file">Experimental CSV or ZIP (max 8 MiB)</label>
          <input id="generic-file" type="file" accept=".csv,.zip" onChange={e => setFile(e.target.files?.[0] ?? null)} />
          <button type="submit" className="primary" disabled={!file || busy}>Preview columns</button>
        </form>
        {preview && <form onSubmit={commit} className="generic-form generic-mapping-form">
          <h3>Map source columns</h3>
          <p>{preview.row_count} rows detected. Each required field must map to a different column.</p>
          <div className="fields">
            {FIELDS.map(field => <label key={field}>
              <span>{field}</span>
              <select value={mapping[field] ?? ''} onChange={e => setMapping(old => ({ ...old, [field]: e.target.value }))}>
                <option value="">Select CSV column</option>
                {preview.columns.map(col => <option key={col} value={col}>{col}</option>)}
              </select>
            </label>)}
          </div>
          <h3>Source preview</h3>
          <div className="tablewrap"><table><thead><tr>{preview.columns.map(col => <th key={col}>{col}</th>)}</tr></thead>
            <tbody>{preview.sample_rows.map((row, i) => <tr key={i}>{preview.columns.map(col => <td key={col}>{row[col]}</td>)}</tr>)}</tbody>
          </table></div>
          <label><input type="checkbox" checked={confirmed} onChange={e => setConfirmed(e.target.checked)} />
            I have verified that matching splits use compatible preprocessing, test samples, class definitions, and protocol settings.
          </label>
          <p>Leaving this unchecked does not block import; it adds a methodological warning.</p>
          <button type="submit" className="primary" disabled={!mapped || busy}>Validate & import dataset</button>
        </form>}
        {imported && <section className="generic-subsection">
          <h3>Import result: {imported.status}</h3>
          <p>{imported.rows} validated rows. Import ID: <code>{imported.import_id}</code></p>
          {imported.warnings.map((message, i) => <p key={i} role="note">⚠ {message}</p>)}
          <a href={`${API}/imports/${imported.import_id}/csv`}>Download normalized CSV</a>
          <form onSubmit={evaluate} className="generic-form generic-evaluate-form">
            <h3>Descriptive claim evaluation</h3>
            <div className="fields">
              <label>Dataset<select value={dataset} onChange={e => setDataset(e.target.value)}>{imported.datasets.map(v => <option key={v}>{v}</option>)}</select></label>
              <label>Protocol<select value={protocol} onChange={e => setProtocol(e.target.value)}>{imported.protocols.map(v => <option key={v}>{v}</option>)}</select></label>
              <label>Target class<select value={targetClass} onChange={e => setTargetClass(e.target.value)}>{imported.target_classes.map(v => <option key={v}>{v}</option>)}</select></label>
              <label>Baseline<select value={baseline} onChange={e => setBaseline(e.target.value)}>{imported.methods.map(v => <option key={v}>{v}</option>)}</select></label>
              <label>Challenger<select value={challenger} onChange={e => setChallenger(e.target.value)}>{imported.methods.map(v => <option key={v}>{v}</option>)}</select></label>
              <label>Maximum FPR<input type="number" min="0" max="1" step="any" value={fprLimit} onChange={e => setFprLimit(e.target.value)} /></label>
            </div>
            <fieldset className="metadata-fieldset">
              <legend>Experimental comparability metadata (optional)</legend>

              <p>
                Provide documented metadata for both methods.
                Leave empty when metadata is unavailable.
                Matching values do not establish independent verification.
              </p>

              <div className="fields">
                <label>
                  Baseline metadata (JSON)
                  <textarea
                    rows={7}
                    value={baselineMetadata}
                    onChange={e => setBaselineMetadata(e.target.value)}
                    placeholder='{"test_set_fingerprint": "..."}'
                  />
                </label>

                <label>
                  Challenger metadata (JSON)
                  <textarea
                    rows={7}
                    value={challengerMetadata}
                    onChange={e => setChallengerMetadata(e.target.value)}
                    placeholder='{"test_set_fingerprint": "..."}'
                  />
                </label>
              </div>
            </fieldset>
            <button type="submit" className="primary" disabled={busy || !challenger || baseline === challenger || fprLimit === '' || !Number.isFinite(Number(fprLimit))}>Evaluate claim</button>
          </form>
        </section>}
        {audit && <section className="generic-subsection generic-audit">
          <span className="eyebrow">RESEARCH CLAIM EVALUATION</span>
          <h3>Audit: {audit.claim_support}</h3>
          <p>
            <strong>Scientific claim status: </strong>
            {audit.scientific_claim_status ?? 'NOT_AVAILABLE'}
          </p>
          {(() => {
            const comparability =
              audit.comparability ?? audit.audit?.comparability;

            if (!comparability) {
              return (
                <p role="alert">
                  Comparability status unavailable.
                </p>
              );
            }

            const status = comparability.status;

            return (
              <div className={`comparability-result comparability-${String(status ?? 'unverified').toLowerCase()}`}>
                <h4>Experimental Comparability</h4>

                <p>
                  <strong>Status: {status}</strong>
                </p>

                {status === 'DECLARED_COMPATIBLE' && (
                  <p>
                    The supplied metadata matches. Independent
                    experimental comparability has not been verified.
                  </p>
                )}

                {status === 'UNVERIFIED' && (
                  <p role="alert">
                    Experimental comparability could not be established
                    from the supplied metadata.
                  </p>
                )}

                {status === 'INCOMPATIBLE' && (
                  <p role="alert">
                    Conflicting experimental metadata detected.
                    Numerical results are descriptive only and must
                    not be interpreted as a valid comparative
                    scientific claim.
                  </p>
                )}

                {comparability.conflicts?.length > 0 && (
                  <pre>{JSON.stringify(comparability.conflicts, null, 2)}</pre>
                )}

                {comparability.missing?.length > 0 && (
                  <p>
                    Missing metadata: {comparability.missing.join(', ')}
                  </p>
                )}
              </div>
            );
          })()}
          <div className="generic-metrics">
            <div><span>Jointly feasible</span><strong>{audit.jointly_feasible} <small>/ {audit.expected_splits}</small></strong></div>
            <div><span>Wins</span><strong>{audit.wins}</strong></div>
            <div><span>Losses</span><strong>{audit.losses}</strong></div>
            <div><span>Ties</span><strong>{audit.ties}</strong></div>
          </div>
          <p><strong>Statistical superiority: {audit.statistical_superiority}</strong></p>
          <div className="tablewrap"><table><thead><tr><th>Split</th><th>Baseline FPR</th><th>Challenger FPR</th><th>Recall Δ</th><th>Outcome</th></tr></thead>
            <tbody>{audit.evidence.map(row => <tr key={row.split_id}><td>{row.split_id}</td><td>{row.baseline_fpr ?? '—'}</td><td>{row.challenger_fpr ?? '—'}</td><td>{row.recall_delta == null ? '—' : Number(row.recall_delta).toFixed(4)}</td><td>{row.outcome}</td></tr>)}</tbody></table></div>
          {audit.limitations.map((line, i) => <p key={i}>{line}</p>)}
          {audit.markdown_report && (
            <div className="actions">
              <button type="button" className="primary" onClick={downloadClaimReport}>
                <Download size={16} />
                Download Research Claim Report
              </button>
            </div>
          )}
        </section>}
      </div>
    </section>
  );
}