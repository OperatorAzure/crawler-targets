import { useEffect, useState } from 'react';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { api, saveBlob } from '../api.js';
import {
  Badge, ConfirmModal, Empty, ErrorState, fdate, FieldError, invalid, PageHead, Pagination, Skeleton, SortTh, today,
  useApi, useTitle, useToast,
} from '../ui.jsx';

const STATUSES = ['Pending', 'Approved', 'Rejected'];

function ReceiptButton({ claim, children }) {
  const toast = useToast();
  // Receipts need the bearer token, so they are fetched as a blob - no plain link exists
  async function open() {
    try { saveBlob(await api(`/api/claims/${claim.id}/receipt`, { blob: true }), claim.receipt_name); }
    catch (err) { toast(err.message, 'error'); }
  }
  return <button type="button" className="btn btn-link btn-sm p-0" onClick={open} title={claim.receipt_name}>{children}</button>;
}

export function ClaimsList() {
  useTitle('Claims');
  const [params, setParams] = useSearchParams();
  const [{ data: cats }] = useApi('/api/claims/categories');
  const query = new URLSearchParams({ sort: 'claim_date', order: 'desc', ...Object.fromEntries(params) });
  const [{ data, error }] = useApi(`/api/claims?${query}`);
  const setFilter = (key) => (e) => {
    const next = new URLSearchParams(params);
    if (e.target.value) next.set(key, e.target.value); else next.delete(key);
    next.delete('page');
    setParams(next);
  };

  return (
    <>
      <PageHead title="Claims" subtitle={data ? `${data.total_amount} reimbursed to you this year.` : 'Loading your claims…'}>
        <Link className="btn btn-primary" to="/claims/new"><i className="bi bi-plus-lg" /> New claim</Link>
      </PageHead>
      <div className="gw-card">
        <div className="gw-filters">
          <select className="form-select form-select-sm" aria-label="Status" value={params.get('status') || ''} onChange={setFilter('status')}>
            <option value="">All statuses</option>{STATUSES.map((s) => <option key={s}>{s}</option>)}
          </select>
          <select className="form-select form-select-sm" aria-label="Category" value={params.get('category') || ''} onChange={setFilter('category')}>
            <option value="">All categories</option>{cats?.items.map((c) => <option key={c}>{c}</option>)}
          </select>
        </div>
        {error ? <ErrorState error={error} /> : !data ? <Skeleton rows={6} /> : (
          <>
            {data.items.length ? (
              <div className="table-responsive"><table className="table gw-table">
                <thead><tr><th>#</th><th>Category</th><th>Description</th><SortTh label="Expense date" field="claim_date" /><SortTh label="Amount" field="amount" className="text-end" /><th>Receipt</th><SortTh label="Status" field="status" /></tr></thead>
                <tbody>{data.items.map((c) => (
                  <tr key={c.id}>
                    <td className="text-muted">{c.id}</td>
                    <td><Link className="fw-semibold" to={`/claims/${c.id}`}>{c.category}</Link><div className="small text-muted">{c.subcategory}</div></td>
                    <td className="text-truncate" style={{ maxWidth: 220 }}>{c.description}</td>
                    <td>{fdate(c.claim_date)}</td><td className="text-end fw-semibold">{c.amount}</td>
                    <td>{c.receipt_name ? <ReceiptButton claim={c}><i className="bi bi-paperclip" /></ReceiptButton> : <span className="text-muted">—</span>}</td>
                    <td><Badge status={c.status} /></td>
                  </tr>
                ))}</tbody>
              </table></div>
            ) : <Empty icon="receipt" title="No claims on this page" text="Try another page or clear your filters." />}
            <Pagination result={data} />
          </>
        )}
      </div>
    </>
  );
}

