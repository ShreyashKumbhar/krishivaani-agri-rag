import { useEffect, useMemo, useState } from 'react';
import {
  BookOpenText,
  CheckCircle2,
  Database,
  FileText,
  Filter,
  Layers,
  Plus,
  RefreshCw,
  Search,
  ShieldCheck,
  Trash2,
  UploadCloud,
  XCircle,
} from 'lucide-react';
import { api, formatDate, titleCase } from '../api.js';
import { useApp } from '../App.jsx';
import {
  Badge,
  EmptyState,
  Modal,
  SectionHeader,
  Spinner,
  StatCard,
} from '../components/ui.jsx';

const EMPTY_FORM = {
  title: '',
  publisher: 'Admin upload',
  source_name: 'Admin upload',
  source_url: '',
  publication_date: '',
  licence: 'Not specified by uploader',
  category: 'crop_advice',
  crops: 'all',
  states: 'Maharashtra',
  content_note: 'Uploaded by an administrator. Approval is required before retrieval.',
  approval_status: 'pending',
};

const CATEGORIES = ['pest_disease', 'crop_advice', 'scheme', 'pesticide_safety', 'weather', 'market', 'other'];

export default function KnowledgeBase() {
  const { adminUser, openLogin } = useApp();
  const [data, setData] = useState({ items: [], total: 0, stats: null });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [query, setQuery] = useState('');
  const [status, setStatus] = useState('');
  const [category, setCategory] = useState('');
  const [showUpload, setShowUpload] = useState(false);
  const [uploadSeed, setUploadSeed] = useState(null);
  const [detail, setDetail] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [busy, setBusy] = useState('');

  async function load() {
    setLoading(true);
    setError('');
    try {
      const result = await api.documents({ q: query, status, category, limit: 200 });
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
  }, [query, status, category]);

  async function openDetail(id) {
    setDetailLoading(true);
    setDetail({ id });
    try {
      const document = await api.document(id);
      setDetail(document);
    } catch (err) {
      setError(err.message);
      setDetail(null);
    } finally {
      setDetailLoading(false);
    }
  }

  async function changeStatus(document, nextStatus) {
    setBusy(document.id);
    try {
      await api.setDocumentStatus(document.id, { status: nextStatus, reviewer: 'admin', note: `Set via dashboard` });
      await load();
      if (detail?.id === document.id) setDetail(await api.document(document.id));
    } catch (err) {
      if (err.status === 401) openLogin();
      setError(err.message);
    } finally {
      setBusy('');
    }
  }

  async function removeDocument(document) {
    if (!adminUser) {
      openLogin();
      return;
    }
    if (!window.confirm(`Delete “${document.title_en}”? This removes its chunks from retrieval.`)) return;
    setBusy(document.id);
    try {
      await api.deleteDocument(document.id);
      setDetail(null);
      await load();
    } catch (err) {
      if (err.status === 401) openLogin();
      setError(err.message);
    } finally {
      setBusy('');
    }
  }

  async function reindex() {
    if (!adminUser) {
      openLogin();
      return;
    }
    setBusy('reindex');
    try {
      await api.reindex();
      await load();
    } catch (err) {
      if (err.status === 401) openLogin();
      setError(err.message);
    } finally {
      setBusy('');
    }
  }

  const stats = data.stats || {};
  const categories = useMemo(() => stats.categories || [], [stats.categories]);

  return (
    <div>
      <SectionHeader
        eyebrow="Knowledge base"
        title="Approved agricultural knowledge, with provenance"
        description="The demo corpus is curated for this build. Uploads stay pending until an administrator approves them; only approved chunks are indexed for retrieval."
        actions={
          <>
            <button type="button" className="button button-secondary" onClick={reindex} disabled={busy === 'reindex'}>
              <RefreshCw size={16} className={busy === 'reindex' ? 'spin' : ''} /> Rebuild index
            </button>
            <button type="button" className="button button-primary" onClick={() => { if (!adminUser) { openLogin(); return; } setUploadSeed(null); setShowUpload(true); }}>
              <Plus size={16} /> Upload document
            </button>
          </>
        }
      />

      <div className="stats-grid">
        <StatCard label="Documents" value={stats.documents ?? '—'} hint={`${stats.approved ?? 0} approved`} icon={BookOpenText} />
        <StatCard label="Chunks indexed" value={stats.chunks ?? '—'} hint="BM25 + dense vectors" icon={Layers} tone="blue" />
        <StatCard label="Pending review" value={stats.pending ?? '—'} hint="Not retrievable yet" icon={ShieldCheck} tone="amber" />
        <StatCard label="Demo summaries" value={stats.demo_documents ?? '—'} hint="Curated, not official ICAR/KVK" icon={Database} tone="violet" />
      </div>

      <div className="panel">
        <div className="filter-bar">
          <div className="search-field">
            <Search size={16} />
            <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search title, source or English content…" />
          </div>
          <label className="select-field"><Filter size={14} />
            <select value={status} onChange={(event) => setStatus(event.target.value)}>
              <option value="">All statuses</option>
              <option value="approved">Approved</option>
              <option value="pending">Pending</option>
              <option value="superseded">Superseded</option>
              <option value="rejected">Rejected</option>
            </select>
          </label>
          <label className="select-field">
            <select value={category} onChange={(event) => setCategory(event.target.value)}>
              <option value="">All categories</option>
              {CATEGORIES.map((item) => <option key={item} value={item}>{titleCase(item)}</option>)}
            </select>
          </label>
          <span className="filter-count">{data.total} result{data.total === 1 ? '' : 's'}</span>
        </div>

        {error ? <div className="alert alert-error">{error}</div> : null}
        {loading ? <Spinner label="Loading documents…" /> : null}

        {!loading && !data.items.length ? (
          <EmptyState title="No documents match" message="Try a different search or clear the filters." icon={FileText} />
        ) : null}

        {!loading && data.items.length ? (
          <div className="document-list">
            {data.items.map((document) => (
              <article key={document.id} className="document-row">
                <button type="button" className="document-main" onClick={() => openDetail(document.id)}>
                  <div className="doc-icon"><FileText size={18} /></div>
                  <div className="doc-copy">
                    <div className="doc-title">{document.title_en}</div>
                    <div className="doc-meta">
                      {document.publisher || 'Unknown publisher'} · {document.source_name || 'No source name'}
                      {document.publication_date ? ` · ${document.publication_date}` : ''}
                    </div>
                    <div className="doc-tags">
                      <Badge tone={document.approval_status === 'approved' ? 'green' : document.approval_status === 'pending' ? 'amber' : document.approval_status === 'superseded' ? 'neutral' : 'red'}>
                        {titleCase(document.approval_status)}
                      </Badge>
                      <Badge tone="neutral">v{document.version || '1.0'}</Badge>
                      <Badge tone="neutral">{titleCase(document.category)}</Badge>
                      {document.is_demo ? <Badge tone="amber">Demo summary</Badge> : <Badge tone="green">Admin source</Badge>}
                      {document.crops?.length ? <Badge tone="neutral">{document.crops.join(', ')}</Badge> : null}
                      <span className="doc-chunks">{document.chunk_count} chunks</span>
                    </div>
                  </div>
                </button>
                <div className="doc-actions">
                  {document.approval_status !== 'approved' ? (
                    <button type="button" className="icon-button icon-approve" title="Approve" disabled={busy === document.id} onClick={() => changeStatus(document, 'approved')}>
                      <CheckCircle2 size={17} />
                    </button>
                  ) : null}
                  {document.approval_status !== 'rejected' ? (
                    <button type="button" className="icon-button icon-reject" title="Reject" disabled={busy === document.id} onClick={() => changeStatus(document, 'rejected')}>
                      <XCircle size={17} />
                    </button>
                  ) : null}
                  <button type="button" className="icon-button icon-delete" title="Delete" disabled={busy === document.id} onClick={() => removeDocument(document)}>
                    <Trash2 size={17} />
                  </button>
                </div>
              </article>
            ))}
          </div>
        ) : null}
      </div>

      {categories.length ? (
        <div className="category-strip">
          <span>Corpus by category</span>
          {categories.map((item) => (
            <button key={item.category} type="button" className={category === item.category ? 'active' : ''} onClick={() => setCategory(category === item.category ? '' : item.category)}>
              {titleCase(item.category)} <strong>{item.count}</strong>
            </button>
          ))}
        </div>
      ) : null}

      {showUpload ? (
        <UploadModal
          seed={uploadSeed}
          onAuthRequired={openLogin}
          onClose={() => { setShowUpload(false); setUploadSeed(null); }}
          onUploaded={async () => { setShowUpload(false); setUploadSeed(null); await load(); }}
        />
      ) : null}

      {detail ? (
        <Modal
          wide
          title={detail.title_en || 'Document detail'}
          subtitle={detailLoading ? 'Loading document…' : `${detail.publisher || 'Unknown publisher'} · ${detail.approval_status}`}
          onClose={() => setDetail(null)}
        >
          {detailLoading ? <Spinner label="Loading chunks…" /> : (
            <div className="document-detail">
              <div className="detail-grid">
                <div><span>Status</span><strong>{titleCase(detail.approval_status)}</strong></div>
                <div><span>Category</span><strong>{titleCase(detail.category)}</strong></div>
                <div><span>Publisher</span><strong>{detail.publisher || '—'}</strong></div>
                <div><span>Source</span><strong>{detail.source_name || '—'}</strong></div>
                <div><span>Published</span><strong>{detail.publication_date || '—'}</strong></div>
                <div><span>Licence</span><strong>{detail.licence || '—'}</strong></div>
                <div><span>Created</span><strong>{formatDate(detail.created_at)}</strong></div>
                <div><span>Version</span><strong>v{detail.version || '1.0'}</strong></div>
                <div><span>Chunks</span><strong>{detail.chunk_count}</strong></div>
              </div>
              {detail.versions?.length > 1 ? (
                <div className="content-block">
                  <h3>Version history</h3>
                  <div className="chunk-list">
                    {detail.versions.map((ver) => (
                      <div key={ver.id} className="detail-note">
                        <Badge tone={ver.approval_status === 'approved' ? 'green' : ver.approval_status === 'superseded' ? 'neutral' : 'amber'}>
                          v{ver.version} · {titleCase(ver.approval_status)}
                        </Badge>
                        <span>{ver.id === detail.id ? 'Current view' : formatDate(ver.created_at)}</span>
                      </div>
                    ))}
                  </div>
                </div>
              ) : null}
              {detail.source_url ? <a className="text-link" href={detail.source_url} target="_blank" rel="noreferrer">Open original source ↗</a> : null}
              <div className="detail-note"><ShieldCheck size={16} /> {detail.content_note}</div>
              {['en', 'hi', 'mr'].map((lang) => (
                detail[`content_${lang}`] ? (
                  <div key={lang} className="content-block">
                    <h3>{lang === 'en' ? 'English' : lang === 'hi' ? 'हिंदी' : 'मराठी'} content</h3>
                    <p>{detail[`content_${lang}`]}</p>
                  </div>
                ) : null
              ))}
              {detail.chunks?.length ? (
                <div className="content-block">
                  <h3>Indexed chunks</h3>
                  <div className="chunk-list">
                    {detail.chunks.map((chunk) => (
                      <details key={chunk.id}>
                        <summary><Badge tone="neutral">{chunk.language.toUpperCase()}</Badge> Chunk {chunk.chunk_index + 1} · {chunk.char_count} chars</summary>
                        <p>{chunk.text}</p>
                      </details>
                    ))}
                  </div>
                </div>
              ) : null}
              <div className="modal-actions">
                <button
                  type="button"
                  className="button button-secondary"
                  onClick={() => {
                    if (!adminUser) { openLogin(); return; }
                    setUploadSeed({
                      parent_id: detail.parent_id || detail.id,
                      title: detail.title_en || '',
                      publisher: detail.publisher || 'Admin upload',
                      source_name: detail.source_name || 'Admin upload',
                      source_url: detail.source_url || '',
                      publication_date: detail.publication_date || '',
                      licence: detail.licence || 'Not specified by uploader',
                      category: detail.category || 'crop_advice',
                      crops: (detail.crops || []).join(', ') || 'all',
                      states: (detail.states || []).join(', ') || 'Maharashtra',
                    });
                    setDetail(null);
                    setShowUpload(true);
                  }}
                >
                  <UploadCloud size={16} /> Upload new version
                </button>
                {detail.approval_status !== 'approved' ? (
                  <button type="button" className="button button-primary" onClick={() => changeStatus(detail, 'approved')} disabled={busy === detail.id}>
                    <CheckCircle2 size={16} /> Approve &amp; index
                  </button>
                ) : null}
                {detail.approval_status !== 'rejected' ? (
                  <button type="button" className="button button-secondary" onClick={() => changeStatus(detail, 'rejected')} disabled={busy === detail.id}>
                    <XCircle size={16} /> Reject
                  </button>
                ) : null}
                <button type="button" className="button button-danger" onClick={() => removeDocument(detail)} disabled={busy === detail.id}>
                  <Trash2 size={16} /> Delete
                </button>
              </div>
            </div>
          )}
        </Modal>
      ) : null}
    </div>
  );
}

