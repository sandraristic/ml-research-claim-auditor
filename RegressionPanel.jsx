import React, { useState } from 'react';
import {
  Activity,
  Play,
  Download,
  AlertCircle,
  CheckCircle2,
} from 'lucide-react';

const formStyle = {
  display: 'grid',
  gap: 14,
};

export default function RegressionPanel() {

  const [corrected, setCorrected] = useState(null);
  const [stability, setStability] = useState(null);
  const [limit, setLimit] = useState('0.01');
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');

  const run = async (e) => {
    e.preventDefault();

    setBusy(true);
    setError('');
    setResult(null);

    try {
      const form = new FormData();

      form.append('corrected', corrected);
      form.append('stability', stability);
      form.append('target_fpr', limit);

      const response = await fetch('/api/v1/regression/run', {
        method: 'POST',
        body: form,
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(
          typeof data.detail === 'string'
            ? data.detail
            : JSON.stringify(data.detail),
        );
      }

      setResult(data);
    } catch (err) {
      setError(err.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  const downloadFile = (content, filename, type) => {
    const blob = new Blob([content], { type });
    const objectUrl = URL.createObjectURL(blob);

    const link = document.createElement('a');

    link.href = objectUrl;
    link.download = filename;

    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);

    setTimeout(() => {
      URL.revokeObjectURL(objectUrl);
    }, 1000);
  };

  const downloadJSON = () => {
    if (!result) return;

    downloadFile(
      JSON.stringify(result, null, 2),
      'regression_report.json',
      'application/json',
    );
  };

  const downloadMarkdown = () => {
    if (!result?.markdown_report) return;

    downloadFile(
      result.markdown_report,
      'regression_report.md',
      'text/markdown;charset=utf-8',
    );
  };
  return (
    <section className="panel">
      <div className="section-head">
        <span className="num">05</span>

        <div>
          <h2>Automated Regression Tests</h2>
          <p>
            Compare the original MITM auditor with Generic Import
            using the same experimental evidence.
          </p>
        </div>
      </div>

      <div className="content">
        <form onSubmit={run} style={formStyle}>
          <label className="field-label">
            Corrected MITM archive
            <input
              type="file"
              accept=".zip"
              required
              onChange={(e) =>
                setCorrected(e.target.files?.[0] || null)
              }
            />
          </label>

          <label className="field-label">
            Stability MITM archive
            <input
              type="file"
              accept=".zip"
              required
              onChange={(e) =>
                setStability(e.target.files?.[0] || null)
              }
            />
          </label>

          <label className="field-label">
            Maximum test FPR
            <select
              value={limit}
              onChange={(e) => setLimit(e.target.value)}
            >
              <option value="0.005">0.5%</option>
              <option value="0.01">1%</option>
              <option value="0.02">2%</option>
            </select>
          </label>

          <button
            className="primary"
            type="submit"
            disabled={busy || !corrected || !stability}
          >
            {busy ? (
              <Activity size={16} />
            ) : (
              <Play size={16} />
            )}

            {busy
              ? 'Comparing experiments…'
              : 'Run regression tests'}
          </button>
        </form>

        {error && (
          <div
            className="error"
            role="alert"
            style={{ marginTop: 18 }}
          >
            <AlertCircle size={18} />
            {error}
          </div>
        )}

        {result && (
          <div
            style={{
              marginTop: 24,
              display: 'grid',
              gap: 16,
            }}
          >
            <div
              className={
                result.status === 'PASS' ? 'success' : 'error'
              }
            >
              {result.status === 'PASS' ? (
                <CheckCircle2 size={20} />
              ) : (
                <AlertCircle size={20} />
              )}

              <strong>
                {result.status} — {result.comparisons} comparisons
                checked
              </strong>
            </div>

            <div
              className="details"
              style={{
                gridTemplateColumns:
                  'repeat(auto-fit, minmax(160px, 1fr))',
              }}
            >
              {result.protocols.map((protocol) => (
                <div key={protocol.protocol}>
                  <span>
                    {protocol.protocol.toUpperCase()}
                  </span>

                  <strong>{protocol.status}</strong>

                  <small>
                    {protocol.comparisons} comparisons
                  </small>
                </div>
              ))}
            </div>

            {result.differences.length > 0 && (
              <div className="limitations">
                <strong>Differences / errors</strong>

                {result.differences.map((line, index) => (
                  <p key={index}>{line}</p>
                ))}
              </div>
            )}

            <details>
              <summary>Detailed comparison log</summary>

              <pre
                style={{
                  whiteSpace: 'pre-wrap',
                  overflowWrap: 'anywhere',
                  fontSize: 12,
                }}
              >
                {result.log}
              </pre>
            </details>

            <p
              style={{
                fontSize: 12,
                color: '#64748b',
              }}
            >
              {result.note}
            </p>

            <div
              className="actions"
              style={{
                display: 'flex',
                flexWrap: 'wrap',
                gap: 12,
              }}
            >
              <button
                type="button"
                onClick={downloadJSON}
              >
                <Download size={16} />
                Download JSON Report
              </button>

              <button
                type="button"
                onClick={downloadMarkdown}
                disabled={!result.markdown_report}
              >
                <Download size={16} />
                Download Markdown Report
              </button>
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