export function ClaimNew() {
  useTitle('New claim');
  const navigate = useNavigate();
  const toast = useToast();
  const [{ data: cats }] = useApi('/api/claims/categories');
  const [form, setForm] = useState({ category: '', subcategory: '', amount: '', claim_date: '', description: '' });
  const [file, setFile] = useState(null);
  const [subs, setSubs] = useState(null);
  const [errors, setErrors] = useState({});
  const [busy, setBusy] = useState(false);
  const set = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }));

  // Dependent dropdown: sub-categories come from the API when the category changes
  useEffect(() => {
    setSubs(null);
    setForm((f) => ({ ...f, subcategory: '' }));
    if (!form.category) return undefined;
    let alive = true;
    api(`/api/claims/categories/${encodeURIComponent(form.category)}`).then((d) => alive && setSubs(d.items));
    return () => { alive = false; };
  }, [form.category]);

  function clientErrors() {
    const e = {};
    const value = parseFloat(form.amount);
    if (!form.category) e.category = 'Choose a category.';
    else if (!form.subcategory) e.subcategory = 'Choose a sub-category.';
    if (!/^\d+(\.\d{1,2})?$/.test(form.amount.trim()) || value <= 0 || value > 5000) e.amount = 'Enter an amount between 0.01 and 5,000.';
    if (!form.claim_date) e.claim_date = 'Pick the expense date.';
    if (form.description.trim().length < 5) e.description = 'Description must be at least 5 characters.';
    if (file && !/\.(pdf|png|jpe?g)$/i.test(file.name)) e.receipt = 'Receipt must be a PDF, PNG or JPG file.';
    else if (file && file.size > 5 * 1024 * 1024) e.receipt = 'Receipt must be 5 MB or smaller.';
    else if (!file && value > 25) e.receipt = 'A receipt is required for claims above $25.00.';
    return e;
  }

  async function submit(e) {
    e.preventDefault();
    const found = clientErrors();
    setErrors(found);
    if (Object.keys(found).length) return;
    setBusy(true);
    const body = new FormData();
    Object.entries(form).forEach(([k, v]) => body.append(k, v));
    if (file) body.append('receipt', file);
    try {
      const { id } = await api('/api/claims', { method: 'POST', form: body });
      toast('Claim submitted for approval.');
      navigate(`/claims/${id}`);
    } catch (err) {
      setErrors(Object.keys(err.errors || {}).length ? err.errors : { _: err.message });
      setBusy(false);
    }
  }

  return (
    <>
      <PageHead crumbs={[['Claims', '/claims'], ['New']]} title="New expense claim" subtitle="Receipts are required for claims above $25." />
      <form className="gw-card" onSubmit={submit} noValidate style={{ maxWidth: 760 }}>
        <div className="gw-card-body">
          {errors._ && <div className="alert alert-danger">{errors._}</div>}
          <div className="row g-3">
            <div className="col-sm-6">
              <label className="form-label" htmlFor="category">Category</label>
              <select className={`form-select${invalid(errors, 'category')}`} id="category" name="category" value={form.category} onChange={set('category')}>
                <option value="">Choose…</option>{cats?.items.map((c) => <option key={c}>{c}</option>)}
              </select>
              <FieldError errors={errors} name="category" />
            </div>
            <div className="col-sm-6">
              <label className="form-label" htmlFor="subcategory">Sub-category</label>
              <select className={`form-select${invalid(errors, 'subcategory')}`} id="subcategory" name="subcategory" value={form.subcategory} onChange={set('subcategory')} disabled={!subs}>
                {subs ? <><option value="">Choose…</option>{subs.map((s) => <option key={s}>{s}</option>)}</> : <option value="">{form.category ? 'Loading…' : 'Choose a category first'}</option>}
              </select>
              <FieldError errors={errors} name="subcategory" />
            </div>
            <div className="col-sm-6">
              <label className="form-label" htmlFor="amount">Amount (SGD)</label>
              <div className="input-group"><span className="input-group-text">$</span>
                <input className={`form-control${invalid(errors, 'amount')}`} id="amount" name="amount" inputMode="decimal" placeholder="0.00" value={form.amount} onChange={set('amount')} />
              </div>
              <FieldError errors={errors} name="amount" />
            </div>
            <div className="col-sm-6">
              <label className="form-label" htmlFor="claim_date">Expense date</label>
              <input className={`form-control${invalid(errors, 'claim_date')}`} id="claim_date" name="claim_date" type="date" max={today()} value={form.claim_date} onChange={set('claim_date')} />
              <FieldError errors={errors} name="claim_date" />
            </div>
            <div className="col-12">
              <label className="form-label" htmlFor="description">Description</label>
              <textarea className={`form-control${invalid(errors, 'description')}`} id="description" name="description" rows={3} maxLength={300} placeholder="e.g. Taxi to client office at Changi Business Park" value={form.description} onChange={set('description')} />
              <FieldError errors={errors} name="description" />
            </div>
            <div className="col-12">
              <label className="form-label" htmlFor="receipt">Receipt <span className="text-muted small">{parseFloat(form.amount) > 25 ? '(required above $25)' : '(optional up to $25)'}</span></label>
              <input className={`form-control${invalid(errors, 'receipt')}`} id="receipt" name="receipt" type="file" accept=".pdf,.png,.jpg,.jpeg" onChange={(e) => setFile(e.target.files[0] || null)} />
              <div className="form-text">PDF, PNG or JPG up to 5 MB.</div>
              <FieldError errors={errors} name="receipt" />
            </div>
          </div>
        </div>
        <div className="gw-modal-foot">
          <Link className="btn btn-link text-muted" to="/claims">Cancel</Link>
          <button className="btn btn-primary" type="submit" disabled={busy}>{busy ? <span className="spinner-border spinner-border-sm" /> : 'Submit claim'}</button>
        </div>
      </form>
    </>
  );
}

