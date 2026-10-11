(function () {
  const { api, html, mount, fdate, empty, skeleton, modal, toast, showErrors, busy } = GW;
  const leaveBox = document.getElementById('leave-approvals');
  const claimBox = document.getElementById('claim-approvals');

  const actions = (kind, id) => html`<div class="d-flex gap-2">
    <button class="btn btn-sm btn-success" data-kind="${kind}" data-id="${id}" data-act="approve"><i class="bi bi-check-lg"></i> Approve</button>
    <button class="btn btn-sm btn-outline-danger" data-kind="${kind}" data-id="${id}" data-act="reject"><i class="bi bi-x-lg"></i> Reject</button>
  </div>`;

  async function load() {
    mount(leaveBox, skeleton(3));
    mount(claimBox, skeleton(3));
    const data = await api('/api/admin/approvals');
    document.getElementById('leave-count').textContent = data.leaves.length;
    document.getElementById('claim-count').textContent = data.claims.length;
    mount(leaveBox, data.leaves.length ? html`<div class="table-responsive"><table class="table gw-table">
      <thead><tr><th>Employee</th><th>Type</th><th>Dates</th><th>Days</th><th>Reason</th><th></th></tr></thead>
      <tbody>${data.leaves.map((l) => html`<tr>
        <td><a class="fw-semibold" href="/directory/${l.user_id}">${l.owner_name}</a></td><td><a href="/leave/${l.id}">${l.leave_type}</a></td>
        <td class="text-nowrap">${fdate(l.start_date)} – ${fdate(l.end_date)}</td><td>${l.days}</td>
        <td class="text-truncate" style="max-width:200px">${l.reason}</td><td>${actions('leave', l.id)}</td></tr>`)}</tbody>
      </table></div>` : empty('check2-all', 'All caught up', 'No leave requests waiting for you.'));
    mount(claimBox, data.claims.length ? html`<div class="table-responsive"><table class="table gw-table">
      <thead><tr><th>Employee</th><th>Claim</th><th>Date</th><th class="text-end">Amount</th><th></th></tr></thead>
      <tbody>${data.claims.map((c) => html`<tr>
        <td><a class="fw-semibold" href="/directory/${c.user_id}">${c.owner_name}</a></td>
        <td><a href="/claims/${c.id}">${c.category}</a><div class="small text-muted text-truncate" style="max-width:220px">${c.description}</div></td>
        <td class="text-nowrap">${fdate(c.claim_date)}</td><td class="text-end fw-semibold">${c.amount}</td><td>${actions('claim', c.id)}</td></tr>`)}</tbody>
      </table></div>` : empty('check2-all', 'All caught up', 'No claims waiting for you.'));
  }

  async function decide(kind, id, action, comment = '') {
    await api(`/api/admin/approvals/${kind}/${id}`, { method: 'POST', body: { action, comment } });
    toast(`${kind === 'leave' ? 'Leave' : 'Claim'} #${id} ${action === 'approve' ? 'approved' : 'rejected'}.`);
    load();
  }

  document.addEventListener('click', async (e) => {
    const btn = e.target.closest('[data-act]');
    if (!btn) return;
    const { kind, id, act } = btn.dataset;
    if (act === 'approve') {
      busy(btn, true);
      try { await decide(kind, id, 'approve'); } catch (err) { toast(err.message, 'error'); busy(btn, false); }
      return;
    }
    // Rejecting needs a reason, collected in a modal
    const m = modal({
      title: `Reject ${kind} #${id}`,
      body: html`<form id="reject-form"><label class="form-label" for="comment">Reason for rejecting</label>
        <textarea class="form-control" id="comment" name="comment" rows="3" maxlength="300" placeholder="Visible to the employee"></textarea></form>`,
      footer: html`<button class="btn btn-light" data-close>Cancel</button><button class="btn btn-danger" form="reject-form">Reject</button>`,
    });
    m.el.querySelector('form').addEventListener('submit', async (ev) => {
      ev.preventDefault();
      try { await decide(kind, id, 'reject', ev.target.comment.value); m.close(); }
      catch (err) { showErrors(ev.target, err.errors || { _: err.message }); }
    });
  });
  load();
})();
