import { useEffect, useState } from 'react';
import { Link, Navigate, useNavigate } from 'react-router-dom';
import { api } from '../api.js';
import { useAuth } from '../auth.jsx';
import { FieldError, invalid, useTitle, useToast } from '../ui.jsx';

const DEPARTMENTS = ['Engineering', 'Finance', 'Human Resources', 'Marketing', 'Sales', 'Operations'];
const BLANK = {
  full_name: '', username: '', email: '', password: '', confirm_password: '',
  department: '', job_title: '', manager_id: '', invite_code: '', agree_terms: false,
};

function clientErrors(f) {
  const e = {};
  if (f.full_name.trim().length < 2) e.full_name = 'Full name must be 2-60 characters.';
  if (!/^[a-z][a-z0-9._]{2,19}$/.test(f.username.trim().toLowerCase())) e.username = '3-20 characters: lowercase letters, numbers, dots or underscores.';
  if (!/^[^@\s]+@[^@\s]+\.[a-z]{2,}$/i.test(f.email)) e.email = 'Enter a valid email address.';
  if (f.password.length < 10 || !/[A-Za-z]/.test(f.password) || !/\d/.test(f.password)) e.password = 'Use at least 10 characters with letters and numbers.';
  if (f.password !== f.confirm_password) e.confirm_password = "Passwords don't match.";
  if (!f.department) e.department = 'Choose a department.';
  if (f.job_title.trim().length < 2) e.job_title = 'Job title must be 2-60 characters.';
  if (!f.manager_id) e.manager_id = 'Choose who you report to.';
  if (!/^[A-Za-z]{2}-\d{4}-\d{4}$/.test(f.invite_code.trim())) e.invite_code = 'Enter your code in the format GW-2026-XXXX.';
  if (!f.agree_terms) e.agree_terms = 'You need to accept the Terms & Privacy notice.';
  return e;
}

