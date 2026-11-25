import { AlertTriangle, CheckCircle2, Info, Loader2, X, XCircle } from 'lucide-react';
import { titleCase } from '../api.js';

export function Badge({ children, tone = 'neutral', dot = false, className = '' }) {
  return (
    <span className={`badge badge-${tone} ${className}`.trim()}>
      {dot ? <span className="badge-dot" /> : null}
      {children}
    </span>
  );
}

export function DecisionBadge({ decision }) {
  const map = {
    answer: { tone: 'green', label: 'Answered', icon: CheckCircle2 },
    ask_to_repeat: { tone: 'amber', label: 'Needs clarification', icon: AlertTriangle },
    refuse: { tone: 'red', label: 'Refused safely', icon: XCircle },
  };
  const item = map[decision] || { tone: 'neutral', label: titleCase(decision), icon: Info };
  const Icon = item.icon;
  return (
    <Badge tone={item.tone}>
      <Icon size={13} strokeWidth={2.4} />
      {item.label}
    </Badge>
  );
}

export function StatCard({ label, value, hint, icon: Icon, tone = 'green' }) {
  return (
    <div className={`stat-card stat-${tone}`}>
      <div className="stat-icon">{Icon ? <Icon size={20} /> : null}</div>
      <div>
        <div className="stat-value">{value}</div>
        <div className="stat-label">{label}</div>
        {hint ? <div className="stat-hint">{hint}</div> : null}
      </div>
    </div>
  );
}

export function ConfidenceMeter({ value, label = 'Confidence' }) {
  const pct = Math.max(0, Math.min(1, Number(value) || 0));
  const tone = pct >= 0.7 ? 'high' : pct >= 0.5 ? 'mid' : 'low';
  return (
    <div className={`confidence confidence-${tone}`}>
      <div className="confidence-head">
        <span>{label}</span>
        <strong>{Math.round(pct * 100)}%</strong>
      </div>
      <div className="confidence-track">
        <div className="confidence-fill" style={{ width: `${pct * 100}%` }} />
      </div>
    </div>
  );
}

export function Spinner({ label = 'Loading' }) {
  return (
    <div className="spinner-row">
      <Loader2 className="spin" size={18} />
      <span>{label}</span>
    </div>
  );
}

export function EmptyState({ title, message, icon: Icon = Info, action }) {
  return (
    <div className="empty-state">
      <div className="empty-icon"><Icon size={24} /></div>
      <h3>{title}</h3>
      {message ? <p>{message}</p> : null}
      {action}
    </div>
  );
}

export function Modal({ title, subtitle, onClose, children, wide = false }) {
  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={onClose}>
      <div
        className={`modal ${wide ? 'modal-wide' : ''}`}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onMouseDown={(event) => event.stopPropagation()}
      >
        <div className="modal-head">
          <div>
            <h2>{title}</h2>
            {subtitle ? <p>{subtitle}</p> : null}
          </div>
          <button type="button" className="icon-button" onClick={onClose} aria-label="Close">
            <X size={18} />
          </button>
        </div>
        <div className="modal-body">{children}</div>
      </div>
    </div>
  );
}

export function SectionHeader({ eyebrow, title, description, actions }) {
  return (
    <div className="section-header">
      <div>
        {eyebrow ? <div className="eyebrow">{eyebrow}</div> : null}
        <h1>{title}</h1>
        {description ? <p>{description}</p> : null}
      </div>
      {actions ? <div className="section-actions">{actions}</div> : null}
    </div>
  );
}

export function SourceCard({ citation, index }) {
  return (
    <div className="source-card">
      <div className="source-index">{String(index + 1).padStart(2, '0')}</div>
      <div className="source-body">
        <div className="source-title">{citation.title || citation.document_id}</div>
        <div className="source-meta">
          {citation.publisher || citation.source_name || 'Unknown publisher'}
          {citation.publication_date ? ` · ${citation.publication_date}` : ''}
        </div>
        {citation.excerpt ? <p className="source-excerpt">{citation.excerpt}</p> : null}
        <div className="source-tags">
          {citation.is_demo ? <Badge tone="amber">Demo summary</Badge> : <Badge tone="green">Approved source</Badge>}
          {citation.category ? <Badge tone="neutral">{titleCase(citation.category)}</Badge> : null}
          {citation.source_url ? (
            <a className="text-link" href={citation.source_url} target="_blank" rel="noreferrer">
              Open source ↗
            </a>
          ) : null}
        </div>
      </div>
    </div>
  );
}

export function Toggle({ checked, onChange, label, hint }) {
  return (
    <label className="toggle-row">
      <span>
        <strong>{label}</strong>
        {hint ? <small>{hint}</small> : null}
      </span>
      <input type="checkbox" checked={checked} onChange={(event) => onChange(event.target.checked)} />
      <span className="toggle-track" aria-hidden="true"><span /></span>
    </label>
  );
}

export function DataModeBadge({ mode }) {
  const normalized = String(mode || '').toLowerCase();
  if (normalized === 'live') return <Badge tone="green" dot>LIVE</Badge>;
  if (normalized === 'simulated') return <Badge tone="amber" dot>SIMULATED</Badge>;
  return <Badge tone="neutral">{normalized ? normalized.toUpperCase() : 'UNKNOWN'}</Badge>;
}
