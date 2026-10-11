(function () {
  const { api, html, mount, fdate, showErrors, formData, busy, flash } = GW;
  const form = document.getElementById('wizard');
  const back = document.getElementById('back');
  const next = document.getElementById('next');
  const reason = document.getElementById('reason');
  let step = 1;

  function show(n) {
    step = n;
    form.querySelectorAll('section[data-step]').forEach((s) => { s.hidden = +s.dataset.step !== n; });
    document.querySelectorAll('#steps li').forEach((li, i) => {
      li.className = i + 1 === n ? 'current' : i + 1 < n ? 'done' : '';
      li.querySelector('span').textContent = i + 1 < n ? '✓' : i + 1;
    });
    document.getElementById('step-label').textContent = `Step ${n} of 3`;
    back.hidden = n === 1;
    mount(next, n === 3 ? html`Submit request <i class="bi bi-send"></i>` : html`Continue <i class="bi bi-arrow-right"></i>`);
  }

  // Client-side checks first, then the server validates the same step
  function clientErrors() {
    const d = formData(form);
    const errors = {};
    if (step === 1 && !d.leave_type) errors.leave_type = 'Choose a leave type.';
    if (step === 2) {
      if (!d.start_date) errors.start_date = 'Pick your first day.';
      if (!d.end_date) errors.end_date = 'Pick your last day.';
      else if (d.start_date && d.end_date < d.start_date) errors.end_date = 'End date must be on or after the start date.';
    }
    if (step === 3 && reason.value.trim().length < 5) errors.reason = 'Reason must be at least 5 characters.';
    return errors;
  }

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const errors = clientErrors();
    showErrors(form, errors);
    if (Object.keys(errors).length) return;
    busy(next, true);
    try {
      if (step < 3) {
        const result = await api('/api/leave/validate', { method: 'POST', body: { ...formData(form), step } });
        if (step === 1) document.getElementById('chosen-type').textContent = result.leave_type;
        if (step === 2) {
          mount(document.getElementById('summary'), html`
            <dt>Leave type</dt><dd>${result.leave_type}</dd>
            <dt>Dates</dt><dd>${fdate(result.start_date)} – ${fdate(result.end_date)}</dd>
            <dt>Working days</dt><dd>${result.days}</dd>`);
        }
        busy(next, false);
        show(step + 1);
      } else {
        const { id } = await api('/api/leave', { method: 'POST', body: formData(form) });
        flash('Leave request submitted for approval.');
        location.href = `/leave/${id}`;
      }
    } catch (err) {
      busy(next, false);
      const errors = err.errors && Object.keys(err.errors).length ? err.errors : { _: err.message };
      // Dates can become invalid between steps (e.g. another request now overlaps)
      if (errors.leave_type) show(1);
      else if (step === 3 && (errors.start_date || errors.end_date)) show(2);
      showErrors(form, errors);
    }
  });

  back.addEventListener('click', () => { showErrors(form, {}); show(step - 1); });
  reason.addEventListener('input', () => { document.getElementById('reason-count').textContent = reason.value.length; });
  show(1);
})();
