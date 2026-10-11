(function () {
  const { api, html, mount, showErrors, formData, busy, flash } = GW;
  const form = document.getElementById('register-form');
  const username = document.getElementById('username');
  const usernameStatus = document.getElementById('username-status');
  const department = document.getElementById('department');
  const manager = document.getElementById('manager_id');

  // Live "is this username free?" check
  let timer;
  username.addEventListener('input', () => {
    clearTimeout(timer);
    const value = username.value.trim().toLowerCase();
    if (!value) {
      usernameStatus.className = 'form-text';
      usernameStatus.textContent = 'Lowercase letters, numbers, dots or underscores.';
      return;
    }
    timer = setTimeout(async () => {
      const result = await api(`/api/auth/username-available?username=${encodeURIComponent(value)}`);
      usernameStatus.className = `form-text ${result.available ? 'text-success' : 'text-danger'}`;
      usernameStatus.textContent = result.message;
    }, 350);
  });

  // "Reports to" depends on the department
  department.addEventListener('change', async () => {
    manager.disabled = true;
    if (!department.value) {
      mount(manager, html`<option value="">Choose a department first</option>`);
      return;
    }
    mount(manager, html`<option value="">Loading…</option>`);
    const { items } = await api(`/api/auth/register/managers?department=${encodeURIComponent(department.value)}`);
    mount(manager, html`<option value="">Choose…</option>${items.map((m) => html`<option value="${m.id}">${m.full_name} · ${m.job_title}</option>`)}`);
    manager.disabled = false;
  });

  function clientErrors(d) {
    const errors = {};
    if ((d.full_name || '').trim().length < 2) errors.full_name = 'Full name must be 2-60 characters.';
    if (!/^[a-z][a-z0-9._]{2,19}$/.test((d.username || '').trim().toLowerCase())) errors.username = '3-20 characters: lowercase letters, numbers, dots or underscores.';
    if (!/^[^@\s]+@[^@\s]+\.[a-z]{2,}$/i.test(d.email || '')) errors.email = 'Enter a valid email address.';
    if ((d.password || '').length < 10 || !/[A-Za-z]/.test(d.password) || !/\d/.test(d.password)) errors.password = 'Use at least 10 characters with letters and numbers.';
    if (d.password !== d.confirm_password) errors.confirm_password = "Passwords don't match.";
    if (!d.department) errors.department = 'Choose a department.';
    if ((d.job_title || '').trim().length < 2) errors.job_title = 'Job title must be 2-60 characters.';
    if (!d.manager_id) errors.manager_id = 'Choose who you report to.';
    if (!/^[A-Za-z]{2}-\d{4}-\d{4}$/.test((d.invite_code || '').trim())) errors.invite_code = 'Enter your code in the format GW-2026-XXXX.';
    if (!d.agree_terms) errors.agree_terms = 'You need to accept the Terms & Privacy notice.';
    return errors;
  }

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const data = formData(form);
    const errors = clientErrors(data);
    showErrors(form, errors);
    if (Object.keys(errors).length) return;
    const button = form.querySelector('[type="submit"]');
    busy(button, true);
    try {
      const result = await api('/api/auth/register', { method: 'POST', body: data });
      flash(`Welcome to GoWork, ${data.full_name.trim().split(' ')[0]}! Your account is ready.`);
      location.href = result.next;
    } catch (err) {
      busy(button, false);
      showErrors(form, Object.keys(err.errors || {}).length ? err.errors : { _: err.message });
    }
  });
})();