export function Register() {
  useTitle('Create your account');
  const { user, ready, signUp } = useAuth();
  const navigate = useNavigate();
  const toast = useToast();
  const [form, setForm] = useState(BLANK);
  const [errors, setErrors] = useState({});
  const [busy, setBusy] = useState(false);
  const [managers, setManagers] = useState(null);
  const [usernameCheck, setUsernameCheck] = useState(null);
  const set = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.type === 'checkbox' ? e.target.checked : e.target.value }));

  // Live "is this username free?" check
  useEffect(() => {
    const value = form.username.trim().toLowerCase();
    if (!value) { setUsernameCheck(null); return undefined; }
    let alive = true;
    const t = setTimeout(async () => {
      const result = await api(`/api/auth/username-available?username=${encodeURIComponent(value)}`);
      if (alive) setUsernameCheck(result);
    }, 350);
    return () => { alive = false; clearTimeout(t); };
  }, [form.username]);

  // "Reports to" depends on the department
  useEffect(() => {
    setManagers(null);
    setForm((f) => ({ ...f, manager_id: '' }));
    if (!form.department) return undefined;
    let alive = true;
    api(`/api/auth/register/managers?department=${encodeURIComponent(form.department)}`).then((d) => alive && setManagers(d.items));
    return () => { alive = false; };
  }, [form.department]);

  if (ready && user) return <Navigate to="/dashboard" replace />;

  async function submit(e) {
    e.preventDefault();
    const found = clientErrors(form);
    setErrors(found);
    if (Object.keys(found).length) return;
    setBusy(true);
    try {
      await signUp(form);
      toast(`Welcome to GoWork, ${form.full_name.trim().split(' ')[0]}! Your account is ready.`);
      navigate('/dashboard', { replace: true });
    } catch (err) {
      setErrors(Object.keys(err.errors || {}).length ? err.errors : { _: err.message });
      setBusy(false);
    }
  }

  const field = (name, label, props = {}, help = null) => (
    <>
      <label className="form-label" htmlFor={name}>{label}</label>
      <input className={`form-control${invalid(errors, name)}`} id={name} name={name} value={form[name]} onChange={set(name)} {...props} />
      {help}
      <FieldError errors={errors} name={name} />
    </>
  );

  return (
    <div className="gw-auth">
      <div className="gw-auth-side">
        <div className="d-flex align-items-center gap-2 fw-bold fs-5 text-white"><span className="gw-logo">G</span> GoWork</div>
        <div>
          <h2>Welcome aboard.</h2>
          <p className="mt-3" style={{ maxWidth: 420 }}>Set up your GoWork account with the employee ID / invite code HR sent you. You&apos;ll be signed in straight away.</p>
        </div>
        <div className="small opacity-75">© 2026 GoWork Pte Ltd · <Link className="link-light" to="/help">Help centre</Link></div>
      </div>
      <div className="gw-auth-form">
        <form className="wide" onSubmit={submit} noValidate>
          <h1 className="h3 fw-bold mb-1">Create your account</h1>
          <p className="text-muted mb-4">Already have one? <Link to="/login">Sign in</Link></p>
          {errors._ && <div className="alert alert-danger py-2">{errors._}</div>}

          <h2 className="h6 fw-semibold text-muted text-uppercase small mb-3">Your account</h2>
          <div className="row g-3 mb-4">
            <div className="col-12">{field('full_name', 'Full name', { maxLength: 60, autoComplete: 'name' })}</div>
            <div className="col-sm-6">
              {field('username', 'Username', { autoComplete: 'username' },
                <div className={`form-text ${usernameCheck ? (usernameCheck.available ? 'text-success' : 'text-danger') : ''}`}>
                  {usernameCheck ? usernameCheck.message : 'Lowercase letters, numbers, dots or underscores.'}
                </div>)}
            </div>
            <div className="col-sm-6">{field('email', 'Work email', { type: 'email', autoComplete: 'email' })}</div>
            <div className="col-sm-6">
              {field('password', 'Password', { type: 'password', autoComplete: 'new-password' },
                <div className="form-text">At least 10 characters, with letters and numbers.</div>)}
            </div>
            <div className="col-sm-6">{field('confirm_password', 'Confirm password', { type: 'password', autoComplete: 'new-password' })}</div>
          </div>

          <h2 className="h6 fw-semibold text-muted text-uppercase small mb-3">Your work</h2>
          <div className="row g-3 mb-4">
            <div className="col-sm-6">
              <label className="form-label" htmlFor="department">Department</label>
              <select className={`form-select${invalid(errors, 'department')}`} id="department" name="department" value={form.department} onChange={set('department')}>
                <option value="">Choose…</option>{DEPARTMENTS.map((d) => <option key={d}>{d}</option>)}
              </select>
              <FieldError errors={errors} name="department" />
            </div>
            <div className="col-sm-6">{field('job_title', 'Job title', { maxLength: 60 })}</div>
            <div className="col-sm-6">
              <label className="form-label" htmlFor="manager_id">Reports to</label>
              <select className={`form-select${invalid(errors, 'manager_id')}`} id="manager_id" name="manager_id" value={form.manager_id} onChange={set('manager_id')} disabled={!managers}>
                {managers
                  ? <><option value="">Choose…</option>{managers.map((m) => <option key={m.id} value={m.id}>{m.full_name} · {m.job_title}</option>)}</>
                  : <option value="">{form.department ? 'Loading…' : 'Choose a department first'}</option>}
              </select>
              <FieldError errors={errors} name="manager_id" />
            </div>
            <div className="col-sm-6">{field('invite_code', 'Employee ID / invite code', { placeholder: 'GW-2026-XXXX' })}</div>
          </div>

          <div className="form-check mb-4">
            <input className={`form-check-input${invalid(errors, 'agree_terms')}`} type="checkbox" id="agree_terms" name="agree_terms" checked={form.agree_terms} onChange={set('agree_terms')} />
            <label className="form-check-label" htmlFor="agree_terms">I agree to the <Link to="/terms">Terms &amp; Privacy notice</Link></label>
            <FieldError errors={errors} name="agree_terms" />
          </div>
          <button className="btn btn-primary w-100 py-2" type="submit" disabled={busy}>
            {busy ? <span className="spinner-border spinner-border-sm" /> : 'Create account'}
          </button>
        </form>
      </div>
    </div>
  );
}
