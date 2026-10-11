(function () {
  const { api, html, mount, showErrors, busy, flash } = GW;
  const form = document.getElementById('claim-form');
  const category = document.getElementById('category');
  const sub = document.getElementById('subcategory');
  const amount = document.getElementById('amount');
  const receipt = document.getElementById('receipt');

  // Dependent dropdown
  category.addEventListener('change', async () => {
    sub.disabled = true;
    if (!category.value) {
      mount(sub, html`<option value="">Choose a category first</option>`);
      return;
    }
    mount(sub, html`<option value="">Loading…</option>`);
    const { items } = await api(`/api/claims/categories/${encodeURIComponent(category.value)}`);
    mount(sub, html`<option value="">Choose…</option>${items.map((s) => html`<option>${s}</option>`)}`);
    sub.disabled = false;
  });

  amount.addEventListener('input', () => {
    const needed = parseFloat(amount.value) > 25;
    document.getElementById('receipt-hint').textContent = needed ? '(required above $25)' : '(optional up to $25)';
  });

  function clientErrors() {
    const errors = {};
    if (!category.value) errors.category = 'Choose a category.';
    else if (!sub.value) errors.subcategory = 'Choose a sub-category.';
    const value = parseFloat(amount.value);
    if (!/^\d+(\.\d{1,2})?$/.test(amount.value.trim()) || value <= 0 || value > 5000) errors.amount = 'Enter an amount between 0.01 and 5,000.';
    if (!form.claim_date.value) errors.claim_date = 'Pick the expense date.';
    if (form.description.value.trim().length < 5) errors.description = 'Description must be at least 5 characters.';
    const file = receipt.files[0];
    if (file && !/\.(pdf|png|jpe?g)$/i.test(file.name)) errors.receipt = 'Receipt must be a PDF, PNG or JPG file.';
    else if (file && file.size > 5 * 1024 * 1024) errors.receipt = 'Receipt must be 5 MB or smaller.';
    else if (!file && value > 25) errors.receipt = 'A receipt is required for claims above $25.00.';
    return errors;
  }

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const errors = clientErrors();
    showErrors(form, errors);
    if (Object.keys(errors).length) return;
    const button = form.querySelector('[type="submit"]');
    busy(button, true);
    try {
      const { id } = await api('/api/claims', { method: 'POST', form: new FormData(form) });
      flash('Claim submitted for approval.');
      location.href = `/claims/${id}`;
    } catch (err) {
      busy(button, false);
      showErrors(form, Object.keys(err.errors).length ? err.errors : { _: err.message });
    }
  });
})();
