import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { api } from './api.js';

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
export function fdate(iso) {
  if (!iso) return '—';
  const [y, m, d] = iso.slice(0, 10).split('-');
  const out = `${d} ${MONTHS[+m - 1]} ${y}`;
  return iso.includes('T') ? `${out}, ${iso.slice(11, 16)}` : out;
}

export function today() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

export function useTitle(title) {
  useEffect(() => { document.title = title ? `${title} · GoWork` : 'GoWork'; }, [title]);
}

// Fetch helper: [{ data, error, loading }, reload]
export function useApi(path) {
  const [state, setState] = useState({ data: null, error: null, loading: true });
  const [tick, setTick] = useState(0);
  useEffect(() => {
    if (!path) return undefined;
    let alive = true;
    setState((s) => ({ ...s, loading: true }));
    api(path).then(
      (data) => alive && setState({ data, error: null, loading: false }),
      (error) => alive && setState({ data: null, error, loading: false }),
    );
    return () => { alive = false; };
  }, [path, tick]);
  return [state, useCallback(() => setTick((t) => t + 1), [])];
}

export const Spinner = () => <div className="spinner-border text-secondary" role="status"><span className="visually-hidden">Loading…</span></div>;

export const Skeleton = ({ rows = 4 }) => (
  <div className="p-3">{Array.from({ length: rows }, (_, i) => <div key={i} className="gw-skeleton mb-3" />)}</div>
);

export const Badge = ({ status }) => <span className={`gw-badge ${status.toLowerCase()}`}>{status}</span>;

export const Avatar = ({ p, size = '' }) => (
  <span className={`gw-avatar ${size}`} style={{ '--c': p.avatar_color }}>{p.initials}</span>
);

export const Empty = ({ icon, title, text }) => (
  <div className="gw-empty"><i className={`bi bi-${icon}`} /><div className="fw-semibold text-dark">{title}</div>{text && <div className="small">{text}</div>}</div>
);

export const FieldError = ({ errors, name }) => (errors?.[name] ? <div className="invalid-feedback d-block">{errors[name]}</div> : null);
export const invalid = (errors, name) => (errors?.[name] ? ' is-invalid' : '');

export function ErrorState({ error }) {
  if (!error) return null;
  if (error.status === 404) return <Empty icon="question-circle" title="Not found" text={error.message} />;
  return <div className="alert alert-danger m-3">{error.message}</div>;
}

export function PageHead({ title, subtitle, crumbs, children }) {
  return (
    <>
      {crumbs && (
        <div className="gw-breadcrumb">
          {crumbs.map(([label, to], i) => (
            <span key={label}>{i > 0 && ' / '}{to ? <Link to={to}>{label}</Link> : label}</span>
          ))}
        </div>
      )}
      <div className="gw-page-head">
        <div><h1>{title}</h1>{subtitle && <p>{subtitle}</p>}</div>
        {children}
      </div>
    </>
  );
}

// Pagination as router <Link>s that keep the other query parameters. "Next" never disables.
export function Pagination({ result }) {
  const [params] = useSearchParams();
  const to = (page) => {
    const next = new URLSearchParams(params);
    next.set('page', Math.max(1, page));
    return `?${next}`;
  };
  return (
    <nav className="d-flex justify-content-between align-items-center px-3 py-2 border-top flex-wrap gap-2" aria-label="Pagination">
      <small className="text-muted">Page {result.page} of {result.pages} · {result.total} total</small>
      <ul className="pagination pagination-sm mb-0">
        <li className={`page-item ${result.page <= 1 ? 'disabled' : ''}`}><Link className="page-link" to={to(result.page - 1)}>Previous</Link></li>
        {Array.from({ length: result.pages }, (_, i) => i + 1).map((n) => (
          <li key={n} className={`page-item ${n === result.page ? 'active' : ''}`}><Link className="page-link" to={to(n)}>{n}</Link></li>
        ))}
        <li className="page-item"><Link className="page-link" to={to(result.page + 1)}>Next</Link></li>
      </ul>
    </nav>
  );
}

export function SortTh({ label, field, className = '' }) {
  const [params] = useSearchParams();
  const sort = params.get('sort');
  const order = params.get('order') || 'desc';
  const next = new URLSearchParams(params);
  next.set('sort', field);
  next.set('order', sort === field && order === 'desc' ? 'asc' : 'desc');
  next.delete('page');
  return (
    <th className={className}>
      <Link className="text-reset text-decoration-none" to={`?${next}`}>
        {label}{sort === field && <i className={`bi bi-arrow-${order === 'desc' ? 'down' : 'up'} ms-1`} />}
      </Link>
    </th>
  );
}

export function Modal({ title, onClose, children, footer }) {
  const ref = useRef(null);
  useEffect(() => {
    const onKey = (e) => e.key === 'Escape' && onClose();
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [onClose]);
  return (
    <div className="gw-modal-backdrop" ref={ref} onClick={(e) => e.target === ref.current && onClose()}>
      <div className="gw-modal" role="dialog" aria-modal="true" aria-label={title}>
        <div className="gw-modal-head"><h3>{title}</h3><button type="button" className="btn-close" aria-label="Close" onClick={onClose} /></div>
        <div className="gw-modal-body">{children}</div>
        {footer && <div className="gw-modal-foot">{footer}</div>}
      </div>
    </div>
  );
}

export function ConfirmModal({ title, text, confirmLabel, onConfirm, onClose }) {
  const [busy, setBusy] = useState(false);
  return (
    <Modal title={title} onClose={onClose} footer={<>
      <button className="btn btn-light" onClick={onClose}>Keep it</button>
      <button className="btn btn-danger" disabled={busy} onClick={async () => { setBusy(true); await onConfirm(); setBusy(false); }}>{confirmLabel}</button>
    </>}>
      <p className="mb-0">{text}</p>
    </Modal>
  );
}

// Toasts
const ToastContext = createContext(() => {});
export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);
  const push = useCallback((message, kind = 'success') => {
    const id = Math.random();
    setToasts((t) => [...t, { id, message, kind }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 4000);
  }, []);
  return (
    <ToastContext.Provider value={push}>
      {children}
      <div className="gw-toasts">
        {toasts.map((t) => (
          <div key={t.id} className={`gw-toast ${t.kind}`} role="status">
            <i className={`bi bi-${t.kind === 'error' ? 'exclamation-circle' : 'check-circle'}`} /><span>{t.message}</span>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}
export const useToast = () => useContext(ToastContext);
