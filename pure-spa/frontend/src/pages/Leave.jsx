import { useState } from 'react';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { api } from '../api.js';
import {
  Badge, ConfirmModal, Empty, ErrorState, fdate, FieldError, invalid, Modal, PageHead, Pagination, Skeleton, SortTh,
  today, useApi, useTitle, useToast,
} from '../ui.jsx';

const STATUSES = ['Pending', 'Approved', 'Rejected', 'Cancelled'];
const TYPES = ['Annual', 'Medical', 'Compassionate', 'Unpaid'];

function Balances() {
  const [{ data }] = useApi('/api/leave/balances');
  if (!data) return <Skeleton rows={2} />;
  return (
    <div className="row g-3 mb-4">
      {data.items.map((b) => (
        <div className="col-md-4" key={b.type}><div className="gw-card gw-card-body">
          <div className="d-flex justify-content-between mb-2"><span className="fw-semibold">{b.type}</span><span className="text-muted small">{b.used} used</span></div>
          <div className="gw-progress mb-2"><span style={{ width: `${Math.round((b.used / b.entitlement) * 100)}%` }} /></div>
          <div className="small text-muted"><strong className="text-dark">{b.remaining}</strong> of {b.entitlement} days left</div>
        </div></div>
      ))}
    </div>
  );
}

function LeavePreview({ id, onClose }) {
  const [{ data: l, error }] = useApi(`/api/leave/${id}`);
  return (
    <Modal title={`Leave request #${id}`} onClose={onClose}>
      {error ? <ErrorState error={error} /> : !l ? <Skeleton rows={4} /> : (
        <>
          <div className="mb-3"><Badge status={l.status} /></div>
          <dl className="gw-dl" style={{ gridTemplateColumns: '120px 1fr' }}>
            <dt>Type</dt><dd>{l.leave_type}</dd>
            <dt>Dates</dt><dd>{fdate(l.start_date)} – {fdate(l.end_date)}</dd>
            <dt>Days</dt><dd>{l.days}</dd>
            <dt>Reason</dt><dd>{l.reason}</dd>
            {l.approver_name && <><dt>Decided by</dt><dd>{l.approver_name}</dd></>}
          </dl>
          <Link className="btn btn-sm btn-outline-primary mt-3" to={`/leave/${l.id}`}>Open full request <i className="bi bi-arrow-right" /></Link>
        </>
      )}
    </Modal>
  );
}

export function LeaveList() {
  useTitle('Leave');
  const [params, setParams] = useSearchParams();
  const [preview, setPreview] = useState(null);
  const query = new URLSearchParams({ sort: 'start_date', order: 'desc', ...Object.fromEntries(params) });
  const [{ data, error }] = useApi(`/api/leave?${query}`);
  const setFilter = (key) => (e) => {
    const next = new URLSearchParams(params);
    if (e.target.value) next.set(key, e.target.value); else next.delete(key);
    next.delete('page');
    setParams(next);
  };

  return (
    <>
      <PageHead title="Leave" subtitle={`Your leave balances and requests for ${today().slice(0, 4)}.`}>
        <Link className="btn btn-primary" to="/leave/apply"><i className="bi bi-calendar-plus" /> Apply for leave</Link>
      </PageHead>
      <Balances />
      <div className="gw-card">
        <div className="gw-filters">
          <select className="form-select form-select-sm" aria-label="Status" value={params.get('status') || ''} onChange={setFilter('status')}>
            <option value="">All statuses</option>{STATUSES.map((s) => <option key={s}>{s}</option>)}
          </select>
          <select className="form-select form-select-sm" aria-label="Leave type" value={params.get('type') || ''} onChange={setFilter('type')}>
            <option value="">All types</option>{TYPES.map((t) => <option key={t}>{t}</option>)}
          </select>
          <span className="small text-muted ms-auto">Tip: click a row for a quick preview</span>
        </div>
        {error ? <ErrorState error={error} /> : !data ? <Skeleton rows={6} /> : (
          <>
            {data.items.length ? (
              <div className="table-responsive"><table className="table gw-table">
                <thead><tr><th>#</th><th>Type</th><SortTh label="Dates" field="start_date" /><SortTh label="Days" field="days" /><th>Reason</th><SortTh label="Status" field="status" /><SortTh label="Submitted" field="created_at" /></tr></thead>
                <tbody>{data.items.map((l) => (
                  <tr key={l.id} style={{ cursor: 'pointer' }} onClick={() => setPreview(l.id)}>
                    <td className="text-muted">{l.id}</td><td className="fw-semibold text-brand">{l.leave_type}</td>
                    <td>{fdate(l.start_date)} – {fdate(l.end_date)}</td><td>{l.days}</td>
                    <td className="text-truncate" style={{ maxWidth: 240 }}>{l.reason}</td><td><Badge status={l.status} /></td>
                    <td className="text-muted small">{fdate(l.created_at)}</td>
                  </tr>
                ))}</tbody>
              </table></div>
            ) : <Empty icon="calendar2-x" title="No leave requests on this page" text="Try another page or clear your filters." />}
            <Pagination result={data} />
          </>
        )}
      </div>
      {preview && <LeavePreview id={preview} onClose={() => setPreview(null)} />}
    </>
  );
}

