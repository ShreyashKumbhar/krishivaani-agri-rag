import { createContext, useContext, useEffect, useMemo, useState } from 'react';
import { NavLink, Route, Routes, useLocation } from 'react-router-dom';
import {
  BookOpenText,
  FlaskConical,
  History,
  KeyRound,
  Leaf,
  LogOut,
  Menu,
  Mic,
  Settings2,
  ShieldCheck,
  Sprout,
  X,
} from 'lucide-react';
import { api, getAdminToken, setAdminToken } from './api.js';
import { Badge, Modal, Spinner } from './components/ui.jsx';
import Assistant from './pages/Assistant.jsx';
import KnowledgeBase from './pages/KnowledgeBase.jsx';
import QueryHistory from './pages/QueryHistory.jsx';
import Evaluation from './pages/Evaluation.jsx';
import Administration from './pages/Administration.jsx';

const AppContext = createContext(null);

export function useApp() {
  return useContext(AppContext);
}

const NAV = [
  { to: '/', label: 'Farmer Assistant', short: 'Assistant', icon: Mic, end: true },
  { to: '/knowledge', label: 'Knowledge Base', short: 'Knowledge', icon: BookOpenText },
  { to: '/history', label: 'Query History', short: 'History', icon: History },
  { to: '/evaluation', label: 'Evaluation', short: 'Evaluation', icon: FlaskConical },
  { to: '/admin', label: 'Administration', short: 'Admin', icon: Settings2 },
];

function Layout({ health, config, onRefresh, adminUser, onOpenLogin, onLogout }) {
  const location = useLocation();
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => {
    setMenuOpen(false);
  }, [location.pathname]);

  const activeLabel = NAV.find((item) => (item.end ? location.pathname === item.to : location.pathname.startsWith(item.to)))?.label;

  return (
    <div className="app-shell">
      <aside className={`sidebar ${menuOpen ? 'sidebar-open' : ''}`}>
        <div className="brand">
          <div className="brand-mark"><Sprout size={24} /></div>
          <div>
            <div className="brand-name">KrishiVaani</div>
            <div className="brand-sub">कृषिवाणी · कृषीवाणी</div>
          </div>
          <button type="button" className="sidebar-close" onClick={() => setMenuOpen(false)} aria-label="Close menu">
            <X size={20} />
          </button>
        </div>

        <div className="sidebar-tagline">
          Voice-first advisory for Hindi &amp; Marathi farmers
        </div>

        <nav className="nav">
          {NAV.map((item) => {
            const Icon = item.icon;
            return (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={({ isActive }) => `nav-item ${isActive ? 'nav-active' : ''}`}
              >
                <Icon size={18} />
                <span>{item.label}</span>
              </NavLink>
            );
          })}
        </nav>

        <div className="sidebar-note">
          <ShieldCheck size={17} />
          <div>
            <strong>Safety gate active</strong>
            <span>Chemical dosage questions are refused and referred to KVK / Kisan Call Centre.</span>
          </div>
        </div>

        <div className="sidebar-footer">
          <div className="helpline">
            <span>Kisan Call Centre</span>
            <strong>1800-180-1551</strong>
          </div>
          <div className="version">v{config?.app?.version || '1.0.0'} · demo build</div>
        </div>
      </aside>

      {menuOpen ? <button type="button" className="sidebar-scrim" onClick={() => setMenuOpen(false)} aria-label="Close menu" /> : null}

      <div className="main-shell">
        <header className="topbar">
          <div className="topbar-left">
            <button type="button" className="icon-button menu-button" onClick={() => setMenuOpen(true)} aria-label="Open menu">
              <Menu size={20} />
            </button>
            <div>
              <div className="topbar-eyebrow">{activeLabel || 'KrishiVaani'}</div>
              <div className="topbar-title">Multilingual agricultural assistant</div>
            </div>
          </div>
          <div className="topbar-right">
            <Badge tone="amber" dot>Demonstration build</Badge>
            {adminUser ? (
              <button type="button" className="button button-secondary" onClick={onLogout} title="Sign out of admin session">
                <LogOut size={14} /> {adminUser}
              </button>
            ) : (
              <button type="button" className="button button-secondary" onClick={onOpenLogin} title="Sign in for admin actions">
                <KeyRound size={14} /> Admin sign in
              </button>
            )}
            <div className={`health-pill ${health?.status === 'ok' ? 'health-ok' : 'health-bad'}`}>
              <span className="health-dot" />
              {health?.status === 'ok' ? `${health.documents} docs · ${health.chunks} chunks` : 'Backend offline'}
            </div>
            <button type="button" className="icon-button" onClick={onRefresh} title="Refresh system status" aria-label="Refresh system status">
              <Leaf size={18} />
            </button>
          </div>
        </header>

        <main className="page">
          <Routes>
            <Route path="/" element={<Assistant />} />
            <Route path="/knowledge" element={<KnowledgeBase />} />
            <Route path="/history" element={<QueryHistory />} />
            <Route path="/evaluation" element={<Evaluation />} />
            <Route path="/admin" element={<Administration />} />
            <Route path="*" element={<Assistant />} />
          </Routes>
        </main>

        <footer className="app-footer">
          <span>KrishiVaani demonstration system · curated demo knowledge base, not official ICAR/KVK advice.</span>
          <span>Mandi data is simulated unless a data.gov.in key is configured.</span>
        </footer>
      </div>
    </div>
  );
}

