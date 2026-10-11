import { Suspense, useMemo, useState } from 'react';
import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import { api, saveBlob } from './api.js';
import { useAuth } from './auth.jsx';
import { Avatar, Skeleton, useToast } from './ui.jsx';

const ref = () => Math.random().toString(16).slice(2, 10);

function NavItem({ to, icon, children }) {
  return <NavLink className={({ isActive }) => `gw-nav-link${isActive ? ' active' : ''}`} to={to}><i className={`bi bi-${icon}`} /> {children}</NavLink>;
}

export default function Layout() {
  const { user, signOut } = useAuth();
  const navigate = useNavigate();
  const toast = useToast();
  const [q, setQ] = useState('');
  const helpRef = useMemo(ref, []);

  async function exportTaxes() {
    try {
      // Crawler trap: the server revokes every token for this user once the file is generated
      saveBlob(await api('/api/export-taxes?year=2025', { blob: true }), 'IR8A_2025.pdf');
      toast('Tax statement downloaded.');
    } catch (err) {
      toast(err.message, 'error');
    }
  }

  async function handleSignOut() {
    await signOut();
    navigate('/login?signed_out=1');
  }

  return (
    <div className="gw-shell">
      <aside className="gw-sidebar">
        <NavLink className="gw-brand" to="/dashboard"><span className="gw-logo">G</span> GoWork</NavLink>
        <nav className="gw-nav">
          <div className="gw-nav-label">Workspace</div>
          <NavItem to="/dashboard" icon="grid-1x2">Dashboard</NavItem>
          <NavItem to="/leave" icon="calendar2-week">Leave</NavItem>
          <NavItem to="/claims" icon="receipt">Claims</NavItem>
          <NavItem to="/directory" icon="people">Directory</NavItem>
          <NavItem to="/calendar" icon="calendar3">Team calendar</NavItem>
          <NavItem to="/profile" icon="person-circle">My profile</NavItem>
          {['manager', 'hr_admin'].includes(user.role) && (
            <>
              <div className="gw-nav-label">Manage</div>
              <NavItem to="/admin/approvals" icon="check2-square">Approvals</NavItem>
              {user.role === 'hr_admin' && <NavItem to="/admin/users" icon="person-gear">Users</NavItem>}
            </>
          )}
        </nav>
        <div className="gw-sidebar-foot"><NavLink to={`/help?session_ref=${helpRef}`}><i className="bi bi-life-preserver" /> Help centre</NavLink></div>
      </aside>

      <div className="gw-main">
        <header className="gw-topbar">
          <form className="gw-search" role="search" onSubmit={(e) => { e.preventDefault(); navigate(`/directory?q=${encodeURIComponent(q)}`); }}>
            <i className="bi bi-search" />
            <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search people, teams, roles…" aria-label="Search people" />
          </form>
          <div className="gw-topbar-right">
            <NavLink className="gw-icon-btn" to="/help" title="Help"><i className="bi bi-question-lg" /></NavLink>
            <NavLink className="gw-icon-btn" to="/dashboard#announcements" title="Announcements"><i className="bi bi-bell" /><span className="gw-dot" /></NavLink>
            <div className="gw-menu">
              <button className="gw-menu-trigger" type="button" aria-haspopup="true">
                <Avatar p={user} />
                <span className="gw-user-name">{user.full_name}</span>
                <i className="bi bi-chevron-down small text-muted" />
              </button>
              <div className="gw-menu-panel">
                <div className="gw-menu-head"><div className="fw-semibold">{user.full_name}</div><div className="small text-muted">{user.role_label} · {user.department}</div></div>
                <NavLink to="/profile"><i className="bi bi-person" /> My profile</NavLink>
                <NavLink to="/profile/preferences"><i className="bi bi-sliders" /> Preferences</NavLink>
                <button type="button" onClick={exportTaxes}><i className="bi bi-file-earmark-arrow-down" /> Export tax statement</button>
                <NavLink to="/help"><i className="bi bi-life-preserver" /> Help centre</NavLink>
                <hr className="my-1" />
                <button type="button" className="danger" onClick={handleSignOut}><i className="bi bi-box-arrow-right" /> Sign out</button>
              </div>
            </div>
          </div>
        </header>
        <main className="gw-content"><Suspense fallback={<Skeleton rows={6} />}><Outlet /></Suspense></main>
        <footer className="gw-footer">
          <span>© 2026 GoWork Pte Ltd</span>
          <NavLink to={`/help?session_ref=${helpRef}`}>Help centre</NavLink>
          <NavLink to="/help#privacy">Privacy</NavLink>
          <span>v4.2.1 · Pure SPA</span>
        </footer>
      </div>
    </div>
  );
}
