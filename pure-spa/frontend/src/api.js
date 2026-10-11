// API client. The access token lives only in memory; the refresh token is kept
// in localStorage so a reload can silently restore the session.
const REFRESH_KEY = 'gw_refresh';
let accessToken = null;
let refreshing = null;
let onExpired = () => {};

export class ApiError extends Error {
  constructor(message, status, errors = {}) {
    super(message);
    this.status = status;
    this.errors = errors;
  }
}

export function onSessionExpired(fn) {
  onExpired = fn;
}

function store(tokens) {
  accessToken = tokens.access_token;
  try { localStorage.setItem(REFRESH_KEY, tokens.refresh_token); } catch { /* private mode */ }
}

function clear() {
  accessToken = null;
  try { localStorage.removeItem(REFRESH_KEY); } catch { /* ignore */ }
}

function savedRefresh() {
  try { return localStorage.getItem(REFRESH_KEY); } catch { return null; }
}

// Concurrent 401s share one refresh request (refresh tokens are single-use)
function refresh() {
  if (!refreshing) {
    refreshing = (async () => {
      const token = savedRefresh();
      if (!token) return null;
      const res = await fetch('/api/auth/refresh', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: token }),
      });
      if (!res.ok) { clear(); return null; }
      const data = await res.json();
      store(data);
      return data;
    })().finally(() => { refreshing = null; });
  }
  return refreshing;
}

export async function api(path, { method = 'GET', body, form, blob = false } = {}, retry = true) {
  const headers = { Accept: 'application/json' };
  if (accessToken) headers.Authorization = `Bearer ${accessToken}`;
  const opts = { method, headers };
  if (form) opts.body = form;
  else if (body !== undefined) {
    opts.body = JSON.stringify(body);
    headers['Content-Type'] = 'application/json';
  }
  const res = await fetch(path, opts);
  if (res.status === 401 && retry) {
    if (await refresh()) return api(path, { method, body, form, blob }, false);
    clear();
    onExpired();
    throw new ApiError('Your session has expired. Please sign in again.', 401);
  }
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new ApiError(data.detail || `Request failed (${res.status})`, res.status, data.errors || {});
  }
  return blob ? res.blob() : res.json();
}

async function authenticate(path, body, fallback) {
  const res = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const data = await res.json();
  if (!res.ok) throw new ApiError(data.detail || fallback, res.status, data.errors || {});
  store(data);
  return data.user;
}

export const login = (username, password) => authenticate('/api/auth/login', { username, password }, 'Sign in failed.');

// Creates the account and signs straight in (the API answers with tokens, like login)
export const register = (form) => authenticate('/api/auth/register', form, 'Could not create your account.');

export async function restoreSession() {
  const data = await refresh();
  return data ? data.user : null;
}

export async function logout() {
  const token = savedRefresh();
  clear();
  await fetch('/api/auth/logout', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh_token: token }),
  }).catch(() => {});
}

export function saveBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
