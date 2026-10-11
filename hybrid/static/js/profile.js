(function () {
  const { api, html, mount, skeleton, showErrors, formData, busy, toast } = GW;
  const panel = document.getElementById('tab-panel');
  const tabs = document.querySelectorAll('[data-tab]');
  const LOCATIONS = ['Singapore HQ · Level 12', 'Singapore HQ · Level 14', 'Jurong East Office', 'Remote'];

  const renderers = {
    async details() {
      const me = await api('/api/me');
      return html`<form data-endpoint="/api/me/profile" data-success="Profile updated."><div class="gw-card-body"><div class="row g-3">
        <div class="col-sm-6"><label class="form-label">Full name</label><input class="form-control" value="${me.full_name}" disabled><div class="form-text">Contact HR to change your legal name.</div></div>
        <div class="col-sm-6"><label class="form-label">Work email</label><input class="form-control" value="${me.email}" disabled></div>
        <div class="col-sm-6"><label class="form-label" for="phone">Phone</label><input class="form-control" id="phone" name="phone" type="tel" value="${me.phone}"></div>
        <div class="col-sm-6"><label class="form-label" for="location">Location</label><input class="form-control" id="location" name="location" maxlength="60" list="locations" value="${me.location}">
          <datalist id="locations">${LOCATIONS.map((l) => html`<option>${l}</option>`)}</datalist></div>
        <div class="col-12"><label class="form-label" for="bio">About me</label><textarea class="form-control" id="bio" name="bio" rows="3" maxlength="300">${me.bio}</textarea></div>
      </div></div><div class="gw-modal-foot"><button class="btn btn-primary">Save changes</button></div></form>`;
    },
    async security() {
      const field = (name, label, ac) => html`<div class="col-12"><label class="form-label" for="${name}">${label}</label><input class="form-control" id="${name}" name="${name}" type="password" autocomplete="${ac}"></div>`;
      return html`<form data-endpoint="/api/me/password" data-success="Password changed." data-reset="1"><div class="gw-card-body"><div class="row g-3" style="max-width:420px">
        ${field('current_password', 'Current password', 'current-password')}
        ${field('new_password', 'New password', 'new-password')}
        ${field('confirm_password', 'Confirm new password', 'new-password')}
        <div class="form-text">At least 10 characters, with letters and numbers.</div>
      </div></div><div class="gw-modal-foot"><button class="btn btn-primary">Change password</button></div></form>`;
    },
    async preferences() {
      const [me, meta] = await Promise.all([api('/api/me'), api('/api/meta')]);
      const toggle = (name, label, on) => html`<div class="form-check form-switch mb-3"><input class="form-check-input" type="checkbox" role="switch" id="${name}" name="${name}" value="1" ${on ? 'checked' : ''}><label class="form-check-label" for="${name}">${label}</label></div>`;
      return html`<form data-endpoint="/api/me/preferences" data-success="Preferences saved."><div class="gw-card-body">
        ${toggle('pref_email_notifications', 'Email me when my requests are approved or rejected', me.pref_email_notifications)}
        ${toggle('pref_weekly_digest', 'Send me a weekly digest of team leave', me.pref_weekly_digest)}
        <label class="form-label" for="pref_language">Language</label>
        <select class="form-select" id="pref_language" name="pref_language" style="max-width:260px">
          ${Object.entries(meta.languages).map(([code, label]) => html`<option value="${code}" ${me.pref_language === code ? 'selected' : ''}>${label}</option>`)}
        </select>
      </div><div class="gw-modal-foot"><button class="btn btn-primary">Save changes</button></div></form>`;
    },
  };

  async function open(name) {
    if (!renderers[name]) name = 'details';
    tabs.forEach((t) => t.classList.toggle('active', t.dataset.tab === name));
    history.replaceState(null, '', `#${name}`);
    mount(panel, skeleton(4));
    mount(panel, await renderers[name]());
  }

  panel.addEventListener('submit', async (e) => {
    e.preventDefault();
    const form = e.target;
    const button = form.querySelector('button');
    busy(button, true);
    try {
      await api(form.dataset.endpoint, { method: 'PUT', body: formData(form) });
      showErrors(form, {});
      toast(form.dataset.success);
      if (form.dataset.reset) form.reset();
    } catch (err) {
      showErrors(form, Object.keys(err.errors).length ? err.errors : { _: err.message });
    }
    busy(button, false);
  });

  tabs.forEach((t) => t.addEventListener('click', () => open(t.dataset.tab)));
  open(location.hash.slice(1) || 'details');
})();
