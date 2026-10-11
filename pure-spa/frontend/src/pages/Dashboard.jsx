import { useMemo } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useAuth } from '../auth.jsx';
import { Avatar, Badge, Empty, ErrorState, fdate, PageHead, Skeleton, useApi, useTitle } from '../ui.jsx';

const ref = () => Math.random().toString(16).slice(2, 10);

function Stat({ icon, tone = '', value, suffix, label }) {
  return (
    <div className="col-sm-6 col-xl-3"><div className="gw-card gw-stat">
      <div className={`gw-stat-icon ${tone}`}><i className={`bi bi-${icon}`} /></div>
      <div><div className="gw-stat-value">{value}{suffix && <small className="fs-6 text-muted"> {suffix}</small>}</div><div className="gw-stat-label">{label}</div></div>
    </div></div>
  );
}

function AnnouncementList() {
  // Slow endpoint (~1.2 s); links get a fresh random ?ref= on every render (crawler trap)
  const [{ data }] = useApi('/api/announcements?limit=5');
  if (!data) return <Skeleton rows={4} />;
  return data.items.map((a) => (
    <div className="gw-list-item" key={a.id}>
      <div className={`gw-stat-icon ${a.pinned ? 'amber' : ''}`} style={{ width: 36, height: 36, fontSize: '1rem' }}><i className={`bi bi-${a.pinned ? 'pin-angle' : 'megaphone'}`} /></div>
      <div><Link className="fw-semibold d-block text-dark" to={`/announcements/${a.id}?ref=${ref()}`}>{a.title}</Link><div className="small text-muted">{fdate(a.created_at)}</div></div>
    </div>
  ));
}

