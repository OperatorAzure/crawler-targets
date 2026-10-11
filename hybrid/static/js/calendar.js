(async function () {
  const { api, html, mount, skeleton } = GW;
  const grid = document.getElementById('cal-grid');
  mount(grid, skeleton(6));
  const month = new URLSearchParams(location.search).get('month') || '';
  const cal = await api(`/api/calendar?month=${encodeURIComponent(month)}`);

  document.getElementById('cal-label').textContent = cal.label;
  document.title = `${cal.label} · Team calendar · GoWork`;
  document.getElementById('cal-summary').textContent = `Approved leave across the company · ${cal.total} booking(s) in ${cal.label}.`;
  // prev/next links are generated here and never run out (crawler trap)
  mount(document.getElementById('cal-nav'), html`
    ${cal.prev ? html`<a class="btn btn-outline-secondary" href="/calendar?month=${cal.prev}" aria-label="Previous month"><i class="bi bi-chevron-left"></i></a>` : ''}
    <a class="btn btn-outline-secondary" href="/calendar">Today</a>
    ${cal.next ? html`<a class="btn btn-outline-secondary" href="/calendar?month=${cal.next}" aria-label="Next month"><i class="bi bi-chevron-right"></i></a>` : ''}`);

  mount(grid, html`<table class="gw-cal">
    <thead><tr>${['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'].map((d) => html`<th>${d}</th>`)}</tr></thead>
    <tbody>${cal.weeks.map((week) => html`<tr>${week.map((cell) => html`
      <td class="${cell.in_month ? '' : 'out'} ${cell.today ? 'today' : ''}">
        <div class="day">${cell.day}</div>
        ${cell.entries.slice(0, 3).map((e) => html`<a class="entry ${e.leave_type}" href="/directory/${e.user_id}" title="${e.name} · ${e.leave_type}">${e.name}</a>`)}
        ${cell.entries.length > 3 ? html`<span class="text-muted">+${cell.entries.length - 3} more</span>` : ''}
      </td>`)}</tr>`)}</tbody>
  </table>`);
})();
