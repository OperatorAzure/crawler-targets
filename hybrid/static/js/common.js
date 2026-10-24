/* GoWork hybrid - shared browser helpers (window.GW) */
(function () {
  const csrf = document.querySelector('meta[name="csrf-token"]')?.content || '';

  // --- escaping: html`...` escapes every interpolated value unless wrapped in raw()
  const ESC = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
  const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ESC[c]);
  const raw = (h) => ({ __raw: true, h });
  const part = (v) => (Array.isArray(v) ? v.map(part).join('') : v && v.__raw ? v.h : esc(v));
  const html = (strings, ...values) =>
    raw(strings.reduce((out, s, i) => out + s + (i < values.length ? part(values[i]) : ''), ''));
  const mount = (el, content) => { el.innerHTML = part(content); return el; };

  // --- API wrapper: sends CSRF header, bounces to login on 401
  async function api(path, { method = 'GET', body, form } = {}) {
    const opts = { method, headers: { Accept: 'application/json' }, credentials: 'same-origin' };
    if (method !== 'GET') opts.headers['X-CSRF-Token'] = csrf;
    if (form) opts.body = form;
    else if (body !== undefined) {
      opts.body = JSON.stringify(body);
      opts.headers['Content-Type'] = 'application/json';
    }
    const res = await fetch(path, opts);
    if (res.status === 401) {
      const next = encodeURIComponent(location.pathname + location.search);
      location.href = `/login?expired=1&next=${next}`;
      throw new Error('Session expired');
    }
    const isJson = (res.headers.get('content-type') || '').includes('json');
    const data = isJson ? await res.json() : await res.blob();
    if (!res.ok) {
      const err = new Error((isJson && data.detail) || `Request failed (${res.status})`);
      err.status = res.status;
      err.errors = (isJson && data.errors) || {};
      throw err;
    }
    return data;
  }

  // --- formatting
  const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  function fdate(iso) {
    if (!iso) return '—';
    const [y, m, d] = iso.slice(0, 10).split('-');
    const out = `${d} ${MONTHS[+m - 1]} ${y}`;
    return iso.includes('T') ? `${out}, ${iso.slice(11, 16)}` : out;
  }
  const badge = (status) => html`<span class="gw-badge ${status.toLowerCase()}">${status}</span>`;
  const avatar = (p, size = '') =>
    html`<span class="gw-avatar ${size}" style="--c: ${p.avatar_color}">${p.initials}</span>`;
  const empty = (icon, title, text = '') =>
    html`<div class="gw-empty"><i class="bi bi-${icon}"></i><div class="fw-semibold text-dark">${title}</div>${text ? html`<div class="small">${text}</div>` : ''}</div>`;
  const skeleton = (rows = 4) =>
    html`<div class="p-3">${Array.from({ length: rows }, () => html`<div class="gw-skeleton mb-3"></div>`)}</div>`;

  // --- toasts
  function toast(message, kind = 'success') {
    let box = document.querySelector('.gw-toasts');
    if (!box) {
      box = document.createElement('div');
      box.className = 'gw-toasts';
      document.body.appendChild(box);
    }
    const el = document.createElement('div');
    el.className = `gw-toast ${kind}`;
    el.setAttribute('role', 'status');
    mount(el, html`<i class="bi bi-${kind === 'error' ? 'exclamation-circle' : 'check-circle'}"></i><span>${message}</span>`);
    box.appendChild(el);
    setTimeout(() => el.remove(), 4000);
  }

  // Flash messages survive a page navigation through sessionStorage
  function flash(message) { try { sessionStorage.setItem('gw-flash', message); } catch (_) { /* ignore */ } }
  try {
    const pending = sessionStorage.getItem('gw-flash');
    if (pending) { sessionStorage.removeItem('gw-flash'); setTimeout(() => toast(pending), 50); }
  } catch (_) { /* ignore */ }

  // --- modal
  function modal({ title, body, footer = '' }) {
    const backdrop = document.createElement('div');
    backdrop.className = 'gw-modal-backdrop';
    mount(backdrop, html`<div class="gw-modal" role="dialog" aria-modal="true" aria-label="${title}">
      <div class="gw-modal-head"><h3>${title}</h3><button type="button" class="btn-close" data-close aria-label="Close"></button></div>
      <div class="gw-modal-body">${body}</div>
      ${footer ? html`<div class="gw-modal-foot">${footer}</div>` : ''}
    </div>`);
    const close = () => { backdrop.remove(); document.removeEventListener('keydown', onKey); };
    const onKey = (e) => e.key === 'Escape' && close();
    backdrop.addEventListener('click', (e) => { if (e.target === backdrop || e.target.closest('[data-close]')) close(); });
    document.addEventListener('keydown', onKey);
    document.body.appendChild(backdrop);
    return { el: backdrop, close, body: backdrop.querySelector('.gw-modal-body') };
  }

  function confirmDialog(title, text, confirmLabel = 'Confirm', danger = true) {
    return new Promise((resolve) => {
      const m = modal({
        title, body: html`<p class="mb-0">${text}</p>`,
        footer: html`<button class="btn btn-light" data-close>Keep it</button><button class="btn ${danger ? 'btn-danger' : 'btn-primary'}" data-ok>${confirmLabel}</button>`,
      });
      m.el.querySelector('[data-ok]').addEventListener('click', () => { m.close(); resolve(true); });
      m.el.addEventListener('click', (e) => { if (e.target.closest('[data-close]') || e.target === m.el) resolve(false); });
    });
  }

  // --- pagination built from buttons (no hrefs); "Next" never disables
  function pagination(result, onPage) {
    const nav = document.createElement('nav');
    nav.className = 'd-flex justify-content-between align-items-center px-3 py-2 border-top flex-wrap gap-2';
    const pages = Array.from({ length: result.pages }, (_, i) => i + 1);
    mount(nav, html`<small class="text-muted">Page ${result.page} of ${result.pages} · ${result.total} total</small>
      <ul class="pagination pagination-sm mb-0">
        <li class="page-item ${result.page <= 1 ? 'disabled' : ''}"><button class="page-link" data-page="${result.page - 1}">Previous</button></li>
        ${pages.map((n) => html`<li class="page-item ${n === result.page ? 'active' : ''}"><button class="page-link" data-page="${n}">${n}</button></li>`)}
        <li class="page-item"><button class="page-link" data-page="${result.page + 1}">Next</button></li>
      </ul>`);
    nav.addEventListener('click', (e) => {
      const btn = e.target.closest('[data-page]');
      if (btn) onPage(Math.max(1, +btn.dataset.page));
    });
    return nav;
  }

  // --- forms
  function showErrors(form, errors) {
    form.querySelectorAll('.is-invalid').forEach((el) => el.classList.remove('is-invalid'));
    form.querySelectorAll('.invalid-feedback[data-js]').forEach((el) => el.remove());
    Object.entries(errors || {}).forEach(([name, message]) => {
      const field = form.querySelector(`[name="${name}"]`);
      const fb = document.createElement('div');
      fb.className = 'invalid-feedback d-block';
      fb.dataset.js = '1';
      fb.textContent = message;
      if (field) {
        field.classList.add('is-invalid');
        (field.closest('.input-group, .form-check') || field).after(fb);
      } else {
        form.prepend(fb);
      }
    });
  }
  const formData = (form) => Object.fromEntries(new FormData(form).entries());
  function busy(button, on) {
    if (!button) return;
    button.disabled = on;
    if (on) { button.dataset.label = button.innerHTML; button.innerHTML = '<span class="spinner-border spinner-border-sm"></span>'; }
    else if (button.dataset.label) button.innerHTML = button.dataset.label;
  }

  // Keep list filters in the address bar without reloading
  function setQuery(params) {
    const qs = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => { if (v !== '' && v != null) qs.set(k, v); });
    history.replaceState(null, '', location.pathname + (qs.toString() ? `?${qs}` : ''));
  }
  const query = () => Object.fromEntries(new URLSearchParams(location.search).entries());

  function download(blob, filename) {
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  // --- global actions
  document.addEventListener('click', async (e) => {
    const btn = e.target.closest('[data-action="export-taxes"]');
    if (!btn) return;
    e.preventDefault();
    try {
      // Crawler trap: this background request ends the session on the server (unless EXPORT_TRAP=0)
      const blob = await api('/api/export-taxes?year=2025');
      download(blob, 'IR8A_2025.pdf');
      toast('Tax statement downloaded.');
    } catch (err) {
      toast(err.message, 'error');
    }
  });

  window.GW = {
    api, html, raw, esc, mount, fdate, badge, avatar, empty, skeleton, toast, flash, modal, confirmDialog,
    pagination, showErrors, formData, busy, setQuery, query, download,
  };
})();
