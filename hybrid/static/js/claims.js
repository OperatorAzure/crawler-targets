(function () {
  const { api, html, mount, fdate, badge, empty, skeleton, pagination, setQuery, query, download, toast } = GW;
  const table = document.getElementById('claims-table');
  const fStatus = document.getElementById('f-status');
  const fCategory = document.getElementById('f-category');
  const state = { status: '', category: '', sort: 'claim_date', order: 'desc', page: 1, ...query() };
  state.page = +state.page || 1;
  fStatus.value = state.status;
  fCategory.value = state.category;

  const sortHead = (label, key, cls = '') => html`<th class="${cls}"><button class="btn btn-link p-0 text-reset text-decoration-none small fw-semibold text-uppercase" data-sort="${key}">${label}${state.sort === key ? html` <i class="bi bi-arrow-${state.order === 'desc' ? 'down' : 'up'}"></i>` : ''}</button></th>`;

  async function load() {
    setQuery(state);
    mount(table, skeleton(5));
    const result = await api(`/api/claims?${new URLSearchParams(state)}`);
    document.getElementById('claims-summary').textContent = `${result.total_amount} reimbursed to you this year.`;
    mount(table, result.items.length ? html`
      <div class="table-responsive"><table class="table gw-table">
        <thead><tr><th>#</th><th>Category</th><th>Description</th>${sortHead('Expense date', 'claim_date')}${sortHead('Amount', 'amount', 'text-end')}<th>Receipt</th>${sortHead('Status', 'status')}</tr></thead>
        <tbody>${result.items.map((c) => html`
          <tr>
            <td class="text-muted">${c.id}</td>
            <td><a class="fw-semibold" href="/claims/${c.id}">${c.category}</a><div class="small text-muted">${c.subcategory}</div></td>
            <td class="text-truncate" style="max-width:220px">${c.description}</td>
            <td>${fdate(c.claim_date)}</td><td class="text-end fw-semibold">${c.amount}</td>
            <td>${c.receipt_name ? html`<button class="btn btn-sm btn-link p-0" data-receipt="${c.id}" data-name="${c.receipt_name}" title="${c.receipt_name}"><i class="bi bi-paperclip"></i></button>` : html`<span class="text-muted">—</span>`}</td>
            <td>${badge(c.status)}</td>
          </tr>`)}</tbody>
      </table></div>` : empty('receipt', 'No claims on this page', 'Try another page or clear your filters.'));
    table.appendChild(pagination(result, (page) => { state.page = page; load(); }));
  }

  table.addEventListener('click', async (e) => {
    const sort = e.target.closest('[data-sort]');
    if (sort) {
      const key = sort.dataset.sort;
      state.order = state.sort === key && state.order === 'desc' ? 'asc' : 'desc';
      state.sort = key;
      state.page = 1;
      load();
      return;
    }
    // Receipts are fetched with XHR and saved as a blob - there is no plain link
    const receipt = e.target.closest('[data-receipt]');
    if (receipt) {
      try { download(await api(`/api/claims/${receipt.dataset.receipt}/receipt`), receipt.dataset.name); }
      catch (err) { toast(err.message, 'error'); }
    }
  });
  fStatus.addEventListener('change', () => { state.status = fStatus.value; state.page = 1; load(); });
  fCategory.addEventListener('change', () => { state.category = fCategory.value; state.page = 1; load(); });
  load();
})();