export function ClaimDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const toast = useToast();
  const [{ data: c, error }] = useApi(`/api/claims/${id}`);
  const [confirm, setConfirm] = useState(false);
  useTitle(`Claim #${id}`);
  if (error) return <ErrorState error={error} />;
  if (!c) return <Skeleton rows={6} />;

  async function remove() {
    try {
      await api(`/api/claims/${id}`, { method: 'DELETE' });
      toast('Claim deleted.');
      navigate('/claims');
    } catch (err) { toast(err.message, 'error'); }
  }

  return (
    <>
      <PageHead crumbs={[['Claims', '/claims'], [`Claim #${c.id}`]]} title={<>{c.amount} <Badge status={c.status} /></>} subtitle={`${c.category} · ${c.subcategory}`}>
        {c.can_delete && <button className="btn btn-outline-danger" onClick={() => setConfirm(true)}><i className="bi bi-trash" /> Delete claim</button>}
      </PageHead>
      <div className="row g-3">
        <div className="col-lg-8"><div className="gw-card">
          <div className="gw-card-head"><h2>Claim details</h2></div>
          <div className="gw-card-body"><dl className="gw-dl">
            <dt>Employee</dt><dd><Link to={`/directory/${c.user_id}`}>{c.owner_name}</Link></dd>
            <dt>Category</dt><dd>{c.category} / {c.subcategory}</dd>
            <dt>Expense date</dt><dd>{fdate(c.claim_date)}</dd>
            <dt>Amount</dt><dd>{c.amount}</dd>
            <dt>Description</dt><dd>{c.description}</dd>
            <dt>Receipt</dt><dd>{c.receipt_name ? <ReceiptButton claim={c}><i className="bi bi-paperclip" /> {c.receipt_name}</ReceiptButton> : 'None attached'}</dd>
            <dt>Submitted</dt><dd>{fdate(c.created_at)}</dd>
          </dl></div>
        </div></div>
        <div className="col-lg-4"><div className="gw-card">
          <div className="gw-card-head"><h2>Approval</h2></div>
          <div className="gw-card-body">
            {c.status === 'Pending' ? <p className="mb-0 text-muted"><i className="bi bi-hourglass-split" /> Waiting for your manager to review.</p> : (
              <dl className="gw-dl" style={{ gridTemplateColumns: '90px 1fr' }}>
                <dt>By</dt><dd>{c.approver_name || '—'}</dd><dt>On</dt><dd>{fdate(c.decided_at)}</dd>
                {c.decision_comment && <><dt>Comment</dt><dd>{c.decision_comment}</dd></>}
              </dl>
            )}
          </div>
        </div></div>
      </div>
      {confirm && <ConfirmModal title="Delete this claim?" text="This permanently removes the claim and its receipt." confirmLabel="Delete claim" onConfirm={remove} onClose={() => setConfirm(false)} />}
    </>
  );
}
