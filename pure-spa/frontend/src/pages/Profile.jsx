import { useState } from 'react';
import { Link, NavLink, Navigate, useParams } from 'react-router-dom';
import { api } from '../api.js';
import { useAuth } from '../auth.jsx';
import { Avatar, FieldError, invalid, Skeleton, useApi, useTitle, useToast } from '../ui.jsx';

const LOCATIONS = ['Singapore HQ · Level 12', 'Singapore HQ · Level 14', 'Jurong East Office', 'Remote'];

function useSave(endpoint, success, after) {
  const toast = useToast();
  const [errors, setErrors] = useState({});
  const [busy, setBusy] = useState(false);
  async function save(e, body) {
    e.preventDefault();
    setBusy(true);
    try {
      await api(endpoint, { method: 'PUT', body });
      setErrors({});
      toast(success);
      after?.();
    } catch (err) {
      setErrors(Object.keys(err.errors || {}).length ? err.errors : { _: err.message });
    }
    setBusy(false);
  }
  return { errors, busy, save };
}

function Details({ me, reload }) {
  const [form, setForm] = useState({ phone: me.phone, location: me.location, bio: me.bio });
  const { errors, busy, save } = useSave('/api/me/profile', 'Profile updated.', reload);
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });
  return (
    <form onSubmit={(e) => save(e, form)} noValidate>
      <div className="gw-card-body"><div className="row g-3">
        {errors._ && <div className="col-12 alert alert-danger">{errors._}</div>}
        <div className="col-sm-6"><label className="form-label">Full name</label><input className="form-control" value={me.full_name} disabled /><div className="form-text">Contact HR to change your legal name.</div></div>
        <div className="col-sm-6"><label className="form-label">Work email</label><input className="form-control" value={me.email} disabled /></div>
        <div className="col-sm-6">
          <label className="form-label" htmlFor="phone">Phone</label>
          <input className={`form-control${invalid(errors, 'phone')}`} id="phone" name="phone" type="tel" value={form.phone} onChange={set('phone')} />
          <FieldError errors={errors} name="phone" />
        </div>
        <div className="col-sm-6">
          <label className="form-label" htmlFor="location">Location</label>
          <input className={`form-control${invalid(errors, 'location')}`} id="location" name="location" maxLength={60} list="locations" value={form.location} onChange={set('location')} />
          <datalist id="locations">{LOCATIONS.map((l) => <option key={l}>{l}</option>)}</datalist>
          <FieldError errors={errors} name="location" />
        </div>
        <div className="col-12">
          <label className="form-label" htmlFor="bio">About me</label>
          <textarea className={`form-control${invalid(errors, 'bio')}`} id="bio" name="bio" rows={3} maxLength={300} value={form.bio} onChange={set('bio')} />
          <FieldError errors={errors} name="bio" />
        </div>
      </div></div>
      <div className="gw-modal-foot"><button className="btn btn-primary" disabled={busy}>Save changes</button></div>
    </form>
  );
}

function Security() {
  const empty = { current_password: '', new_password: '', confirm_password: '' };
  const [form, setForm] = useState(empty);
  const { errors, busy, save } = useSave('/api/me/password', 'Password changed.', () => setForm(empty));
  const fields = [['current_password', 'Current password', 'current-password'], ['new_password', 'New password', 'new-password'], ['confirm_password', 'Confirm new password', 'new-password']];
  return (
    <form onSubmit={(e) => save(e, form)} noValidate>
      <div className="gw-card-body"><div className="row g-3" style={{ maxWidth: 420 }}>
        {errors._ && <div className="col-12 alert alert-danger">{errors._}</div>}
        {fields.map(([name, label, ac]) => (
          <div className="col-12" key={name}>
            <label className="form-label" htmlFor={name}>{label}</label>
            <input className={`form-control${invalid(errors, name)}`} id={name} name={name} type="password" autoComplete={ac} value={form[name]} onChange={(e) => setForm({ ...form, [name]: e.target.value })} />
            <FieldError errors={errors} name={name} />
          </div>
        ))}
        <div className="form-text">At least 10 characters, with letters and numbers.</div>
      </div></div>
      <div className="gw-modal-foot"><button className="btn btn-primary" disabled={busy}>Change password</button></div>
    </form>
  );
}

function Preferences({ me, reload }) {
  const [{ data: meta }] = useApi('/api/meta');
  const [form, setForm] = useState({
    pref_email_notifications: !!me.pref_email_notifications, pref_weekly_digest: !!me.pref_weekly_digest, pref_language: me.pref_language,
  });
  const { busy, save } = useSave('/api/me/preferences', 'Preferences saved.', reload);
  const toggle = (name, label) => (
    <div className="form-check form-switch mb-3">
      <input className="form-check-input" type="checkbox" role="switch" id={name} checked={form[name]} onChange={(e) => setForm({ ...form, [name]: e.target.checked })} />
      <label className="form-check-label" htmlFor={name}>{label}</label>
    </div>
  );
  return (
    <form onSubmit={(e) => save(e, form)}>
      <div className="gw-card-body">
        {toggle('pref_email_notifications', 'Email me when my requests are approved or rejected')}
        {toggle('pref_weekly_digest', 'Send me a weekly digest of team leave')}
        <label className="form-label" htmlFor="pref_language">Language</label>
        <select className="form-select" id="pref_language" style={{ maxWidth: 260 }} value={form.pref_language} onChange={(e) => setForm({ ...form, pref_language: e.target.value })}>
          {meta && Object.entries(meta.languages).map(([code, label]) => <option key={code} value={code}>{label}</option>)}
        </select>
      </div>
      <div className="gw-modal-foot"><button className="btn btn-primary" disabled={busy}>Save changes</button></div>
    </form>
  );
}

export function Profile() {
  const { tab = 'details' } = useParams();
  const { reload: reloadUser } = useAuth();
  const [{ data: me }, reload] = useApi('/api/me');
  useTitle('My profile');
  if (!['details', 'security', 'preferences'].includes(tab)) return <Navigate to="/profile" replace />;
  if (!me) return <Skeleton rows={6} />;
  const refresh = () => { reload(); reloadUser(); };
  const tabClass = ({ isActive }) => (isActive ? 'active' : '');

  return (
    <>
      <div className="gw-page-head">
        <div className="d-flex gap-3 align-items-center">
          <Avatar p={me} size="lg" />
          <div><h1>{me.full_name}</h1><p>{me.job_title} · {me.department} · @{me.username}</p></div>
        </div>
        <Link className="btn btn-outline-primary" to={`/directory/${me.id}`}><i className="bi bi-eye" /> View public profile</Link>
      </div>
      <div className="gw-card" style={{ maxWidth: 860 }}>
        <nav className="gw-tabs">
          <NavLink to="/profile" end className={({ isActive }) => (isActive || tab === 'details' ? 'active' : '')}>Details</NavLink>
          <NavLink to="/profile/security" className={tabClass}>Security</NavLink>
          <NavLink to="/profile/preferences" className={tabClass}>Preferences</NavLink>
        </nav>
        {tab === 'details' && <Details key={me.phone + me.bio} me={me} reload={refresh} />}
        {tab === 'security' && <Security />}
        {tab === 'preferences' && <Preferences me={me} reload={refresh} />}
      </div>
    </>
  );
}
