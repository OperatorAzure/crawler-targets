(function () {
  const { api, html, mount, avatar, badge, empty, skeleton, pagination, setQuery, query } = GW;
  const table = document.getElementById('user-table');
  const filters = document.getElementById('user-filters');
  const initial = { status: 'active', ...query() };
  ['q', 'role', 'status'].forEach((k) => { if (initial[k]) filters.elements[k].value = initial[k]; });
  let page = +initial.page || 1;

  async function load() {
    const params = { ...Object.fromEntries(new FormData(filters)), page };
    setQuery(params);
    mount(table, skeleton(6));
    const result = await api(`/api/admin/users?${new URLSearchParams(params)}`);
    document.getElementById('user-count').textContent = `${result.total} account(s).`;
    mount(table, result.items.length ? html`<div class="table-responsive"><table class="table gw-table">
      <thead><tr><th>Name</th><th>Username</th><th>Department</th><th>Role</th><th>Status</th><th></th></tr></thead>
      <tbody>${result.items.map((u) => html`<tr>
        <td><div class="d-flex gap-2 align-items-center">${avatar(u, 'sm')}<div><div class="fw-semibold">${u.full_name}</div><div class="small text-muted">${u.email}</div></div></div></td>
        <td class="text-muted">@${u.username}</td><td>${u.department}</td><td>${u.role_label}</td>
        <td>${badge(u.active ? 'Active' : 'Inactive')}</td>
        <td class="text-end"><a class="btn btn-sm btn-light" href="/admin/users/${u.id}">Edit</a></td></tr>`)}</tbody>
      </table></div>` : empty('person-x', 'No users on this page'));
    table.appendChild(pagination(result, (n) => { page = n; load(); }));
  }

  let timer;
  filters.addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(() => { page = 1; load(); }, 300); });
  filters.addEventListener('submit', (e) => { e.preventDefault(); page = 1; load(); });
  load();
})();