export function LeaveDetail() {
  const { id } = useParams();
  const [{ data: l, error }, reload] = useApi(`/api/leave/${id}`);
  const [confirm, setConfirm] = useState(false);
  const toast = useToast();
  useTitle(`Leave #${id}`);
  if (error) return <ErrorState error={error} />;
  if (!l) return <Skeleton rows={6} />;

  async function cancel() {
    try {
      await api(`/api/leave/${id}/cancel`, { method: 'POST' });
      toast('Leave request cancelled.');
      setConfirm(false);
      reload();
    } catch (err) { toast(err.message, 'error'); }
  }

  return (
    <>
      <PageHead crumbs={[['Leave', '/leave'], [`Request #${l.id}`]]} title={<>{l.leave_type} leave <Badge status={l.status} /></>}
        subtitle={`${fdate(l.start_date)} – ${fdate(l.end_date)} · ${l.days} working day(s)`}>
        {l.can_cancel && <button className="btn btn-outline-danger" onClick={() => setConfirm(true)}><i className="bi bi-x-circle" /> Cancel request</button>}
      </PageHead>
      <div className="row g-3">
        <div className="col-lg-8"><div className="gw-card">
          <div className="gw-card-head"><h2>Request details</h2></div>
          <div className="gw-card-body"><dl className="gw-dl">
            <dt>Employee</dt><dd><Link to={`/directory/${l.user_id}`}>{l.owner_name}</Link></dd>
            <dt>Leave type</dt><dd>{l.leave_type}</dd>
            <dt>From</dt><dd>{fdate(l.start_date)}</dd>
            <dt>To</dt><dd>{fdate(l.end_date)}</dd>
            <dt>Working days</dt><dd>{l.days}</dd>
            <dt>Reason</dt><dd>{l.reason}</dd>
            <dt>Submitted</dt><dd>{fdate(l.created_at)}</dd>
          </dl></div>
        </div></div>
        <div className="col-lg-4"><div className="gw-card">
          <div className="gw-card-head"><h2>Approval</h2></div>
          <div className="gw-card-body">
            {l.status === 'Pending' ? <p className="mb-0 text-muted"><i className="bi bi-hourglass-split" /> Waiting for your manager to review.</p>
              : l.approver_name ? (
                <dl className="gw-dl" style={{ gridTemplateColumns: '90px 1fr' }}>
                  <dt>By</dt><dd>{l.approver_name}</dd><dt>On</dt><dd>{fdate(l.decided_at)}</dd>
                  {l.decision_comment && <><dt>Comment</dt><dd>{l.decision_comment}</dd></>}
                </dl>
              ) : <p className="mb-0 text-muted">This request was {l.status.toLowerCase()}.</p>}
          </div>
        </div></div>
      </div>
      {confirm && <ConfirmModal title="Cancel this request?" text="Your manager will be notified and the days returned to your balance." confirmLabel="Cancel request" onConfirm={cancel} onClose={() => setConfirm(false)} />}
    </>
  );
}

