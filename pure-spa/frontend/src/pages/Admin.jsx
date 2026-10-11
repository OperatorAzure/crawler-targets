import { useEffect, useState } from 'react';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { api } from '../api.js';
import { useAuth } from '../auth.jsx';
import {
  Avatar, Badge, ConfirmModal, Empty, ErrorState, fdate, FieldError, invalid, Modal, PageHead, Pagination, Skeleton,
  useApi, useTitle, useToast,
} from '../ui.jsx';

const ROLES = { employee: 'Employee', manager: 'Manager', hr_admin: 'HR Admin' };
const DEPARTMENTS = ['Engineering', 'Finance', 'Human Resources', 'Marketing', 'Sales', 'Operations'];

function RejectModal({ item, onDone, onClose }) {
  const [comment, setComment] = useState('');
  const [errors, setErrors] = useState({});
  async function submit(e) {
    e.preventDefault();
    try {
      await api(`/api/admin/approvals/${item.kind}/${item.id}`, { method: 'POST', body: { action: 'reject', comment } });
      onDone('rejected');
    } catch (err) {
      setErrors(Object.keys(err.errors || {}).length ? err.errors : { comment: err.message });
    }
  }
  return (
    <Modal title={`Reject ${item.kind} #${item.id}`} onClose={onClose} footer={<>
      <button className="btn btn-light" onClick={onClose}>Cancel</button>
      <button className="btn btn-danger" form="reject-form">Reject</button>
    </>}>
      <form id="reject-form" onSubmit={submit}>
        <label className="form-label" htmlFor="comment">Reason for rejecting</label>
        <textarea className={`form-control${invalid(errors, 'comment')}`} id="comment" rows={3} maxLength={300} placeholder="Visible to the employee" value={comment} onChange={(e) => setComment(e.target.value)} />
        <FieldError errors={errors} name="comment" />
      </form>
    </Modal>
  );
}

export function Approvals() {
  useTitle('Approvals');
  const { user } = useAuth();
  const toast = useToast();
  const [{ data, error }, reload] = useApi('/api/admin/approvals');
  const [rejecting, setRejecting] = useState(null);

  async function approve(kind, id) {
    try {
      await api(`/api/admin/approvals/${kind}/${id}`, { method: 'POST', body: { action: 'approve' } });
      toast(`${kind === 'leave' ? 'Leave' : 'Claim'} #${id} approved.`);
      reload();
    } catch (err) { toast(err.message, 'error'); }
  }
  const actions = (kind, id) => (
    <div className="d-flex gap-2">
      <button className="btn btn-sm btn-success" onClick={() => approve(kind, id)}><i className="bi bi-check-lg" /> Approve</button>
      <button className="btn btn-sm btn-outline-danger" onClick={() => setRejecting({ kind, id })}><i className="bi bi-x-lg" /> Reject</button>
    </div>
  );

  if (error) return <ErrorState error={error} />;
  return (
    <>
      <PageHead title="Approvals" subtitle={user.role === 'hr_admin' ? 'All pending requests across GoWork.' : 'Pending requests from your direct reports.'} />
      <div className="gw-card mb-4">
        <div className="gw-card-head"><h2>Leave requests <span className="badge text-bg-warning">{data ? data.leaves.length : '…'}</span></h2></div>
        {!data ? <Skeleton rows={3} /> : data.leaves.length ? (
          <div className="table-responsive"><table className="table gw-table">
            <thead><tr><th>Employee</th><th>Type</th><th>Dates</th><th>Days</th><th>Reason</th><th /></tr></thead>
            <tbody>{data.leaves.map((l) => (
              <tr key={l.id}>
                <td><Link className="fw-semibold" to={`/directory/${l.user_id}`}>{l.owner_name}</Link></td><td><Link to={`/leave/${l.id}`}>{l.leave_type}</Link></td>
                <td className="text-nowrap">{fdate(l.start_date)} – {fdate(l.end_date)}</td><td>{l.days}</td>
                <td className="text-truncate" style={{ maxWidth: 200 }}>{l.reason}</td><td>{actions('leave', l.id)}</td>
              </tr>
            ))}</tbody>
          </table></div>
        ) : <Empty icon="check2-all" title="All caught up" text="No leave requests waiting for you." />}
      </div>
      <div className="gw-card">
        <div className="gw-card-head"><h2>Expense claims <span className="badge text-bg-warning">{data ? data.claims.length : '…'}</span></h2></div>
        {!data ? <Skeleton rows={3} /> : data.claims.length ? (
          <div className="table-responsive"><table className="table gw-table">
            <thead><tr><th>Employee</th><th>Claim</th><th>Date</th><th className="text-end">Amount</th><th /></tr></thead>
            <tbody>{data.claims.map((c) => (
              <tr key={c.id}>
                <td><Link className="fw-semibold" to={`/directory/${c.user_id}`}>{c.owner_name}</Link></td>
                <td><Link to={`/claims/${c.id}`}>{c.category}</Link><div className="small text-muted text-truncate" style={{ maxWidth: 220 }}>{c.description}</div></td>
                <td className="text-nowrap">{fdate(c.claim_date)}</td><td className="text-end fw-semibold">{c.amount}</td><td>{actions('claim', c.id)}</td>
              </tr>
            ))}</tbody>
          </table></div>
        ) : <Empty icon="check2-all" title="All caught up" text="No claims waiting for you." />}
      </div>
      {rejecting && <RejectModal item={rejecting} onClose={() => setRejecting(null)} onDone={() => {
        toast(`${rejecting.kind === 'leave' ? 'Leave' : 'Claim'} #${rejecting.id} rejected.`);
        setRejecting(null);
        reload();
      }} />}
    </>
  );
}

