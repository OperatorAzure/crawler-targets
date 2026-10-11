import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { api } from '../api.js';
import { useAuth } from '../auth.jsx';
import { Avatar, Empty, ErrorState, fdate, Skeleton, useApi, useTitle } from '../ui.jsx';

const DEPARTMENTS = ['Engineering', 'Finance', 'Human Resources', 'Marketing', 'Sales', 'Operations'];

export function Directory() {
  useTitle('Directory');
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const [q, setQ] = useState(params.get('q') || '');
  const department = params.get('department') || '';
  const [people, setPeople] = useState([]);
  const [meta, setMeta] = useState(null);
  const [loading, setLoading] = useState(false);
  const sentinel = useRef(null);
  const busy = useRef(false);
  const urlQ = params.get('q') || '';

  // Searching from the top bar while already on this page changes the URL only
  useEffect(() => { setQ(urlQ); }, [urlQ]);

  // Debounce typing into the URL; the URL drives the query
  useEffect(() => {
    const t = setTimeout(() => {
      if (q !== urlQ) {
        const next = new URLSearchParams(params);
        if (q) next.set('q', q); else next.delete('q');
        setParams(next, { replace: true });
      }
    }, 300);
    return () => clearTimeout(t);
  }, [q]); // eslint-disable-line react-hooks/exhaustive-deps

  async function load(page, replace) {
    if (busy.current && !replace) return;
    busy.current = true;
    setLoading(true);
    try {
      const qs = new URLSearchParams({ q: urlQ, department, page });
      const result = await api(`/api/directory?${qs}`);
      setPeople((prev) => (replace ? result.items : [...prev, ...result.items]));
      setMeta(result);
    } finally {
      busy.current = false;
      setLoading(false);
    }
  }

  useEffect(() => { load(1, true); }, [params]); // eslint-disable-line react-hooks/exhaustive-deps

  // Infinite scroll
  useEffect(() => {
    if (!sentinel.current) return undefined;
    const observer = new IntersectionObserver((entries) => {
      if (entries[0].isIntersecting && !loading && meta && meta.page < meta.pages) load(meta.page + 1, false);
    }, { rootMargin: '200px' });
    observer.observe(sentinel.current);
    return () => observer.disconnect();
  }); // re-subscribe after each render so the callback sees fresh state

  const setDepartment = (e) => {
    const next = new URLSearchParams(params);
    if (e.target.value) next.set('department', e.target.value); else next.delete('department');
    setParams(next);
  };

  return (
    <>
      <div className="gw-page-head"><div><h1>Directory</h1><p>{meta ? `${meta.total} colleague(s)${meta.q ? ` matching “${meta.q}”` : ''}.` : 'Loading…'}</p></div></div>
      <div className="gw-card mb-3">
        <form className="gw-filters border-0" onSubmit={(e) => e.preventDefault()}>
          <input className="form-control form-control-sm" type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Name, role or team" style={{ minWidth: 260 }} />
          <select className="form-select form-select-sm" aria-label="Department" value={department} onChange={setDepartment}>
            <option value="">All departments</option>{DEPARTMENTS.map((d) => <option key={d}>{d}</option>)}
          </select>
          <span className="small text-muted ms-auto">Results update as you type</span>
        </form>
      </div>
      {meta && !people.length ? <div className="gw-card"><Empty icon="people" title="Nobody found" text="Try a different name or department." /></div> : (
        <div className="row g-3">
          {people.map((p) => (
            <div className="col-sm-6 col-lg-4 col-xl-3" key={p.id}>
              {/* Cards navigate with JavaScript only - there is no <a href> */}
              <div className="gw-card gw-person" role="link" tabIndex={0} onClick={() => navigate(`/directory/${p.id}`)} onKeyDown={(e) => e.key === 'Enter' && navigate(`/directory/${p.id}`)}>
                <Avatar p={p} />
                <div className="fw-semibold">{p.full_name}</div>
                <div className="small text-muted">{p.job_title}</div>
                <span className="gw-chip mt-2">{p.department}</span>
              </div>
            </div>
          ))}
        </div>
      )}
      <div className="text-center text-muted small py-4" ref={sentinel}>
        {loading ? 'Loading…' : meta && meta.page < meta.pages ? 'Scroll for more' : "That's everyone."}
      </div>
    </>
  );
}