export default function App() {
  const [health, setHealth] = useState(null);
  const [config, setConfig] = useState(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [refreshKey, setRefreshKey] = useState(0);
  const [adminUser, setAdminUser] = useState('');
  const [showLogin, setShowLogin] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    Promise.all([api.health(), api.config(), api.adminAuthStatus().catch(() => ({ authenticated: false, username: '' }))])
      .then(([healthData, configData, authData]) => {
        if (cancelled) return;
        setHealth(healthData);
        setConfig(configData);
        setAdminUser(authData?.authenticated ? authData.username : '');
        if (!authData?.authenticated && getAdminToken()) setAdminToken('');
        setError('');
      })
      .catch((err) => {
        if (!cancelled) setError(err.message || 'Could not reach the backend.');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [refreshKey]);

  function handleLogout() {
    setAdminToken('');
    setAdminUser('');
  }

  const value = useMemo(
    () => ({
      health,
      config,
      adminUser,
      openLogin: () => setShowLogin(true),
      logoutAdmin: handleLogout,
      refresh: () => setRefreshKey((key) => key + 1),
    }),
    [health, config, adminUser],
  );

  if (loading) {
    return (
      <div className="boot-screen">
        <div className="boot-mark"><Sprout size={34} /></div>
        <h1>KrishiVaani</h1>
        <p>Starting the multilingual agricultural assistant…</p>
        <Spinner label="Connecting to backend" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="boot-screen">
        <div className="boot-mark boot-mark-error"><X size={32} /></div>
        <h1>Backend not reachable</h1>
        <p>{error}</p>
        <div className="boot-help">
          Start the API from <code>agri_assistant/backend</code>:
          <code>python -m uvicorn app.main:app --reload --port 8000</code>
        </div>
        <button type="button" className="button button-primary" onClick={() => setRefreshKey((key) => key + 1)}>
          Try again
        </button>
      </div>
    );
  }

  return (
    <AppContext.Provider value={value}>
      <Layout
        health={health}
        config={config}
        adminUser={adminUser}
        onOpenLogin={() => setShowLogin(true)}
        onLogout={handleLogout}
        onRefresh={() => setRefreshKey((key) => key + 1)}
      />
      {showLogin ? (
        <AdminLoginModal
          onClose={() => setShowLogin(false)}
          onSuccess={(username) => {
            setAdminUser(username);
            setShowLogin(false);
          }}
        />
      ) : null}
    </AppContext.Provider>
  );
}

function AdminLoginModal({ onClose, onSuccess }) {
  const [username, setUsername] = useState('admin');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      const res = await api.adminLogin({ username, password });
      setAdminToken(res.token);
      onSuccess(res.username || username);
    } catch (err) {
      setError(err.message || 'Sign in failed');
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal title="Administrator sign in" subtitle="Required for knowledge uploads, approvals, glossary edits, query reviews and running evaluation." onClose={onClose}>
      <form className="upload-form" onSubmit={submit}>
        <div className="form-grid">
          <label className="form-wide">
            <span>Username</span>
            <input value={username} onChange={(e) => setUsername(e.target.value)} required />
          </label>
          <label className="form-wide">
            <span>Password</span>
            <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="Enter admin password" required />
          </label>
        </div>
        {error ? <div className="alert alert-error">{error}</div> : null}
        <div className="modal-actions">
          <button type="button" className="button button-secondary" onClick={onClose}>Cancel</button>
          <button type="submit" className="button button-primary" disabled={busy}>
            <KeyRound size={16} /> {busy ? 'Signing in…' : 'Sign in'}
          </button>
        </div>
      </form>
    </Modal>
  );
}
