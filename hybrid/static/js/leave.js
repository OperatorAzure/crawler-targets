(function () {
  const { api, html, mount, fdate, badge, empty, skeleton, pagination, modal, setQuery, query } = GW;
  const table = document.getElementById('leave-table');
  const fStatus = document.getElementById('f-status');
  const fType = document.getElementById('f-type');
  const state = { status: '', type: '', sort: 'start_date', order: 'desc', page: 1, ...query() };
  state.page = +state.page || 1;
  fStatus.value = state.status;
  fType.value = state.type;

  const sortHead = (label, key) => html`<th><button class="btn btn-link p-0 text-reset text-decoration-none small fw-semibold text-uppercase" data-sort="${key}">${label}${state.sort === key ? html` <i class="bi bi-arrow-${state.order === 'desc' ? 'down' : 'up'}"></i>` : ''}</button></th>`;

  async function load() {
    setQuery(state);
    mount(table, skeleton(5));
    const result = await api(`/api/leave?${new URLSearchParams(state)}`);
    mount(table, result.items.length ? html`
      <div class="table-responsive"><table class="table gw-table">
        <thead><tr><th>#</th><th>Type</th>${sortHead('Dates', 'start_date')}${sortHead('Days', 'days')}<th>Reason</th>${sortHead('Status', 'status')}${sortHead('Submitted', 'created_at')}</tr></thead>
        <tbody>${result.items.map((l) => html`
          <tr data-id="${l.id}" style="cursor:pointer">
            <td class="text-muted">${l.id}</td><td class="fw-semibold text-brand">${l.leave_type}</td>
            <td>${fdate(l.start_date)} – ${fdate(l.end_date)}</td><td>${l.days}</td>
            <td class="text-truncate" style="max-width:240px">${l.reason}</td><td>${badge(l.status)}</td>
            <td class="text-muted small">${fdate(l.created_at)}</td>
          </tr>`)}</tbody>
      </table></div>` : empty('calendar2-x', 'No leave requests on this page', 'Try another page or clear your filters.'));
    table.appendChild(pagination(result, (page) => { state.page = page; load(); }));
  }

  // Quick-view modal: the full detail page is only linked from inside the modal
  async function preview(id) {
    const m = modal({ title: `Leave request #${id}`, body: skeleton(4) });
    const l = await api(`/api/leave/${id}`);
    mount(m.body, html`
      <div class="mb-3">${badge(l.status)}</div>
      <dl class="gw-dl" style="grid-template-columns: 120px 1fr">
        <dt>Type</dt><dd>${l.leave_type}</dd>
        <dt>Dates</dt><dd>${fdate(l.start_date)} – ${fdate(l.end_date)}</dd>
        <dt>Days</dt><dd>${l.days}</dd>
        <dt>Reason</dt><dd>${l.reason}</dd>
        ${l.approver_name ? html`<dt>Decided by</dt><dd>${l.approver_name}</dd>` : ''}
      </dl>
      <a class="btn btn-sm btn-outline-primary mt-3" href="/leave/${l.id}">Open full request <i class="bi bi-arrow-right"></i></a>`);
  }

  table.addEventListener('click', (e) => {
    const sort = e.target.closest('[data-sort]');
    if (sort) {
      const key = sort.dataset.sort;
      state.order = state.sort === key && state.order === 'desc' ? 'asc' : 'desc';
      state.sort = key;
      state.page = 1;
      load();
      return;
    }
    const row = e.target.closest('tr[data-id]');
    if (row) preview(row.dataset.id);
  });
  fStatus.addEventListener('change', () => { state.status = fStatus.value; state.page = 1; load(); });
  fType.addEventListener('change', () => { state.type = fType.value; state.page = 1; load(); });
  load();
})();