export function Dashboard() {
  useTitle('Dashboard');
  const { user } = useAuth();
  const [{ data, error }] = useApi('/api/dashboard');
  if (error) return <ErrorState error={error} />;
  if (!data) return <Skeleton rows={8} />;
  const [annual, medical] = data.balances;
  const next = data.upcoming_leave;

  return (
    <>
      <PageHead title={`Welcome back, ${user.full_name.split(' ')[0]} 👋`} subtitle="Here's what's happening with your work today.">
        <div className="d-flex gap-2">
          <Link className="btn btn-outline-primary" to="/claims/new"><i className="bi bi-plus-lg" /> New claim</Link>
          <Link className="btn btn-primary" to="/leave/apply"><i className="bi bi-calendar-plus" /> Apply for leave</Link>
        </div>
      </PageHead>

      {data.approvals_waiting > 0 && (
        <div className="alert alert-warning d-flex align-items-center gap-2">
          <i className="bi bi-hourglass-split" />
          <span><strong>{data.approvals_waiting}</strong> request(s) from your team are waiting for your approval.</span>
          <Link className="ms-auto btn btn-sm btn-warning" to="/admin/approvals">Review now</Link>
        </div>
      )}

      <div className="row g-3 mb-4">
        <Stat icon="sun" value={annual.remaining} suffix={`/ ${annual.entitlement}`} label="Annual leave left" />
        <Stat icon="heart-pulse" tone="rose" value={medical.remaining} suffix={`/ ${medical.entitlement}`} label="Medical leave left" />
        <Stat icon="hourglass-split" tone="amber" value={data.pending_leaves} label="Leave requests pending" />
        <Stat icon="receipt" tone="violet" value={data.pending_claims_amount} label={`${data.pending_claims} claim(s) pending`} />
      </div>

      <div className="row g-3">
        <div className="col-lg-8">
          <div className="gw-card mb-3">
            <div className="gw-card-head"><h2>Recent leave requests</h2><Link className="small" to="/leave">View all</Link></div>
            {data.recent_leaves.length ? (
              <div className="table-responsive"><table className="table gw-table">
                <thead><tr><th>Type</th><th>Dates</th><th>Days</th><th>Status</th></tr></thead>
                <tbody>{data.recent_leaves.map((l) => (
                  <tr key={l.id}><td><Link to={`/leave/${l.id}`}>{l.leave_type}</Link></td><td>{fdate(l.start_date)} – {fdate(l.end_date)}</td><td>{l.days}</td><td><Badge status={l.status} /></td></tr>
                ))}</tbody>
              </table></div>
            ) : <Empty icon="calendar2-x" title="No leave requests yet" />}
          </div>
          <div className="gw-card">
            <div className="gw-card-head"><h2>Recent claims</h2><Link className="small" to="/claims">View all</Link></div>
            {data.recent_claims.length ? (
              <div className="table-responsive"><table className="table gw-table">
                <thead><tr><th>Claim</th><th>Date</th><th className="text-end">Amount</th><th>Status</th></tr></thead>
                <tbody>{data.recent_claims.map((c) => (
                  <tr key={c.id}><td><Link to={`/claims/${c.id}`}>{c.category} · {c.subcategory}</Link></td><td>{fdate(c.claim_date)}</td><td className="text-end">{c.amount}</td><td><Badge status={c.status} /></td></tr>
                ))}</tbody>
              </table></div>
            ) : <Empty icon="receipt" title="No claims yet" />}
          </div>
        </div>

        <div className="col-lg-4">
          <div className="gw-card mb-3" id="announcements">
            <div className="gw-card-head"><h2>Announcements</h2></div>
            <AnnouncementList />
          </div>
          <div className="gw-card mb-3">
            <div className="gw-card-head"><h2>Out of office today</h2><Link className="small" to="/calendar">Calendar</Link></div>
            {data.out_today.length ? data.out_today.map((p) => (
              <div className="gw-list-item" key={p.id}><Avatar p={p} size="sm" /><div><Link className="fw-semibold text-dark" to={`/directory/${p.id}`}>{p.full_name}</Link><div className="small text-muted">{p.leave_type} · back after {fdate(p.end_date)}</div></div></div>
            )) : <div className="gw-card-body text-muted small">Everyone's in today.</div>}
          </div>
          <div className="gw-card gw-card-body">
            <div className="small text-muted mb-1">Your next approved leave</div>
            {next ? <Link className="fw-semibold" to={`/leave/${next.id}`}>{next.leave_type} leave · {fdate(next.start_date)}</Link>
              : <><div className="fw-semibold">Nothing booked yet</div><Link className="small" to="/leave/apply">Plan some time off →</Link></>}
          </div>
        </div>
      </div>
    </>
  );
}

export function Announcement() {
  const { id } = useParams();
  const [{ data: a, error }] = useApi(`/api/announcements/${id}`);
  const [{ data: others }] = useApi('/api/announcements?limit=6');
  const refs = useMemo(() => ({}), [others]);
  useTitle(a?.title);
  if (error) return <ErrorState error={error} />;
  if (!a) return <Skeleton rows={6} />;
  return (
    <>
      <div className="gw-breadcrumb"><Link to="/dashboard">Dashboard</Link> / Announcements</div>
      <div className="row g-3">
        <div className="col-lg-8">
          <article className="gw-card gw-card-body">
            {a.pinned ? <span className="gw-chip mb-2"><i className="bi bi-pin-angle" /> Pinned</span> : null}
            <h1 className="h3 fw-bold">{a.title}</h1>
            <div className="text-muted small mb-4">{a.author_name} · {a.author_title} · {fdate(a.created_at)}</div>
            <p className="lead fs-6">{a.summary}</p>
            <p>{a.body}</p>
          </article>
        </div>
        <div className="col-lg-4">
          <div className="gw-card">
            <div className="gw-card-head"><h2>More announcements</h2></div>
            {others ? others.items.filter((o) => o.id !== a.id).map((o) => (
              <div className="gw-list-item" key={o.id}><Link to={`/announcements/${o.id}?ref=${refs[o.id] ||= ref()}`}>{o.title}</Link></div>
            )) : <Skeleton rows={3} />}
          </div>
        </div>
      </div>
    </>
  );
}
