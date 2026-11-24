import React, { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { Activity, ArrowRight, BadgeCheck, CheckCircle2, ChevronDown, CircleAlert, ClipboardCheck, Download, FileArchive, FileText, FlaskConical, Info, LoaderCircle, ShieldCheck, UploadCloud, XCircle } from 'lucide-react';
import './styles.css';
import GenericImportPanel from './GenericImportPanel';
import RegressionPanel from './RegressionPanel';

const API = '/api/v1';
const METHODS = { baseline: 'Baseline', mitm_smote: 'SMOTE', mitm_weighting: 'Weighting' };
const fmt = (n) => n == null || !Number.isFinite(Number(n)) ? '—' : (Number(n) * 100).toFixed(2) + '%';
const pretty = (s) => String(s ?? '').replaceAll('_', ' ').toLowerCase().replace(/^./, x => x.toUpperCase());
async function req(path, options) {
  const response = await fetch(API + path, options);
  let body;
  try {
    body = await response.json()
  } catch {
    body = { detail: await response.text() }
  }
  if (!response.ok) throw new Error(typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail ?? body));
  return body
}
function App() {

  const [importMode, setImportMode] = useState('generic');
  const pageTitles = { generic: 'Generic data import', mitm: 'MITM archive analysis', regression: 'Regression verification' };
  const pageDescriptions = { generic: 'Import structured ML experiment results, evaluate conditional claims, and inspect scientific limitations.', mitm: 'Validate original MITM experiment archives and audit split-level evidence.', regression: 'Verify implementation consistency between the existing and generic import pipelines.' };

  const [health, setHealth] = useState('checking'), [protocol, setProtocol] = useState('corrected'), [file, setFile] = useState(null), [imp, setImp] = useState(null), [manifest, setManifest] = useState(null), [loading, setLoading] = useState(''), [error, setError] = useState(''), [audit, setAudit] = useState(null);

  const [dataset, setDataset] = useState('ton'), [baseline, setBaseline] = useState('baseline'), [challenger, setChallenger] = useState('mitm_weighting'), [limit, setLimit] = useState('0.01'), [claimType, setClaimType] = useState('conditional_recall_advantage');

  useEffect(() => {
    req('/health').then(() => setHealth('online')).catch(() => setHealth('offline'))
  }, []);

  const splits = manifest?.expected_splits?.[dataset] ?? [];

  const upload = async (e) => {
    e.preventDefault();

    if (!file) return;

    setLoading('upload');
    setError('');
    setAudit(null);

    try {
      const form = new FormData();
      form.append('protocol', protocol);
      form.append('file', file);

      const data = await req('/datasets/import', {
        method: 'POST',
        body: form,
      });

      const m = await req(`/datasets/${data.import_id}/manifest`);

      setImp(data);
      setManifest(m);

      const ds = Object.keys(m.expected_splits)[0];

      setDataset(ds);
      setBaseline(
        m.expected_methods.includes('baseline')
          ? 'baseline'
          : m.expected_methods[0],
      );
      setChallenger(
        m.expected_methods.includes('mitm_weighting')
          ? 'mitm_weighting'
          : m.expected_methods[1],
      );
      setLimit(
        String(
          m.fpr_limits.find((n) => Math.abs(n - 0.01) < 1e-9) ??
          m.fpr_limits[0],
        ),
      );
    } catch (ex) {
      setError(ex.message);
    } finally {
      setLoading('');
    }
  };

  const run = async (e) => {
    e.preventDefault();

    setLoading('evaluate');
    setError('');
    setAudit(null);

    try {
      const claim = {
        claim_type: claimType,
        dataset_id: dataset,
        protocol_id: manifest.protocol_id,
        target_class: manifest.target_class,
        baseline_method: baseline,
        challenger_method: challenger,
        fpr_limit: Number(limit),
        recall_margin: 0,
        expected_split_ids: splits,
      };

      const result = await req('/claims/evaluate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          import_id: imp.import_id,
          claim,
        }),
      });

      setAudit(result);
    } catch (ex) {
      setError(ex.message);
    } finally {
      setLoading('');
    }
  };

  return <div className="app">
    <aside className="sidebar">
      <div className="brand">
        <div className="brand-icon">
          <FlaskConical size={23} />
        </div>
        <div>
          <strong>Research Claim<br />Auditor</strong>
          <span>RESEARCH WORKSPACE</span>
        </div>
      </div>
      <div className="navtitle">WORKSPACE</div>
      <nav className="sidebar-nav" aria-label="Primary navigation">
        <button type="button" className={`navitem ${importMode === 'generic' ? 'active' : ''}`} aria-current={importMode === 'generic' ? 'page' : undefined} onClick={() => setImportMode('generic')}><UploadCloud size={18} /> Generic data import</button>
        <button type="button" className={`navitem ${importMode === 'mitm' ? 'active' : ''}`} aria-current={importMode === 'mitm' ? 'page' : undefined} onClick={() => setImportMode('mitm')}><FileArchive size={18} /> MITM archive analysis</button>
        <button type="button" className={`navitem ${importMode === 'regression' ? 'active' : ''}`} aria-current={importMode === 'regression' ? 'page' : undefined} onClick={() => setImportMode('regression')}><ClipboardCheck size={18} /> Regression tests</button>
      </nav>
      <div className="sidebar-note"><ShieldCheck size={16} /> Descriptive research tool. No statistical superiority is inferred.</div>
      <div className="aside-bottom">
        <div className={'server ' + health}><span className="pulse" /> API {health}</div>
        <div className="version">Research prototype • Local workspace</div>
      </div>
    </aside>

    <main>
      <header className="top">
        <div>
          <span className="eyebrow">ML RESEARCH / CLAIM EVALUATION</span>
          <h1>{pageTitles[importMode]}</h1>
          <p>{pageDescriptions[importMode]}</p>
        </div>
        <span className="top-status"><Activity size={15} /> DESCRIPTIVE AUDIT</span>
      </header>

      {error && <div role="alert" className="error">
        <CircleAlert size={18} />
        <span>
          {error}
        </span>
        <button aria-label="Dismiss error" onClick={() => setError('')}>×</button>
      </div>}

             <div className="import-mode-switch" role="tablist" aria-label="Research workflows">
         <button type="button" role="tab" aria-selected={importMode === 'generic'} onClick={() => setImportMode('generic')}><UploadCloud size={16} /> Generic CSV / ZIP</button>
         <button type="button" role="tab" aria-selected={importMode === 'mitm'} onClick={() => setImportMode('mitm')}><FileArchive size={16} /> MITM archives</button>
         <button type="button" role="tab" aria-selected={importMode === 'regression'} onClick={() => setImportMode('regression')}><ClipboardCheck size={16} /> Regression tests</button>
       </div>
{importMode === 'generic' && <GenericImportPanel />}
    {importMode === 'regression' && <RegressionPanel />}
    <div style={{ display: importMode === 'mitm' ? 'block' : 'none' }}>
    <div className="steps">
        <section className="panel">
          <div className="section-head">
            <span className="num">01</span>
            <div>
              <h2>Import experiment results</h2>
              <p>Load a supported MITM experiment archive.</p>
            </div>
          </div>
          <form onSubmit={upload} className="content">
            <label className="field-label">Experiment protocol</label>
            <select value={protocol} onChange={e => setProtocol(e.target.value)} disabled={!!loading}>
              <option value="corrected">Corrected validation</option>
              <option value="stability">Stability validation</option>
            </select>
            <label className="dropzone">
              <FileArchive size={26} />
              <strong>
                {file ? file.name : 'Choose a ZIP archive'}
              </strong>
              <span>Corrected or Stability experiment • up to 8 MB</span>
              <input type="file" accept=".zip,application/zip" onChange={e => setFile(e.target.files[0] ?? null)} />
            </label>
            <button className="primary" disabled={!file || !!loading} type="submit">{loading === 'upload' ? <LoaderCircle className="spin" size={16} /> : <UploadCloud size={16} />} Import & validate <ArrowRight size={16} /></button>
          </form>
        </section>

        <section className="panel">
          <div className="section-head">
            <span className="num">02</span>
            <div>
              <h2>Evidence integrity</h2>
              <p>Confirm all required experiment records are present.</p>
            </div>
          </div>
          <div className="content">
            {imp ? <>
              <div className="success">
                <BadgeCheck size={21} />
                <div>
                  <strong>
                    {imp.status.replaceAll('_', ' ')}
                  </strong>
                  <span>{imp.rows} experiment records imported • {imp.protocol} protocol</span>
                </div>
              </div>
              <div className="details">
                <div>
                  <span>Target class</span>
                  <strong>
                    {manifest.target_class}
                  </strong>
                </div>
                <div>
                  <span>Methods</span>
                  <strong>
                    {manifest.expected_methods.length}
                  </strong>
                </div>
                <div>
                  <span>FPR targets</span>
                  <strong>
                    {manifest.fpr_limits.length}
                  </strong>
                </div>
              </div>
              {imp.warnings?.length > 0 && <details className="warnings">
                <summary>Methodological warnings ({imp.warnings.length})</summary>
                {imp.warnings.map((w, i) => <p key={i}>
                  {w}
                </p>)}
              </details>}
            </> : <div className="empty">
              <ShieldCheck size={26} />
              <span>Import an archive to inspect its evidence integrity.</span>
            </div>}
          </div>
        </section>

        <section className="panel wide">
          <div className="section-head">
            <span className="num">03</span>
            <div>
              <h2>Define the research claim</h2>
              <p>Compare two methods under a fixed operational constraint.</p>
            </div>
          </div>
          <form onSubmit={run} className="content claim-form">
            <div className="fields">
              <label>
                <span>Dataset</span>
                <select disabled={!manifest || !!loading} value={dataset} onChange={e => setDataset(e.target.value)}>
                  {(manifest ? Object.keys(manifest.expected_splits) : ['ton']).map(ds => <option key={ds} value={ds}>
                    {ds === 'ton' ? 'ToN-IoT' : ds === 'iotid' ? 'IoTID20' : ds}
                  </option>)}
                </select>
              </label>
              <label>
                <span>Baseline</span>
                <select disabled={!manifest || !!loading} value={baseline} onChange={e => setBaseline(e.target.value)}>
                  {(manifest?.expected_methods ?? ['baseline']).map(m => <option key={m} value={m}>
                    {METHODS[m] || m}
                  </option>)}
                </select>
              </label>
              <label>
                <span>Challenger</span>
                <select disabled={!manifest || !!loading} value={challenger} onChange={e => setChallenger(e.target.value)}>
                  {(manifest?.expected_methods ?? ['mitm_weighting']).map(m => <option key={m} value={m}>
                    {METHODS[m] || m}
                  </option>)}
                </select>
              </label>
              <label>
                <span>Max. test FPR</span>
                <select disabled={!manifest || !!loading} value={limit} onChange={e => setLimit(e.target.value)}>
                  {(manifest?.fpr_limits ?? [.01]).map(v => <option key={v} value={String(v)}>
                    {fmt(v)}
                  </option>)}
                </select>
              </label>
            </div>
            <label>
              <span>Claim to evaluate</span>
              <select disabled={!manifest || !!loading} value={claimType} onChange={e => setClaimType(e.target.value)}>
                <option value="conditional_recall_advantage">Conditional recall advantage</option>
                <option value="universal_operational_advantage">Universal operational advantage</option>
              </select>
            </label>
            <p className="explanation">
              {claimType === 'conditional_recall_advantage' ? 'Does the challenger outperform baseline in jointly FPR-feasible splits?' : 'Is the challenger better in every expected split while both methods satisfy FPR?'}
            </p>
            <button className="primary" type="submit" disabled={!manifest || !!loading || baseline === challenger}>{loading === 'evaluate' ? <LoaderCircle className="spin" size={16} /> : <ClipboardCheck size={16} />} Evaluate claim <ArrowRight size={16} /></button>
          </form>
        </section>
      </div>

      {audit && <section className="panel results">
        <div className="section-head">
          <span className="num">04</span>
          <div>
            <h2>Audit results</h2>
            <p>Evidence-backed, descriptive findings from your uploaded experiments.</p>
          </div>
        </div>
        <div className="content">
          <div className="result-header">
            <div>
              <span className="eyebrow">CLAIM SUPPORT</span>
              <h3>
                {pretty(audit.claim_support)}
              </h3>
              <p>{pretty(audit.comparison.finding)} · Statistical superiority: not established</p>
            </div>
            <div className="result-chip"><Info size={17} /> Descriptive only</div>
          </div>
          <div className="metrics">
            <div>
              <span>Jointly feasible</span>
              <strong>
                {audit.operational.jointly_feasible}

                <small>/ {audit.operational.expected_splits}</small>
              </strong>
            </div>
            <div>
              <span>Wins</span>
              <strong>
                {audit.comparison.wins}
              </strong>
            </div>
            <div>
              <span>Losses</span>
              <strong>
                {audit.comparison.losses}
              </strong>
            </div>
            <div>
              <span>Ties</span>
              <strong>
                {audit.comparison.ties}
              </strong>
            </div>
          </div>
          <div className="tablewrap">
            <table>
              <thead>
                <tr>
                  <th>Split</th>
                  <th>Baseline FPR</th>
                  <th>Challenger FPR</th>
                  <th>Recall Δ</th>
                  <th>Outcome</th>
                </tr>
              </thead>
              <tbody>
                {audit.evidence.map(ev => <tr key={ev.split_id}>
                  <td>
                    {ev.split_id}
                  </td>
                  <td>
                    {fmt(ev.baseline_fpr)}
                  </td>
                  <td>
                    {fmt(ev.challenger_fpr)}
                  </td>
                  <td>
                    {(ev.recall_delta >= 0 ? '+' : '') + fmt(ev.recall_delta)}
                  </td>
                  <td>
                    <span className={'outcome ' + ev.outcome.toLowerCase()}>
                      {pretty(ev.outcome)}
                    </span>
                  </td>
                </tr>)}
              </tbody>
            </table>
          </div>
          <div className="limitations">
            <strong><CircleAlert size={17} /> Research limitations</strong>
            {audit.limitations.map((line, i) => <p key={i}>
              {line}
            </p>)}
          </div>
          <div className="actions">
            <a href={`${API}/audits/${audit.audit_id}/report`}><Download size={16} /> Markdown report</a>
            <a href={`${API}/audits/${audit.audit_id}/evidence`}><Download size={16} /> Evidence CSV</a>
            <button onClick={() => {
              const blob = new Blob([JSON.stringify(audit, null, 2)], { type: 'application/json' });
              const url = URL.createObjectURL(blob);
              const a = document.createElement('a');
              a.href = url;
              a.download = 'audit.json';
              a.click();
              URL.revokeObjectURL(url)
            }}><Download size={16} /> Audit JSON</button>
          </div>
        </div>
      </section>}

      </div>
    <footer><ShieldCheck size={15} /> Research prototype · Results are descriptive, not proof of causal or statistical superiority.</footer>
    </main>
  </div>
}
createRoot(document.getElementById('root')).render(<App />);
