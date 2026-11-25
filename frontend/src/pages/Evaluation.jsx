import { useEffect, useMemo, useState } from 'react';
import {
  BarChart3,
  CheckCircle2,
  Download,
  ExternalLink,
  FlaskConical,
  Gauge,
  Languages,
  Play,
  RefreshCw,
  Search,
  ShieldCheck,
  Target,
  Timer,
} from 'lucide-react';
import { api, formatDate, percent, titleCase } from '../api.js';
import { useApp } from '../App.jsx';
import {
  Badge,
  DecisionBadge,
  EmptyState,
  SectionHeader,
  Spinner,
  StatCard,
} from '../components/ui.jsx';

export default function Evaluation() {
  const { adminUser, openLogin } = useApp();
  const [latest, setLatest] = useState(null);
  const [cases, setCases] = useState([]);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState('');
  const [category, setCategory] = useState('');
  const [decision, setDecision] = useState('');
  const [search, setSearch] = useState('');

  async function load() {
    setLoading(true);
    setError('');
    try {
      const [latestResult, caseResult] = await Promise.all([api.evaluationLatest(), api.evaluationCases()]);
      setLatest(latestResult.run);
      setCases(caseResult.cases || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function runEvaluation() {
    if (!adminUser) {
      openLogin();
      return;
    }
    setRunning(true);
    setError('');
    try {
      const result = await api.runEvaluation();
      setLatest(result);
    } catch (err) {
      if (err.status === 401) openLogin();
      setError(err.message);
    } finally {
      setRunning(false);
    }
  }

  const metrics = latest?.metrics;
  const rows = useMemo(() => {
    const items = latest?.cases || [];
    return items.filter((item) => {
      if (category && item.category !== category) return false;
      if (decision && item.actual_decision !== decision) return false;
      if (search && !`${item.id} ${item.query}`.toLowerCase().includes(search.toLowerCase())) return false;
      return true;
    });
  }, [latest, category, decision, search]);

  return (
    <div>
      <SectionHeader
        eyebrow="Evaluation"
        title="Measured performance, not marketing numbers"
        description="The bundled 50-case set is executed locally. Retrieval, refusal, intent and latency are measured; faithfulness is a transparent lexical-support check, not an LLM judge."
        actions={
          <>
            <a className="button button-secondary" href={api.reportUrl} target="_blank" rel="noreferrer"><Download size={16} /> Markdown report</a>
            <a className="button button-secondary" href={api.resultsUrl} target="_blank" rel="noreferrer"><ExternalLink size={16} /> Results JSON</a>
            <button type="button" className="button button-primary" onClick={runEvaluation} disabled={running}>
              {running ? <RefreshCw className="spin" size={16} /> : <Play size={16} />}
              {running ? 'Running 50 cases…' : 'Run evaluation'}
            </button>
          </>
        }
      />

      {error ? <div className="alert alert-error">{error}</div> : null}
      {loading ? <Spinner label="Loading evaluation results…" /> : null}

      {!loading && !latest ? (
        <div className="panel">
          <EmptyState
            title="No evaluation run yet"
            message="Press “Run evaluation” to execute the bundled 50-case set. The runner writes docs/EVALUATION_REPORT.md and docs/evaluation_latest.json."
            icon={FlaskConical}
            action={<button type="button" className="button button-primary" onClick={runEvaluation} disabled={running}>Run evaluation</button>}
          />
        </div>
      ) : null}

      {latest && metrics ? (
        <>
          <div className="eval-banner">
            <div>
              <Badge tone="green" dot>Run completed</Badge>
              <strong>{latest.id}</strong>
              <span>{formatDate(latest.created_at)} · dataset v{latest.dataset_version} · {(latest.duration_ms / 1000).toFixed(1)}s</span>
            </div>
            <div className="eval-banner-note">
              {latest.notes}
            </div>
          </div>

          <div className="stats-grid">
            <StatCard label="Recall@5" value={percent(metrics.recall_at_5, 1)} hint={`${metrics.retrieval_cases} retrieval cases · target 85%`} icon={Target} tone={metrics.target_status?.recall_at_5 === 'met' ? 'green' : 'amber'} />
            <StatCard label="Faithfulness" value={percent(metrics.faithfulness, 1)} hint="Lexical support · target 90%" icon={ShieldCheck} tone={metrics.target_status?.faithfulness === 'met' ? 'green' : 'amber'} />
            <StatCard label="Correct refusal" value={percent(metrics.correct_refusal_rate, 1)} hint={`${metrics.refusal_cases} refusal cases · target 90%`} icon={CheckCircle2} tone={metrics.target_status?.correct_refusal_rate === 'met' ? 'green' : 'amber'} />
            <StatCard label="Intent accuracy" value={percent(metrics.intent_accuracy, 1)} hint="Rule-based labels vs hand labels" icon={Gauge} tone="blue" />
            <StatCard label="Decision accuracy" value={percent(metrics.decision_accuracy, 1)} hint="Answer / clarify / refuse" icon={BarChart3} tone="violet" />
            <StatCard label="p95 latency" value={`${metrics.latency_ms_p95?.toFixed(0)} ms`} hint={`Mean ${metrics.latency_ms_mean?.toFixed(0)} ms · in-process`} icon={Timer} tone="blue" />
          </div>

          <div className="two-column">
            <div className="panel">
              <div className="panel-head"><h2><Languages size={18} /> Language breakdown</h2></div>
              <div className="bar-list">
                {Object.entries(metrics.by_language || {}).map(([lang, values]) => (
                  <div key={lang} className="bar-row">
                    <div className="bar-label"><span>{lang.toUpperCase()}</span><small>{values.cases} cases</small></div>
                    <div className="bar-track"><div className="bar-fill" style={{ width: `${values.decision_accuracy * 100}%` }} /></div>
                    <strong>{percent(values.decision_accuracy, 0)}</strong>
                  </div>
                ))}
              </div>
              <div className="panel-foot">Decision accuracy by language. Intent accuracy: {Object.entries(metrics.by_language || {}).map(([lang, values]) => `${lang} ${percent(values.intent_accuracy, 0)}`).join(' · ')}</div>
            </div>
            <div className="panel">
              <div className="panel-head"><h2><Target size={18} /> Target status</h2></div>
              <div className="target-list">
                {Object.entries(metrics.target_status || {}).map(([key, value]) => (
                  <div key={key} className="target-row">
                    <span>{titleCase(key)}</span>
                    <Badge tone={value === 'met' ? 'green' : 'amber'}>{value}</Badge>
                  </div>
                ))}
                <div className="target-row"><span>Voice round-trip</span><Badge tone="neutral">Not measured</Badge></div>
              </div>
              <div className="panel-foot">
                Voice round-trip is listed as a design target only. Browser ASR and network TTS latency are not benchmarked by this runner.
              </div>
            </div>
          </div>

          <div className="panel">
            <div className="panel-head">
              <h2><FlaskConical size={18} /> Case-level results</h2>
              <span>{rows.length} of {latest.cases?.length || 0} cases</span>
            </div>
            <div className="filter-bar">
              <div className="search-field"><Search size={16} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search case id or question…" /></div>
              <label className="select-field">
                <select value={category} onChange={(event) => setCategory(event.target.value)}>
                  <option value="">All categories</option>
                  {[...new Set((latest.cases || []).map((item) => item.category))].map((item) => <option key={item} value={item}>{titleCase(item)}</option>)}
                </select>
              </label>
              <label className="select-field">
                <select value={decision} onChange={(event) => setDecision(event.target.value)}>
                  <option value="">All decisions</option>
                  <option value="answer">Answered</option>
                  <option value="ask_to_repeat">Ask to repeat</option>
                  <option value="refuse">Refused</option>
                </select>
              </label>
            </div>
            <div className="table-wrap">
              <table className="data-table eval-table">
                <thead>
                  <tr>
                    <th>Case</th>
                    <th>Lang</th>
                    <th>Category</th>
                    <th>Expected</th>
                    <th>Actual</th>
                    <th>Intent</th>
                    <th>Recall@5</th>
                    <th>Faith.</th>
                    <th>Conf.</th>
                    <th>Latency</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((item) => (
                    <tr key={item.id}>
                      <td>
                        <div className="case-id">{item.id}</div>
                        <div className="case-query">{item.query}</div>
                      </td>
                      <td><Badge tone="neutral">{item.language?.toUpperCase()}</Badge></td>
                      <td>{titleCase(item.category)}</td>
                      <td><DecisionBadge decision={item.expected_decision} /></td>
                      <td><DecisionBadge decision={item.actual_decision} /></td>
                      <td>{item.intent_correct ? <Badge tone="green">OK</Badge> : <Badge tone="red">{titleCase(item.actual_intent)}</Badge>}</td>
                      <td>{item.recall_at_5 === null ? '—' : item.recall_at_5?.toFixed(2)}</td>
                      <td>{item.faithfulness === null ? '—' : item.faithfulness?.toFixed(2)}</td>
                      <td>{Math.round((item.confidence || 0) * 100)}%</td>
                      <td>{item.latency_ms?.toFixed(0)} ms</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className="panel provenance-panel">
            <div className="panel-head"><h2><ShieldCheck size={18} /> Provenance and honesty notes</h2></div>
            <ul className="honesty-list">
              <li><strong>Recall, refusal and intent:</strong> measured on the bundled hand-built set. The corpus is small and curated, so these numbers are internal engineering checks, not field accuracy.</li>
              <li><strong>Faithfulness:</strong> token overlap between the answer body and retrieved evidence, after removing template scaffolding and source lines. The default composer is extractive, so this is high by construction.</li>
              <li><strong>Not measured:</strong> ASR word error rate, translation quality, native-speaker comprehension, farmer usefulness, hosted-LLM quality, network latency or production load.</li>
              <li><strong>Tool modes:</strong> {JSON.stringify(metrics.tool_modes || {})}. Simulated mandi data is labelled in every answer; weather is labelled LIVE only when the request succeeds.</li>
              <li><strong>Generation providers:</strong> {JSON.stringify(metrics.generation_providers || {})}. The default is a deterministic template composer, not an LLM.</li>
            </ul>
          </div>
        </>
      ) : null}
    </div>
  );
}