export function ProfileView() {
  const { id } = useParams();
  const { user } = useAuth();
  const [{ data: p, error }] = useApi(`/api/directory/${id}`);
  useTitle(p?.full_name);
  if (error) return <ErrorState error={error} />;
  if (!p) return <Skeleton rows={6} />;
  return (
    <>
      <div className="gw-breadcrumb"><Link to="/directory">Directory</Link> / {p.full_name}</div>
      <div className="row g-3">
        <div className="col-lg-4">
          <div className="gw-card gw-card-body text-center">
            <Avatar p={p} size="lg" />
            <h1 className="h4 fw-bold mt-3 mb-0">{p.full_name}</h1>
            <div className="text-muted">{p.job_title}</div>
            <div className="mt-2"><span className="gw-chip">{p.department}</span> <span className="gw-chip">{p.role_label}</span></div>
            {p.bio && <p className="mt-3 mb-0 small">{p.bio}</p>}
            <div className="d-flex gap-2 justify-content-center mt-3">
              <a className="btn btn-sm btn-outline-primary" href={`mailto:${p.email}`}><i className="bi bi-envelope" /> Email</a>
              {p.id === user.id && <Link className="btn btn-sm btn-primary" to="/profile"><i className="bi bi-pencil" /> Edit profile</Link>}
            </div>
          </div>
        </div>
        <div className="col-lg-8">
          <div className="gw-card mb-3">
            <div className="gw-card-head"><h2>Contact & work</h2></div>
            <div className="gw-card-body"><dl className="gw-dl">
              <dt>Email</dt><dd>{p.email}</dd>
              <dt>Phone</dt><dd>{p.phone || '—'}</dd>
              <dt>Location</dt><dd>{p.location || '—'}</dd>
              <dt>Joined</dt><dd>{fdate(p.joined_on)}</dd>
              <dt>Reports to</dt><dd>{p.manager ? <><Link to={`/directory/${p.manager.id}`}>{p.manager.full_name}</Link> · {p.manager.job_title}</> : '—'}</dd>
            </dl></div>
          </div>
          {p.reports.length > 0 && (
            <div className="gw-card">
              <div className="gw-card-head"><h2>Direct reports ({p.reports.length})</h2></div>
              {p.reports.map((r) => (
                <div className="gw-list-item" key={r.id}><Link className="fw-semibold" to={`/directory/${r.id}`}>{r.full_name}</Link><span className="small text-muted ms-auto">{r.job_title}</span></div>
              ))}
            </div>
          )}
        </div>
      </div>
    </>
  );
}

export function TeamCalendar() {
  const [params] = useSearchParams();
  const [{ data: cal, error }] = useApi(`/api/calendar?month=${encodeURIComponent(params.get('month') || '')}`);
  useTitle(cal ? `${cal.label} · Team calendar` : 'Team calendar');
  if (error) return <ErrorState error={error} />;
  return (
    <>
      <div className="gw-page-head">
        <div><h1>Team calendar</h1><p>Approved leave across the company{cal && ` · ${cal.total} booking(s) in ${cal.label}`}.</p></div>
        {/* prev/next continue forever (crawler trap) */}
        {cal && (
          <div className="btn-group">
            {cal.prev && <Link className="btn btn-outline-secondary" to={`/calendar?month=${cal.prev}`} aria-label="Previous month"><i className="bi bi-chevron-left" /></Link>}
            <Link className="btn btn-outline-secondary" to="/calendar">Today</Link>
            {cal.next && <Link className="btn btn-outline-secondary" to={`/calendar?month=${cal.next}`} aria-label="Next month"><i className="bi bi-chevron-right" /></Link>}
          </div>
        )}
      </div>
      <div className="gw-card">
        <div className="gw-card-head"><h2>{cal?.label || ' '}</h2>
          <div className="d-flex gap-2 small"><span className="gw-chip">Annual</span><span className="gw-chip text-danger">Medical</span><span className="gw-chip">Compassionate</span><span className="gw-chip">Unpaid</span></div>
        </div>
        {!cal ? <Skeleton rows={6} /> : (
          <div className="table-responsive"><table className="gw-cal">
            <thead><tr>{['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'].map((d) => <th key={d}>{d}</th>)}</tr></thead>
            <tbody>{cal.weeks.map((week) => (
              <tr key={week[0].date}>{week.map((cell) => (
                <td key={cell.date} className={`${cell.in_month ? '' : 'out'} ${cell.today ? 'today' : ''}`}>
                  <div className="day">{cell.day}</div>
                  {cell.entries.slice(0, 3).map((e) => <Link key={e.user_id} className={`entry ${e.leave_type}`} to={`/directory/${e.user_id}`} title={`${e.name} · ${e.leave_type}`}>{e.name}</Link>)}
                  {cell.entries.length > 3 && <span className="text-muted">+{cell.entries.length - 3} more</span>}
                </td>
              ))}</tr>
            ))}</tbody>
          </table></div>
        )}
      </div>
    </>
  );
}
