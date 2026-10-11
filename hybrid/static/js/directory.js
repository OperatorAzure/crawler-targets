(function () {
  const { api, html, mount, avatar, empty } = GW;
  const grid = document.getElementById('people');
  const sentinel = document.getElementById('sentinel');
  const filters = document.getElementById('dir-filters');
  let page = 1;
  let pages = +grid.dataset.pages;
  let loading = false;

  const card = (p) => html`<div class="col-sm-6 col-lg-4 col-xl-3">
    <div class="gw-card gw-person" data-href="/directory/${p.id}" role="link" tabindex="0">
      ${avatar(p)}<div class="fw-semibold">${p.full_name}</div><div class="small text-muted">${p.job_title}</div>
      <span class="gw-chip mt-2">${p.department}</span>
    </div></div>`;

  const params = () => new URLSearchParams(new FormData(filters));

  async function loadPage(n, replace = false) {
    loading = true;
    sentinel.textContent = 'Loading…';
    const qs = params();
    qs.set('page', n);
    const result = await api(`/api/directory?${qs}`);
    page = result.page;
    pages = result.pages;
    const content = result.items.map(card);
    if (replace) {
      mount(grid, result.items.length ? content : html`<div class="col-12"><div class="gw-card">${empty('people', 'Nobody found', 'Try a different name or department.')}</div></div>`);
      document.getElementById('dir-count').textContent = `${result.total} colleague(s)${result.q ? ` matching “${result.q}”` : ''}.`;
    } else {
      grid.insertAdjacentHTML('beforeend', content.map((c) => c.h).join(''));
    }
    sentinel.textContent = page < pages ? 'Scroll for more' : "That's everyone.";
    loading = false;
  }

  // Infinite scroll
  new IntersectionObserver((entries) => {
    if (entries[0].isIntersecting && !loading && page < pages) loadPage(page + 1);
  }, { rootMargin: '200px' }).observe(sentinel);

  // Live search (debounced); keeps the URL shareable
  let timer;
  filters.addEventListener('input', () => {
    clearTimeout(timer);
    timer = setTimeout(() => {
      GW.setQuery(Object.fromEntries(params()));
      loadPage(1, true);
    }, 300);
  });
  filters.addEventListener('submit', (e) => { e.preventDefault(); loadPage(1, true); });

  // Cards navigate with JavaScript only
  const go = (e) => {
    const el = e.target.closest('[data-href]');
    if (el && (e.type === 'click' || e.key === 'Enter')) location.href = el.dataset.href;
  };
  grid.addEventListener('click', go);
  grid.addEventListener('keydown', go);
})();
