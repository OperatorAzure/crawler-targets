(async function () {
  const { api, html, mount, fdate, badge, avatar, empty, skeleton } = GW;
  const recentLeaves = document.getElementById('recent-leaves');
  const recentClaims = document.getElementById('recent-claims');
  [recentLeaves, recentClaims].forEach((el) => mount(el, skeleton(3)));

  // Announcements come from a deliberately slow endpoint (~1.2 s)
  api('/api/announcements?limit=5').then(({ items }) => {
    document.getElementById('ann-status').textContent = '';
    // Links carry a random ?ref= token on every render (crawler trap)
    const ref = () => Math.random().toString(16).slice(2, 10);
    mount(document.getElementById('announcement-list'), items.map((a) => html`
      <div class="gw-list-item">
        <div class="gw-stat-icon ${a.pinned ? 'amber' : ''}" style="width:36px;height:36px;font-size:1rem"><i class="bi bi-${a.pinned ? 'pin-angle' : 'megaphone'}"></i></div>
        <div><a class="fw-semibold d-block text-dark" href="/announcements/${a.id}?ref=${ref()}">${a.title}</a><div class="small text-muted">${fdate(a.created_at)}</div></div>
      </div>`));
  });

  const data = await api('/api/dashboard');
  mount(recentLeaves, data.recent_leaves.length ? html`
    <div class="table-responsive"><table class="table gw-table">
      <thead><tr><th>Type</th><th>Dates</th><th>Days</th><th>Status</th></tr></thead>
      <tbody>${data.recent_leaves.map((l) => html`<tr><td><a href="/leave/${l.id}">${l.leave_type}</a></td><td>${fdate(l.start_date)} – ${fdate(l.end_date)}</td><td>${l.days}</td><td>${badge(l.status)}</td></tr>`)}</tbody>
    </table></div>` : empty('calendar2-x', 'No leave requests yet'));

  mount(recentClaims, data.recent_claims.length ? html`
    <div class="table-responsive"><table class="table gw-table">
      <thead><tr><th>Claim</th><th>Date</th><th class="text-end">Amount</th><th>Status</th></tr></thead>
      <tbody>${data.recent_claims.map((c) => html`<tr><td><a href="/claims/${c.id}">${c.category} · ${c.subcategory}</a></td><td>${fdate(c.claim_date)}</td><td class="text-end">${c.amount}</td><td>${badge(c.status)}</td></tr>`)}</tbody>
    </table></div>` : empty('receipt', 'No claims yet'));

  mount(document.getElementById('out-today'), data.out_today.length ? data.out_today.map((p) => html`
    <div class="gw-list-item">${avatar(p, 'sm')}<div><a class="fw-semibold text-dark" href="/directory/${p.id}">${p.full_name}</a><div class="small text-muted">${p.leave_type} · back after ${fdate(p.end_date)}</div></div></div>`)
    : html`<div class="gw-card-body text-muted small">Everyone's in today.</div>`);

  const next = data.upcoming_leave;
  mount(document.getElementById('next-leave'), html`<div class="small text-muted mb-1">Your next approved leave</div>
    ${next ? html`<a class="fw-semibold" href="/leave/${next.id}">${next.leave_type} leave · ${fdate(next.start_date)}</a>`
    : html`<div class="fw-semibold">Nothing booked yet</div><a class="small" href="/leave/apply">Plan some time off →</a>`}`);
})();