export function LeaveApply() {
  useTitle('Apply for leave');
  const navigate = useNavigate();
  const toast = useToast();
  const [{ data: balances }] = useApi('/api/leave/balances');
  const [step, setStep] = useState(1);
  const [form, setForm] = useState({ leave_type: '', start_date: '', end_date: '', reason: '' });
  const [summary, setSummary] = useState(null);
  const [errors, setErrors] = useState({});
  const [busy, setBusy] = useState(false);
  const set = (key) => (e) => setForm({ ...form, [key]: e.target.value });
  const balanceFor = (t) => balances?.items.find((b) => b.type === t);

  function clientErrors() {
    const e = {};
    if (step === 1 && !form.leave_type) e.leave_type = 'Choose a leave type.';
    if (step === 2) {
      if (!form.start_date) e.start_date = 'Pick your first day.';
      if (!form.end_date) e.end_date = 'Pick your last day.';
      else if (form.start_date && form.end_date < form.start_date) e.end_date = 'End date must be on or after the start date.';
    }
    if (step === 3 && form.reason.trim().length < 5) e.reason = 'Reason must be at least 5 characters.';
    return e;
  }

  async function submit(e) {
    e.preventDefault();
    const found = clientErrors();
    setErrors(found);
    if (Object.keys(found).length) return;
    setBusy(true);
    try {
      if (step < 3) {
        const result = await api('/api/leave/validate', { method: 'POST', body: { ...form, step } });
        if (step === 2) setSummary(result);
        setStep(step + 1);
      } else {
        const { id } = await api('/api/leave', { method: 'POST', body: form });
        toast('Leave request submitted for approval.');
        navigate(`/leave/${id}`);
        return;
      }
    } catch (err) {
      const errs = Object.keys(err.errors || {}).length ? err.errors : { _: err.message };
      if (errs.leave_type) setStep(1);
      else if (step === 3 && (errs.start_date || errs.end_date)) setStep(2);
      setErrors(errs);
    }
    setBusy(false);
  }

  const labels = ['Leave type', 'Dates', 'Review & submit'];
  return (
    <>
      <PageHead crumbs={[['Leave', '/leave'], ['Apply']]} title="Apply for leave" subtitle={`Step ${step} of 3`} />
      <ol className="gw-steps">
        {labels.map((label, i) => (
          <li key={label} className={i + 1 === step ? 'current' : i + 1 < step ? 'done' : ''}><span>{i + 1 < step ? '✓' : i + 1}</span> {label}</li>
        ))}
      </ol>
      <form className="gw-card" onSubmit={submit} noValidate style={{ maxWidth: 760 }}>
        <div className="gw-card-body">
          {errors._ && <div className="alert alert-danger">{errors._}</div>}
          {step === 1 && (
            <>
              <h2 className="h6 fw-semibold mb-3">What kind of leave do you need?</h2>
              <div className="row g-3">
                {TYPES.map((t) => {
                  const b = balanceFor(t);
                  return (
                    <div className="col-sm-6" key={t}>
                      <label className="gw-choice">
                        <input className="form-check-input" type="radio" name="leave_type" value={t} checked={form.leave_type === t} onChange={set('leave_type')} />
                        <span className="fw-semibold">{t}</span>
                        <div className="small text-muted mt-1">{b ? `${b.remaining} of ${b.entitlement} days left this year` : 'No yearly limit · unpaid'}</div>
                      </label>
                    </div>
                  );
                })}
              </div>
              <FieldError errors={errors} name="leave_type" />
            </>
          )}
          {step === 2 && (
            <>
              <h2 className="h6 fw-semibold mb-3">When will you be away? <span className="gw-chip">{form.leave_type}</span></h2>
              <div className="row g-3">
                <div className="col-sm-6">
                  <label className="form-label" htmlFor="start_date">First day</label>
                  <input className={`form-control${invalid(errors, 'start_date')}`} type="date" id="start_date" name="start_date" min={today()} value={form.start_date} onChange={set('start_date')} />
                  <FieldError errors={errors} name="start_date" />
                </div>
                <div className="col-sm-6">
                  <label className="form-label" htmlFor="end_date">Last day</label>
                  <input className={`form-control${invalid(errors, 'end_date')}`} type="date" id="end_date" name="end_date" min={form.start_date || today()} value={form.end_date} onChange={set('end_date')} />
                  <FieldError errors={errors} name="end_date" />
                </div>
              </div>
              <p className="small text-muted mt-3 mb-0"><i className="bi bi-info-circle" /> Weekends aren't counted. A single request can cover up to 30 working days.</p>
            </>
          )}
          {step === 3 && summary && (
            <>
              <h2 className="h6 fw-semibold mb-3">Review your request</h2>
              <dl className="gw-dl mb-4">
                <dt>Leave type</dt><dd>{summary.leave_type} <button type="button" className="btn btn-link btn-sm p-0 ms-2" onClick={() => setStep(1)}>Change</button></dd>
                <dt>Dates</dt><dd>{fdate(summary.start_date)} – {fdate(summary.end_date)} <button type="button" className="btn btn-link btn-sm p-0 ms-2" onClick={() => setStep(2)}>Change</button></dd>
                <dt>Working days</dt><dd>{summary.days}</dd>
              </dl>
              <label className="form-label" htmlFor="reason">Reason</label>
              <textarea className={`form-control${invalid(errors, 'reason')}`} id="reason" name="reason" rows={4} maxLength={500} placeholder="e.g. Family holiday to Penang" value={form.reason} onChange={set('reason')} />
              <div className="form-text">{form.reason.length}/500</div>
              <FieldError errors={errors} name="reason" />
            </>
          )}
        </div>
        <div className="gw-modal-foot">
          {step > 1 && <button type="button" className="btn btn-light me-auto" onClick={() => { setErrors({}); setStep(step - 1); }}><i className="bi bi-arrow-left" /> Back</button>}
          <Link className="btn btn-link text-muted" to="/leave">Cancel</Link>
          <button className="btn btn-primary" type="submit" disabled={busy}>
            {busy ? <span className="spinner-border spinner-border-sm" /> : step === 3 ? <>Submit request <i className="bi bi-send" /></> : <>Continue <i className="bi bi-arrow-right" /></>}
          </button>
        </div>
      </form>
    </>
  );
}
