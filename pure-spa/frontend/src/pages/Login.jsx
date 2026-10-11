import { useState } from 'react';
import { Link, Navigate, useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '../auth.jsx';
import { useTitle } from '../ui.jsx';

function safeNext(next) {
  return next && next.startsWith('/') && !next.startsWith('//') && !next.includes('\\') ? next : '/dashboard';
}

export default function Login() {
  useTitle('Sign in');
  const { user, ready, signIn } = useAuth();
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const [form, setForm] = useState({ username: '', password: '', remember: false });
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const next = safeNext(params.get('next'));

  if (ready && user) return <Navigate to={next} replace />;

  async function submit(e) {
    e.preventDefault();
    if (!form.username.trim() || !form.password) {
      setError('Enter your username and password.');
      return;
    }
    setBusy(true);
    setError('');
    try {
      await signIn(form.username, form.password);
      navigate(next, { replace: true });
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  }

  const set = (key) => (e) => setForm({ ...form, [key]: e.target.type === 'checkbox' ? e.target.checked : e.target.value });

  return (
    <div className="gw-auth">
      <div className="gw-auth-side">
        <div className="d-flex align-items-center gap-2 fw-bold fs-5 text-white"><span className="gw-logo">G</span> GoWork</div>
        <div>
          <h2>Everything about work, in one place.</h2>
          <p className="mt-3" style={{ maxWidth: 420 }}>Apply for leave, submit claims, find colleagues and keep track of approvals - all from your GoWork portal.</p>
        </div>
        <div className="small opacity-75">© 2026 GoWork Pte Ltd · <Link className="link-light" to="/help">Help centre</Link></div>
      </div>
      <div className="gw-auth-form">
        <form onSubmit={submit} noValidate>
          <h1 className="h3 fw-bold mb-1">Welcome back</h1>
          <p className="text-muted mb-4">Sign in with your GoWork account.</p>
          {params.get('signed_out') && <div className="alert alert-success py-2">You've been signed out.</div>}
          {params.get('expired') && <div className="alert alert-warning py-2"><i className="bi bi-clock-history" /> Your session expired. Please sign in again.</div>}
          {error && <div className="alert alert-danger py-2"><i className="bi bi-exclamation-circle" /> {error}</div>}
          <div className="mb-3">
            <label className="form-label" htmlFor="username">Username</label>
            <input className="form-control" id="username" name="username" autoComplete="username" autoFocus value={form.username} onChange={set('username')} />
          </div>
          <div className="mb-3">
            <div className="d-flex justify-content-between"><label className="form-label" htmlFor="password">Password</label><Link className="small" to="/help#password">Forgot password?</Link></div>
            <input className="form-control" id="password" name="password" type="password" autoComplete="current-password" value={form.password} onChange={set('password')} />
          </div>
          <div className="form-check mb-4">
            <input className="form-check-input" type="checkbox" id="remember" checked={form.remember} onChange={set('remember')} />
            <label className="form-check-label" htmlFor="remember">Keep me signed in on this device</label>
          </div>
          <button className="btn btn-primary w-100 py-2" type="submit" disabled={busy}>
            {busy ? <span className="spinner-border spinner-border-sm" /> : 'Sign in'}
          </button>
          <p className="text-center text-muted small mt-4 mb-0">New here? <Link to="/register">Create an account</Link></p>
        </form>
      </div>
    </div>
  );
}
