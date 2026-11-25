import { useEffect, useState } from 'react';
import {
  CheckCircle2,
  Clock,
  Filter,
  MessageSquareText,
  RefreshCw,
  Search,
  ShieldAlert,
  ThumbsUp,
  Timer,
  XCircle,
} from 'lucide-react';
import { api, formatDate, titleCase } from '../api.js';
import {
  Badge,
  ConfidenceMeter,
  DecisionBadge,
  EmptyState,
  Modal,
  SectionHeader,
  Spinner,
  StatCard,
} from '../components/ui.jsx';

export default function QueryHistory() {
  const { adminUser, openLogin } = useApp();
  const [data, setData] = useState({ items: [], total: 0, stats: null });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [query, setQuery] = useState('');
  const [decision, setDecision] = useState('');
  const [language, setLanguage] = useState('');
  const [detail, setDetail] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [review, setReview] = useState({ status: 'reviewed', note: '', corrected_answer: '', reviewer: 'admin' });
  const [saving, setSaving] = useState(false);

  async function load() {
    setLoading(true);
    setError('');
    try {
      const result = await api.history({ q: query, decision, language, limit: 100 });
      setData(result);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    const timer = setTimeout(load, 220);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query, decision, language]);

  async function openDetail(id) {
    setDetailLoading(true);
    setDetail({ id });
    try {
      const item = await api.historyDetail(id);
      setDetail(item);
      setReview({
        status: item.review_status === 'unreviewed' ? 'reviewed' : item.review_status,
        note: item.review_note || '',
        corrected_answer: item.corrected_answer || '',
        reviewer: 'admin',
      });
    } catch (err) {
      setError(err.message);
      setDetail(null);
    } finally {
      setDetailLoading(false);
    }
  }

  async function submitReview() {
    if (!detail) return;
    if (!adminUser) {
      openLogin();
      return;
    }
    setSaving(true);
    try {
      const updated = await api.reviewQuery(detail.id, review);
      setDetail(updated);
      await load();
    } catch (err) {
      if (err.status === 401) openLogin();
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  const stats = data.stats || {};
  return (
    <div>
      <SectionHeader
        eyebrow="Query history"
        title="Every answer, decision and review"
        description="The pipeline logs each question with its intent, gate decision, confidence, sources and latency. Refusals are kept for expert review."
        actions={<button type="button" className="button button-secondary" onClick={load}><RefreshCw size={16} /> Refresh</button>}
      />

      <div className="stats-grid">
        <StatCard label="Total queries" value={stats.total_queries ?? '—'} hint={stats.last_query_at ? `Last ${formatDate(stats.last_query_at)}` : 'No queries yet'} icon={MessageSquareText} />
        <StatCard label="Answered" value={stats.answered ?? '—'} hint="Grounded or tool-backed" icon={CheckCircle2} tone="green" />
        <StatCard label="Refused safely" value={stats.refused ?? '—'} hint={`${stats.unreviewed_refusals ?? 0} awaiting review`} icon={ShieldAlert} tone="red" />
        <StatCard label="Mean latency" value={stats.avg_latency_ms ? `${stats.avg_latency_ms.toFixed(0)} ms` : '—'} hint="In-process pipeline" icon={Timer} tone="blue" />
      </div>

      <div className="panel">
        <div className="filter-bar">
          <div className="search-field">
            <Search size={16} />
            <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search question or answer text…" />
          </div>
          <label className="select-field"><Filter size={14} />
            <select value={decision} onChange={(event) => setDecision(event.target.value)}>
              <option value="">All decisions</option>
              <option value="answer">Answered</option>
              <option value="ask_to_repeat">Ask to repeat</option>
              <option value="refuse">Refused</option>
            </select>
          </label>
          <label className="select-field">
            <select value={language} onChange={(event) => setLanguage(event.target.value)}>
              <option value="">All languages</option>
              <option value="hi">Hindi</option>
              <option value="mr">Marathi</option>
              <option value="en">English</option>
            </select>
          </label>
          <span className="filter-count">{data.total} result{data.total === 1 ? '' : 's'}</span>
        </div>

        {error ? <div className="alert alert-error">{error}</div> : null}
        {loading ? <Spinner label="Loading query history…" /> : null}
        {!loading && !data.items.length ? (
          <EmptyState title="No queries match" message="Ask a question in the Farmer Assistant, or clear the filters." icon={Clock} />
        ) : null}

        {!loading && data.items.length ? (
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>When</th>
                  <th>Question</th>
                  <th>Lang</th>
                  <th>Decision</th>
                  <th>Confidence</th>
                  <th>Latency</th>
                  <th>Review</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((item) => (
                  <tr key={item.id} onClick={() => openDetail(item.id)} className="clickable-row">
                    <td className="nowrap">{formatDate(item.created_at)}</td>
                    <td className="question-cell">{item.text}</td>
                    <td><Badge tone="neutral">{item.language?.toUpperCase()}</Badge></td>
                    <td><DecisionBadge decision={item.decision} /></td>
                    <td>{Math.round((item.confidence || 0) * 100)}%</td>
                    <td>{item.latency_ms?.toFixed(0)} ms</td>
                    <td><Badge tone={item.review_status === 'unreviewed' ? 'amber' : 'green'}>{titleCase(item.review_status)}</Badge></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </div>

      {detail ? (
        <Modal wide title="Query detail" subtitle={detailLoading ? 'Loading…' : `${detail.language_name || detail.language} · ${formatDate(detail.created_at)}`} onClose={() => setDetail(null)}>
          {detailLoading ? <Spinner label="Loading query…" /> : (
            <div className="query-detail">
              <div className="detail-headline">
                <DecisionBadge decision={detail.decision} />
                <Badge tone="neutral">{titleCase(detail.intent)}</Badge>
                <Badge tone={detail.review_status === 'unreviewed' ? 'amber' : 'green'}>{titleCase(detail.review_status)}</Badge>
                {detail.simulated ? <Badge tone="amber">Simulated tool</Badge> : null}
              </div>
              <div className="query-question"><span>Question</span><p>{detail.text}</p></div>
              <div className="answer-text compact">{detail.answer}</div>
              <div className="detail-grid">
                <div><span>Confidence</span><strong>{Math.round((detail.confidence || 0) * 100)}%</strong></div>
                <div><span>Intent confidence</span><strong>{Math.round((detail.intent_confidence || 0) * 100)}%</strong></div>
                <div><span>Reason</span><strong>{titleCase(detail.reason_code)}</strong></div>
                <div><span>Generation</span><strong>{detail.generation_provider}</strong></div>
                <div><span>Input mode</span><strong>{titleCase(detail.input_mode)}</strong></div>
                <div><span>Latency</span><strong>{detail.latency_ms?.toFixed(0)} ms</strong></div>
              </div>
              <div className="reason-box"><span>Gate detail</span><p>{detail.reason_detail}</p></div>
              <ConfidenceMeter value={detail.confidence} />
              {detail.evidence?.length ? (
                <div className="content-block">
                  <h3>Retrieved evidence</h3>
                  {detail.evidence.map((item, index) => (
                    <details key={item.chunk_id || index} open={index === 0}>
                      <summary><span>{item.title}</span><span className="evidence-score">score {Number(item.score || 0).toFixed(3)}</span></summary>
                      <p>{item.text}</p>
                    </details>
                  ))}
                </div>
              ) : null}
              <div className="review-form">
                <h3><ThumbsUp size={17} /> Expert review</h3>
                <div className="form-grid">
                  <label><span>Status</span>
                    <select value={review.status} onChange={(event) => setReview({ ...review, status: event.target.value })}>
                      <option value="reviewed">Reviewed</option>
                      <option value="needs_followup">Needs follow-up</option>
                      <option value="dismissed">Dismissed</option>
                    </select>
                  </label>
                  <label><span>Reviewer</span><input value={review.reviewer} onChange={(event) => setReview({ ...review, reviewer: event.target.value })} /></label>
                  <label className="form-wide"><span>Review note</span><textarea rows={2} value={review.note} onChange={(event) => setReview({ ...review, note: event.target.value })} /></label>
                  <label className="form-wide"><span>Corrected answer (optional)</span><textarea rows={3} value={review.corrected_answer} onChange={(event) => setReview({ ...review, corrected_answer: event.target.value })} /></label>
                </div>
                <div className="modal-actions">
                  <button type="button" className="button button-primary" onClick={submitReview} disabled={saving}>
                    {saving ? <RefreshCw className="spin" size={16} /> : <CheckCircle2 size={16} />}
                    Save review
                  </button>
                </div>
              </div>
              {detail.reviewed_at ? <div className="inline-note"><CheckCircle2 size={15} /> Last reviewed {formatDate(detail.reviewed_at)} by {detail.reviewed_by || 'admin'}.</div> : null}
            </div>
          )}
        </Modal>
      ) : null}
    </div>
  );
}