export function Users() {
  useTitle('Users');
  const [params, setParams] = useSearchParams();
  const [q, setQ] = useState(params.get('q') || '');
  const query = new URLSearchParams({ status: 'active', ...Object.fromEntries(params) });
  const [{ data, error }] = useApi(`/api/admin/users?${query}`);

  useEffect(() => {
    const t = setTimeout(() => {
      if (q === (params.get('q') || '')) return;
      const next = new URLSearchParams(params);
      if (q) next.set('q', q); else next.delete('q');
      next.delete('page');
      setParams(next, { replace: true });
    }, 300);
    return () => clearTimeout(t);
  }, [q]); // eslint-disable-line react-hooks/exhaustive-deps

  const setFilter = (key) => (e) => {
    const next = new URLSearchParams(params);
    next.set(key, e.target.value);
    next.delete('page');
    setParams(next);
  };

  return (
    <>
      <PageHead title="User management" subtitle={data ? `${data.total} account(s).` : 'Loading accounts…'}>
        <Link className="btn btn-primary" to="/admin/users/new"><i className="bi bi-person-plus" /> Add user</Link>
      </PageHead>
      <div className="gw-card">
        <div className="gw-filters">
          <input className="form-control form-control-sm" type="search" placeholder="Name, username or email" value={q} onChange={(e) => setQ(e.target.value)} />
          <select className="form-select form-select-sm" aria-label="Role" value={params.get('role') || ''} onChange={setFilter('role')}>
            <option value="">All roles</option>{Object.entries(ROLES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
          <select className="form-select form-select-sm" aria-label="Status" value={params.get('status') || 'active'} onChange={setFilter('status')}>
            <option value="active">Active</option><option value="inactive">Inactive</option><option value="all">All</option>
          </select>
        </div>
        {error ? <ErrorState error={error} /> : !data ? <Skeleton rows={6} /> : (
          <>
            {data.items.length ? (
              <div className="table-responsive"><table className="table gw-table">
                <thead><tr><th>Name</th><th>Username</th><th>Department</th><th>Role</th><th>Status</th><th /></tr></thead>
                <tbody>{data.items.map((u) => (
                  <tr key={u.id}>
                    <td><div className="d-flex gap-2 align-items-center"><Avatar p={u} size="sm" /><div><div className="fw-semibold">{u.full_name}</div><div className="small text-muted">{u.email}</div></div></div></td>
                    <td className="text-muted">@{u.username}</td><td>{u.department}</td><td>{u.role_label}</td>
                    <td><Badge status={u.active ? 'Active' : 'Inactive'} /></td>
                    <td className="text-end"><Link className="btn btn-sm btn-light" to={`/admin/users/${u.id}`}>Edit</Link></td>
                  </tr>
                ))}</tbody>
              </table></div>
            ) : <Empty icon="person-x" title="No users on this page" />}
            <Pagination result={data} />
          </>
        )}
      </div>
    </>
  );
}

const BLANK = { username: '', temp_password: '', full_name: '', email: '', department: '', job_title: '', role: 'employee', manager_id: '' };

export function UserForm() {
  const { id } = useParams();
  const { user } = useAuth();
  const navigate = useNavigate();
  const toast = useToast();
  const [{ data: target, error }, reload] = useApi(id ? `/api/admin/users/${id}` : null);
  const [{ data: managers }] = useApi('/api/admin/managers');
  const [form, setForm] = useState(BLANK);
  const [errors, setErrors] = useState({});
  const [busy, setBusy] = useState(false);
  const [confirm, setConfirm] = useState(false);
  useTitle(target ? target.full_name : 'Add user');

  useEffect(() => {
    if (target) setForm({ ...BLANK, ...target, manager_id: target.manager_id ? String(target.manager_id) : '' });
    else if (!id) setForm(BLANK);
  }, [target, id]);

  if (error) return <ErrorState error={error} />;
  if (id && !target) return <Skeleton rows={6} />;

  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });
  const field = (name, label, props = {}) => (
    <div className="col-sm-6">
      <label className="form-label" htmlFor={name}>{label}</label>
      <input className={`form-control${invalid(errors, name)}`} id={name} name={name} value={form[name] ?? ''} onChange={set(name)} {...props} />
      <FieldError errors={errors} name={name} />
    </div>
  );

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    try {
      if (id) {
        await api(`/api/admin/users/${id}`, { method: 'PUT', body: form });
        toast('User updated.');
        reload();
        setErrors({});
      } else {
        const res = await api('/api/admin/users', { method: 'POST', body: form });
        toast('User created. Share the temporary password with them securely.');
        navigate(`/admin/users/${res.id}`);
      }
    } catch (err) {
      setErrors(Object.keys(err.errors || {}).length ? err.errors : { _: err.message });
    }
    setBusy(false);
  }

  async function toggleStatus() {
    try {
      await api(`/api/admin/users/${id}/status`, { method: 'POST', body: { active: !target.active } });
      toast(target.active ? 'User deactivated and signed out everywhere.' : 'User reactivated.');
      setConfirm(false);
      reload();
    } catch (err) { toast(err.message, 'error'); }
  }

  return (
    <>
      <PageHead crumbs={[['Users', '/admin/users'], [target ? target.full_name : 'New']]}
        title={target ? <>{target.full_name} <Badge status={target.active ? 'Active' : 'Inactive'} /></> : 'Add user'}
        subtitle={target ? `@${target.username}` : 'Create a GoWork account for a new joiner.'}>
        {target && target.id !== user.id && (
          <button className={`btn ${target.active ? 'btn-outline-danger' : 'btn-outline-success'}`} onClick={() => (target.active ? setConfirm(true) : toggleStatus())}>
            <i className={`bi bi-person-${target.active ? 'slash' : 'check'}`} /> {target.active ? 'Deactivate' : 'Reactivate'}
          </button>
        )}
      </PageHead>
      <form className="gw-card" onSubmit={submit} noValidate style={{ maxWidth: 860 }}>
        <div className="gw-card-body"><div className="row g-3">
          {errors._ && <div className="col-12 alert alert-danger">{errors._}</div>}
          {!id && field('username', 'Username', { autoComplete: 'off' })}
          {!id && field('temp_password', 'Temporary password', { type: 'password', autoComplete: 'new-password' })}
          {field('full_name', 'Full name', { maxLength: 60 })}
          {field('email', 'Email', { type: 'email' })}
          <div className="col-sm-6">
            <label className="form-label" htmlFor="department">Department</label>
            <select className={`form-select${invalid(errors, 'department')}`} id="department" value={form.department} onChange={set('department')}>
              <option value="">Choose…</option>{DEPARTMENTS.map((d) => <option key={d}>{d}</option>)}
            </select>
            <FieldError errors={errors} name="department" />
          </div>
          {field('job_title', 'Job title', { maxLength: 60 })}
          <div className="col-sm-6">
            <label className="form-label" htmlFor="role">Role</label>
            <select className={`form-select${invalid(errors, 'role')}`} id="role" value={form.role} onChange={set('role')}>
              {Object.entries(ROLES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
            <FieldError errors={errors} name="role" />
          </div>
          <div className="col-sm-6">
            <label className="form-label" htmlFor="manager_id">Reports to</label>
            <select className={`form-select${invalid(errors, 'manager_id')}`} id="manager_id" value={form.manager_id} onChange={set('manager_id')}>
              <option value="">No manager</option>
              {managers?.items.map((m) => <option key={m.id} value={m.id}>{m.full_name} · {m.department}</option>)}
            </select>
            <FieldError errors={errors} name="manager_id" />
          </div>
        </div></div>
        <div className="gw-modal-foot">
          <Link className="btn btn-link text-muted" to="/admin/users">Cancel</Link>
          <button className="btn btn-primary" type="submit" disabled={busy}>{id ? 'Save changes' : 'Create user'}</button>
        </div>
      </form>
      {confirm && <ConfirmModal title="Deactivate this user?" text="They will be signed out everywhere and can no longer sign in." confirmLabel="Deactivate" onConfirm={toggleStatus} onClose={() => setConfirm(false)} />}
    </>
  );
}
