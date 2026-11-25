import { useEffect, useMemo, useState } from 'react';
import {
  Activity,
  BookOpenText,
  CheckCircle2,
  CloudSun,
  Database,
  Globe2,
  Info,
  KeyRound,
  Languages,
  ListChecks,
  Plus,
  RefreshCw,
  Server,
  ShieldCheck,
  Store,
  Trash2,
  Volume2,
  Wrench,
} from 'lucide-react';
import { api, formatDate, percent, titleCase } from '../api.js';
import { useApp } from '../App.jsx';
import {
  Badge,
  DataModeBadge,
  EmptyState,
  SectionHeader,
  Spinner,
  StatCard,
} from '../components/ui.jsx';

const EMPTY_GLOSSARY = { term_en: '', term_hi: '', term_mr: '', category: 'general', aliases: '' };

export default function Administration() {
  const { adminUser, openLogin } = useApp();
  const [overview, setOverview] = useState(null);
  const [system, setSystem] = useState(null);
  const [safety, setSafety] = useState(null);
  const [glossary, setGlossary] = useState({ items: [], counts: {}, total: 0 });
  const [audit, setAudit] = useState([]);
  const [sources, setSources] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [glossaryForm, setGlossaryForm] = useState(EMPTY_GLOSSARY);
  const [glossarySearch, setGlossarySearch] = useState('');
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState('');

  async function load() {
    setLoading(true);
    setError('');
    try {
      const [overviewData, systemData, safetyData, glossaryData, auditData, sourceData] = await Promise.all([
        api.overview(),
        api.system(),
        api.safety(),
        api.glossary(),
        api.audit(80),
        api.sources(),
      ]);
      setOverview(overviewData);
      setSystem(systemData);
      setSafety(safetyData);
      setGlossary(glossaryData);
      setAudit(auditData.items || []);
      setSources(sourceData.items || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function addGlossary(event) {
    event.preventDefault();
    if (!adminUser) {
      openLogin();
      return;
    }
    if (!glossaryForm.term_en.trim()) return;
    setSaving(true);
    setMessage('');
    try {
      await api.addGlossary({
        ...glossaryForm,
        aliases: glossaryForm.aliases.split(',').map((item) => item.trim()).filter(Boolean),
      });
      setGlossaryForm(EMPTY_GLOSSARY);
      setMessage('Glossary entry saved and the retrieval index rebuilt.');
      await load();
    } catch (err) {
      if (err.status === 401) openLogin();
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  async function removeGlossary(entry) {
    if (!adminUser) {
      openLogin();
      return;
    }
    if (!window.confirm(`Delete glossary term “${entry.term_en}”?`)) return;
    try {
      await api.deleteGlossary(entry.id);
      await load();
    } catch (err) {
      if (err.status === 401) openLogin();
      setError(err.message);
    }
  }

  const filteredGlossary = useMemo(() => {
    const needle = glossarySearch.toLowerCase();
    if (!needle) return glossary.items;
    return glossary.items.filter((item) => `${item.term_en} ${item.term_hi} ${item.term_mr} ${(item.aliases || []).join(' ')}`.toLowerCase().includes(needle));
  }, [glossary.items, glossarySearch]);

  const counts = overview?.queries || {};
  const docs = overview?.documents || {};

  return (
    <div>
      <SectionHeader
        eyebrow="Administration"
        title="System status, safety policy and terminology"
        description="Inspect the actual runtime configuration. Optional providers are shown as configured or unavailable; the UI never presents a fallback as a live integration."
        actions={<button type="button" className="button button-secondary" onClick={load}><RefreshCw size={16} /> Refresh</button>}
      />

      {error ? <div className="alert alert-error">{error}</div> : null}
      {loading ? <Spinner label="Loading administration data…" /> : null}

      {!loading && system ? (
        <>
          <div className="stats-grid">
            <StatCard label="Queries logged" value={counts.total_queries ?? 0} hint={`${counts.answered ?? 0} answered · ${counts.refused ?? 0} refused`} icon={Activity} />
            <StatCard label="Approved documents" value={docs.approved ?? 0} hint={`${docs.pending ?? 0} pending review`} icon={BookOpenText} tone="blue" />
            <StatCard label="Indexed chunks" value={system.retrieval?.chunks ?? 0} hint={`${system.retrieval?.documents ?? 0} documents`} icon={Database} tone="violet" />
            <StatCard label="Glossary terms" value={glossary.total ?? 0} hint="Crop, pest, input and place names" icon={Languages} tone="green" />
          </div>

          <div className="admin-grid">
            <ProviderCard
              icon={Database}
              title="Answer generation"
              provider={system.generation?.provider}
              mode={system.generation?.mode}
              available={system.generation?.available}
              note={system.generation?.note}
              honesty="The default is an extractive template composer. It is not an LLM."
            />
            <ProviderCard
              icon={Globe2}
              title="Embeddings"
              provider={system.retrieval?.embedding?.provider}
              mode={system.retrieval?.embedding?.mode}
              available
              note={`${system.retrieval?.embedding?.dimension || 0} dimensions. ${system.retrieval?.embedding?.fallback_reason || 'No fallback active.'}`}
              honesty="Hashed multilingual embeddings are deterministic and CPU-only; neural embeddings are optional."
            />
            <ProviderCard
              icon={Volume2}
              title="Speech"
              provider={`TTS ${system.speech?.tts?.provider} · ASR ${system.speech?.asr?.provider}`}
              mode={system.speech?.asr?.server_available ? 'server ASR available' : 'browser ASR'}
              available={system.speech?.tts?.provider?.startsWith('edge')}
              note={system.speech?.asr?.note}
              honesty="Server ASR is optional. The default path uses the browser Web Speech API; no WER claim is made."
            />
            <ProviderCard
              icon={Store}
              title="Mandi data"
              provider={system.tools?.mandi?.configured_provider}
              mode={system.tools?.mandi?.mode}
              available={system.tools?.mandi?.live}
              note={system.tools?.mandi?.note}
              honesty="Simulated fixtures are used unless a data.gov.in key is configured; every answer is labelled."
            />
            <ProviderCard
              icon={CloudSun}
              title="Weather"
              provider={system.tools?.weather?.configured_provider}
              mode={system.tools?.weather?.mode}
              available
              note={system.tools?.weather?.note}
              honesty="Open-Meteo is a free forecast API, not an official IMD Agromet bulletin. Failures fall back to a labelled simulation."
            />
            <ProviderCard
              icon={Server}
              title="Runtime"
              provider={`${system.app} v${system.version}`}
              mode="CPU · SQLite · single process"
              available
              note={`Started ${formatDate(system.started_at)} · DB ${system.database}`}
              honesty="This is a demonstration build sized for a laptop, not a production cluster."
            />
          </div>

          <div className="two-column">
            <div className="panel">
              <div className="panel-head"><h2><ShieldCheck size={18} /> Safety gate policy</h2></div>
              <div className="policy-grid">
                {Object.entries(safety?.decision_policy || {}).map(([key, items]) => (
                  <div key={key} className={`policy-column policy-${key}`}>
                    <h3>{titleCase(key)}</h3>
                    <ul>{items.map((item) => <li key={item}>{item}</li>)}</ul>
                  </div>
                ))}
              </div>
              <div className="thresholds">
                {Object.entries(safety?.thresholds || {}).map(([key, value]) => (
                  <div key={key}><span>{titleCase(key)}</span><strong>{value}</strong></div>
                ))}
              </div>
              <div className="detail-note"><Info size={16} /> {safety?.chemical_dosage_policy}</div>
              <div className="helpline-card">
                <span>Kisan Call Centre</span>
                <strong>{safety?.helplines?.kisan_call_centre}</strong>
                <a href={safety?.helplines?.kvk_portal} target="_blank" rel="noreferrer">KVK portal ↗</a>
              </div>
            </div>

            <div className="panel">
              <div className="panel-head"><h2><ListChecks size={18} /> Recent audit events</h2><span>{audit.length} events</span></div>
              <div className="audit-list">
                {audit.slice(0, 12).map((item) => (
                  <div key={item.id} className="audit-row">
                    <div className="audit-dot" />
                    <div>
                      <strong>{titleCase(item.action)}</strong>
                      <span>{item.entity_type}{item.entity_id ? ` · ${item.entity_id}` : ''} · {item.actor || 'system'}</span>
                    </div>
                    <small>{formatDate(item.created_at)}</small>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div className="panel">
            <div className="panel-head">
              <h2><Languages size={18} /> Agricultural glossary</h2>
              <span>{filteredGlossary.length} of {glossary.total} terms</span>
            </div>
            <div className="glossary-toolbar">
              <input value={glossarySearch} onChange={(event) => setGlossarySearch(event.target.value)} placeholder="Search English, Hindi, Marathi or alias…" />
              <div className="glossary-counts">
                {Object.entries(glossary.counts || {}).map(([key, value]) => <Badge key={key} tone="neutral">{titleCase(key)} {value}</Badge>)}
              </div>
            </div>
            <div className="glossary-layout">
              <form className="glossary-form" onSubmit={addGlossary}>
                <h3><Plus size={16} /> Add a term</h3>
                <label><span>English</span><input required value={glossaryForm.term_en} onChange={(event) => setGlossaryForm({ ...glossaryForm, term_en: event.target.value })} /></label>
                <label><span>Hindi</span><input value={glossaryForm.term_hi} onChange={(event) => setGlossaryForm({ ...glossaryForm, term_hi: event.target.value })} /></label>
                <label><span>Marathi</span><input value={glossaryForm.term_mr} onChange={(event) => setGlossaryForm({ ...glossaryForm, term_mr: event.target.value })} /></label>
                <label><span>Category</span>
                  <select value={glossaryForm.category} onChange={(event) => setGlossaryForm({ ...glossaryForm, category: event.target.value })}>
                    {['crop', 'pest', 'disease', 'input', 'scheme', 'place', 'general'].map((item) => <option key={item} value={item}>{titleCase(item)}</option>)}
                  </select>
                </label>
                <label><span>Aliases (comma separated)</span><input value={glossaryForm.aliases} onChange={(event) => setGlossaryForm({ ...glossaryForm, aliases: event.target.value })} /></label>
                <button type="submit" className="button button-primary" disabled={saving}>{saving ? <RefreshCw className="spin" size={16} /> : <Plus size={16} />} Save term</button>
                {message ? <div className="inline-note"><CheckCircle2 size={15} /> {message}</div> : null}
              </form>
              <div className="glossary-table-wrap">
                <table className="data-table glossary-table">
                  <thead><tr><th>English</th><th>हिंदी</th><th>मराठी</th><th>Category</th><th>Aliases</th><th /></tr></thead>
                  <tbody>
                    {filteredGlossary.map((item) => (
                      <tr key={item.id}>
                        <td><strong>{item.term_en}</strong></td>
                        <td>{item.term_hi || '—'}</td>
                        <td>{item.term_mr || '—'}</td>
                        <td><Badge tone="neutral">{titleCase(item.category)}</Badge></td>
                        <td className="aliases">{(item.aliases || []).join(', ') || '—'}</td>
                        <td><button type="button" className="icon-button icon-delete" onClick={() => removeGlossary(item)} title="Delete term"><Trash2 size={15} /></button></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>

          <div className="panel">
            <div className="panel-head"><h2><BookOpenText size={18} /> Source register</h2><span>{sources.length} records</span></div>
            <div className="table-wrap">
              <table className="data-table">
                <thead><tr><th>Title</th><th>Publisher</th><th>Source</th><th>Status</th><th>Type</th><th>Note</th></tr></thead>
                <tbody>
                  {sources.map((item) => (
                    <tr key={item.id}>
                      <td><strong>{item.title}</strong></td>
                      <td>{item.publisher || '—'}</td>
                      <td>{item.source_url ? <a className="text-link" href={item.source_url} target="_blank" rel="noreferrer">Link ↗</a> : item.source_name || '—'}</td>
                      <td><Badge tone={item.approval_status === 'approved' ? 'green' : 'amber'}>{titleCase(item.approval_status)}</Badge></td>
                      <td>{item.is_demo ? <Badge tone="amber">Demo summary</Badge> : <Badge tone="green">Admin source</Badge>}</td>
                      <td className="note-cell">{item.content_note}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className="panel">
            <div className="panel-head"><h2><KeyRound size={18} /> Configuration and limits</h2></div>
            <div className="config-list">
              <div><span>Demo notice</span><p>{system.demo_notice}</p></div>
              <div><span>Evaluation set</span><p>{system.evaluation?.cases} cases · dataset v{system.evaluation?.dataset}</p></div>
              <div><span>Optional API keys</span><p><code>OPENAI_API_KEY</code> for a hosted LLM, <code>DATA_GOV_IN_API_KEY</code> for live Agmarknet mandi data. Neither is required for the demo.</p></div>
              <div><span>Persistence</span><p>SQLite at <code>{system.database}</code>. Delete the file to re-seed the demonstration corpus.</p></div>
            </div>
          </div>
        </>
      ) : null}
    </div>
  );
}

function ProviderCard({ icon: Icon, title, provider, mode, available, note, honesty }) {
  return (
    <div className="provider-card">
      <div className="provider-head">
        <div className="provider-icon"><Icon size={19} /></div>
        <div><strong>{title}</strong><span>{mode}</span></div>
        <Badge tone={available ? 'green' : 'amber'} dot>{available ? 'Available' : 'Fallback'}</Badge>
      </div>
      <div className="provider-name">{provider}</div>
      <p>{note}</p>
      <div className="provider-honesty"><Info size={14} /> {honesty}</div>
    </div>
  );
}
