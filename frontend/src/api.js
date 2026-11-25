const BASE = import.meta.env.VITE_API_BASE || '/api';
const TOKEN_KEY = 'krishivaani_admin_token';

export function getAdminToken() {
  try {
    return sessionStorage.getItem(TOKEN_KEY) || '';
  } catch {
    return '';
  }
}

export function setAdminToken(token) {
  try {
    if (token) sessionStorage.setItem(TOKEN_KEY, token);
    else sessionStorage.removeItem(TOKEN_KEY);
  } catch {
    // Ignore storage errors in restricted contexts.
  }
}

async function readError(response) {
  let message = `${response.status} ${response.statusText}`;
  try {
    const body = await response.json();
    message = body.detail || body.message || body.error || message;
  } catch {
    // Keep the HTTP status text when the body is not JSON.
  }
  const error = new Error(message);
  error.status = response.status;
  return error;
}

async function request(path, options = {}) {
  const token = getAdminToken();
  const baseHeaders = options.body instanceof FormData ? {} : { 'Content-Type': 'application/json' };
  if (token) baseHeaders.Authorization = `Bearer ${token}`;
  const response = await fetch(`${BASE}${path}`, {
    ...options,
    headers: { ...baseHeaders, ...(options.headers || {}) },
  });
  if (!response.ok) throw await readError(response);
  if (response.status === 204) return null;
  const type = response.headers.get('content-type') || '';
  if (type.includes('application/json')) return response.json();
  return response.text();
}

function queryString(params = {}) {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') search.set(key, value);
  });
  const value = search.toString();
  return value ? `?${value}` : '';
}

export const api = {
  health: () => request('/health'),
  config: () => request('/config'),
  samples: (language) => request(`/samples?language=${language}`),

  ask: (payload) => request('/assistant/query', { method: 'POST', body: JSON.stringify(payload) }),
  history: (params) => request(`/history${queryString(params)}`),
  historyDetail: (id) => request(`/history/${id}`),
  feedback: (payload) => request('/feedback', { method: 'POST', body: JSON.stringify(payload) }),

  toolCatalog: () => request('/tools/catalog'),
  mandi: (commodity, market) => request(`/tools/mandi${queryString({ commodity, market })}`),
  weather: (district) => request(`/tools/weather${queryString({ district })}`),
  speechInfo: () => request('/speech/info'),

  async synthesize(text, language) {
    const response = await fetch(`${BASE}/speech/synthesize`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, language }),
    });
    if (!response.ok) throw await readError(response);
    return response.blob();
  },

  documents: (params) => request(`/knowledge/documents${queryString(params)}`),
  document: (id) => request(`/knowledge/documents/${id}`),
  knowledgeStats: () => request('/knowledge/stats'),
  uploadDocument: (formData) =>
    request('/knowledge/upload', { method: 'POST', body: formData }),
  setDocumentStatus: (id, payload) =>
    request(`/knowledge/documents/${id}/status`, { method: 'POST', body: JSON.stringify(payload) }),
  deleteDocument: (id) => request(`/knowledge/documents/${id}`, { method: 'DELETE' }),
  reindex: () => request('/knowledge/reindex', { method: 'POST' }),

  overview: () => request('/admin/overview'),
  adminLogin: (payload) => request('/admin/login', { method: 'POST', body: JSON.stringify(payload) }),
  adminAuthStatus: () => request('/admin/auth/status'),
  adminQueries: (params) => request(`/admin/queries${queryString(params)}`),
  refusals: (params) => request(`/admin/refusals${queryString(params)}`),
  reviewQuery: (id, payload) =>
    request(`/admin/queries/${id}/review`, { method: 'POST', body: JSON.stringify(payload) }),
  feedbackList: (params) => request(`/admin/feedback${queryString(params)}`),
  reviewFeedback: (id) => request(`/admin/feedback/${id}/review`, { method: 'POST' }),
  glossary: () => request('/admin/glossary'),
  addGlossary: (payload) => request('/admin/glossary', { method: 'POST', body: JSON.stringify(payload) }),
  deleteGlossary: (id) => request(`/admin/glossary/${id}`, { method: 'DELETE' }),
  audit: (limit = 100) => request(`/admin/audit?limit=${limit}`),
  system: () => request('/admin/system'),
  safety: () => request('/admin/safety'),
  sources: () => request('/admin/sources'),

  evaluationCases: () => request('/evaluation/cases'),
  evaluationRuns: () => request('/evaluation/runs'),
  evaluationLatest: () => request('/evaluation/latest'),
  evaluationRun: (id) => request(`/evaluation/runs/${id}`),
  runEvaluation: () => request('/evaluation/run', { method: 'POST' }),
  reportUrl: `${BASE}/evaluation/report`,
  resultsUrl: `${BASE}/evaluation/results.json`,
};

export function formatDate(value) {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat('en-IN', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date);
}

export function percent(value, digits = 0) {
  if (value === null || value === undefined) return '—';
  return `${(Number(value) * 100).toFixed(digits)}%`;
}

export function titleCase(value) {
  if (!value) return '—';
  return String(value)
    .replaceAll('_', ' ')
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}