function UploadModal({ seed, onAuthRequired, onClose, onUploaded }) {
  const [form, setForm] = useState(() => ({ ...EMPTY_FORM, ...(seed || {}) }));
  const [file, setFile] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  function update(key, value) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  async function submit(event) {
    event.preventDefault();
    if (!file) {
      setError('Choose a .txt, .md or .pdf file to upload.');
      return;
    }
    setBusy(true);
    setError('');
    const payload = new FormData();
    Object.entries(form).forEach(([key, value]) => payload.append(key, value));
    payload.append('file', file);
    try {
      await api.uploadDocument(payload);
      await onUploaded();
    } catch (err) {
      if (err.status === 401) onAuthRequired?.();
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal title="Upload a knowledge document" subtitle="Only .txt, .md and .pdf are accepted. Pending uploads are not retrievable until approved." onClose={onClose} wide>
      <form className="upload-form" onSubmit={submit}>
        <label className="file-drop">
          <UploadCloud size={26} />
          <strong>{file ? file.name : 'Choose a document'}</strong>
          <span>Text, Markdown or PDF · up to 20 MB</span>
          <input type="file" accept=".txt,.md,.pdf,text/plain,text/markdown,application/pdf" onChange={(event) => setFile(event.target.files?.[0] || null)} />
        </label>
        <div className="form-grid">
          <label><span>Title</span><input value={form.title} onChange={(event) => update('title', event.target.value)} placeholder="e.g. Cotton pest scouting note" /></label>
          <label><span>Publisher</span><input value={form.publisher} onChange={(event) => update('publisher', event.target.value)} /></label>
          <label><span>Source name</span><input value={form.source_name} onChange={(event) => update('source_name', event.target.value)} /></label>
          <label><span>Source URL</span><input value={form.source_url} onChange={(event) => update('source_url', event.target.value)} placeholder="https://…" /></label>
          <label><span>Publication date</span><input value={form.publication_date} onChange={(event) => update('publication_date', event.target.value)} placeholder="YYYY-MM-DD" /></label>
          <label><span>Licence</span><input value={form.licence} onChange={(event) => update('licence', event.target.value)} /></label>
          <label><span>Category</span>
            <select value={form.category} onChange={(event) => update('category', event.target.value)}>
              {CATEGORIES.map((item) => <option key={item} value={item}>{titleCase(item)}</option>)}
            </select>
          </label>
          <label><span>Crops (comma separated or all)</span><input value={form.crops} onChange={(event) => update('crops', event.target.value)} /></label>
          <label><span>States</span><input value={form.states} onChange={(event) => update('states', event.target.value)} /></label>
          <label><span>Approval on upload</span>
            <select value={form.approval_status} onChange={(event) => update('approval_status', event.target.value)}>
              <option value="pending">Pending review</option>
              <option value="approved">Approve immediately</option>
            </select>
          </label>
          <label className="form-wide"><span>Content note</span><textarea rows={2} value={form.content_note} onChange={(event) => update('content_note', event.target.value)} /></label>
        </div>
        {error ? <div className="alert alert-error">{error}</div> : null}
        <div className="modal-actions">
          <button type="button" className="button button-secondary" onClick={onClose}>Cancel</button>
          <button type="submit" className="button button-primary" disabled={busy}>
            {busy ? <RefreshCw className="spin" size={16} /> : <UploadCloud size={16} />}
            {busy ? 'Uploading…' : 'Upload document'}
          </button>
        </div>
      </form>
    </Modal>
  );
}
