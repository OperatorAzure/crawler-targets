# GoWork crawler targets: answer key

Three versions of the same HR portal ("GoWork"). They share the same features, data, roles and rules; only the web architecture differs. Use them to compare how well the crawler copes with each architecture.

| Site | URL | Architecture |
|---|---|---|
| Non-SPA | http://localhost:8001 | Flask. Every page is rendered on the server, all actions are plain HTML forms, and there is no JavaScript. |
| Hybrid | http://localhost:8002 | FastAPI + Jinja. The server renders the layout and detail pages; lists, the wizard, tabs and actions use JavaScript calls to `/api`. |
| Pure SPA | http://localhost:8003 | React + Vite bundles served by nginx. Everything is rendered in the browser. The JSON API is at `/api` (also directly on :8004). |

Machine-readable versions: [ground-truth/non-spa.json](ground-truth/non-spa.json), [ground-truth/hybrid.json](ground-truth/hybrid.json), [ground-truth/pure-spa.json](ground-truth/pure-spa.json), plus [ground-truth/concrete-urls.json](ground-truth/concrete-urls.json).

## Running

```bash
docker compose up -d --build        # all three sites
docker compose restart              # reset every site to the seed data
python ground-truth/generate.py --concrete   # rebuild the answer key (no Docker or packages needed)
```

- The database is rebuilt from the same seed every time a container starts, so each crawler run begins from the same state.
- Seed dates are relative to today **in Singapore time**; the containers run with `TZ=Asia/Singapore`. Regenerate `concrete-urls.json` on the day you run the crawler, and restart the containers that same day. Run the generator on a machine set to Singapore time, or use `TZ=Asia/Singapore` there too.
- Settings (in [docker-compose.yml](docker-compose.yml)):
  - `SESSION_IDLE_MINUTES` (default 30): idle session timeout on all sites.
  - `ACCESS_TOKEN_MINUTES` (default 10): lifetime of the SPA's access token.

## Test accounts

All 40 seeded users share the password `GoWork@2026`. Other usernames follow the pattern `first.last`; carol can see them all under **Users**.

| Username | Role | Notes |
|---|---|---|
| `alice` | employee | Reports to bob. Has 2 pages of leave and claims. |
| `bob` | manager | Engineering manager with 12 active direct reports. Sees **Approvals**. |
| `carol` | hr_admin | Sees **Approvals** for everyone and **Users** (user admin). |
| `li.tan` | manager | Finance manager. |
| `shu.nair` | employee | **Deactivated**, so sign-in must fail. |

## Registering a new account

Anyone can create an account at **`/register`**, linked as "Create an account" on the sign-in page.

- **Invite codes:** a valid employee ID / invite code is required. There are 10 codes, `GW-2026-0001` to `GW-2026-0010`. Case doesn't matter, and each code can be used any number of times.
- **Fields:**
  - full name, username, work email, password + confirm;
  - department, job title, and **Reports to** (which depends on the department: its manager(s) plus HR);
  - the invite code and an "I agree to the Terms & Privacy notice" checkbox (`/terms`).
- **Rules:** the same as HR's "Add user" form. The username and email must not already be in use.
- **Result:** an active **employee** account, signed in straight away. The user lands on the dashboard with a "Welcome to GoWork, …!" message. Signed-in users who open `/register` are sent to the dashboard.
- **How each site does it:**
  - **Non-SPA:** an HTML form POST with a CSRF token. A ⟳ button reloads the "Reports to" list.
  - **Hybrid and SPA:** `POST /api/auth/register` (JSON). They also check usernames live through `GET /api/auth/username-available?username=` and load managers from `GET /api/auth/register/managers?department=`.
  - **What comes back:** Hybrid sets the `gw_sid` cookie; the SPA returns tokens, the same as sign-in.
- **Resetting:** registered accounts disappear when the containers restart.

## What each role can reach

| Section | employee | manager | hr_admin |
|---|:-:|:-:|:-:|
| Dashboard, Leave, Claims, Directory, Team calendar, My profile, Help | ✓ | ✓ | ✓ |
| Other people's leave/claim detail pages | ✗ (404) | direct reports only | everyone |
| Approvals (`/admin/approvals`) | ✗ | team | everyone except self |
| Users (`/admin/users`, `/admin/users/new`, `/admin/users/{id}`) | ✗ | ✗ | ✓ |

How each site handles a page the user isn't allowed to see:
- **Non-SPA and Hybrid:** return a real **403**.
- **SPA:** returns **200**, then redirects to `/forbidden` in the browser. Its API returns 403.
- **Someone else's leave or claim:** **404** on every site, so the record's existence isn't revealed.

## Pages (all sites unless noted)

| Section | URLs |
|---|---|
| Public | `/login`, `/register`, `/terms`, `/help` (anchors `#leave #claims #password #approvals #privacy`) |
| Dashboard | `/dashboard`, `/announcements/{1-6}` |
| Leave | `/leave` (`status`, `type`, `sort`, `order`, `page`), `/leave/{id}`, `/leave/apply` |
| Claims | `/claims` (`status`, `category`, `sort`, `order`, `page`), `/claims/new`, `/claims/{id}` |
| People | `/directory` (`q`, `department`, `page`), `/directory/{id}`, `/calendar?month=YYYY-MM` |
| My profile | Non-SPA and SPA: `/profile`, `/profile/security`, `/profile/preferences`. Hybrid: `/profile#details`, `#security`, `#preferences` (tabs loaded by JavaScript). |
| Admin | `/admin/approvals`, `/admin/users`, `/admin/users/new`, `/admin/users/{id}` |

Pages that exist on only one or two sites:
- **Non-SPA only:**
  - `/leave/apply?step=1..3`: one URL per wizard step.
  - `/claims/{id}/receipt`: the receipt file.
  - `/profile/details`: a duplicate of `/profile`.
  - `/export-taxes`: the tax statement.
  - `/logout`.
- **Hybrid:** `/logout`, 12 JavaScript files under `/static/js/`, and receipts at `/api/claims/{id}/receipt`.
- **SPA:** `/forbidden`. Any unknown path returns 200 with "Page not found" drawn in the browser.

The **API** (Hybrid and SPA) has about 35 endpoints. The full list, with methods and roles, is in the JSON files. Highlights:
- `/api/dashboard`
- `/api/announcements`, which is deliberately slow (about 1.2 s)
- `/api/leave/validate`, used by the wizard
- `/api/claims/categories/{category}`, which feeds the dependent dropdown
- `/api/admin/*`

## Sign-in and sessions

| | Non-SPA | Hybrid | Pure SPA |
|---|---|---|---|
| Sign-in | HTML form `POST /login` | `fetch POST /api/auth/login` (JSON) | `fetch POST /api/auth/login` (JSON) |
| Credential | Signed cookie `gowork_session` | Server-side session, cookie `gw_sid` | Bearer JWT (10 min) + single-use refresh token (30 min) in `localStorage['gw_refresh']` |
| CSRF | Hidden `csrf_token` in every form (else 400) | `X-CSRF-Token` header from `<meta name="csrf-token">` (else 403) | None (no cookies) |
| Not signed in | 302 `/login?next=…` | Pages: 302 `/login?next=…`. API: 401 | Redirect in the browser to `/login?next=…`. API: 401 |
| Session expired | `/login?expired=1` | `/login?expired=1` | Tries one refresh, then `/login?expired=1` |
| Sign out | `GET /logout` link | `GET /logout` link | "Sign out" **button** |

## Crawler traps

| Trap | Where | What happens |
|---|---|---|
| **Tax export logs you out** | User menu (hover) → "Export tax statement". Non-SPA: a link to `/export-taxes`. Hybrid and SPA: a **button** that calls `GET /api/export-taxes` in the background. | Downloads a PDF and **ends the session**. The SPA revokes every token for that user. |
| **Infinite calendar** | `/calendar?month=` prev/next | Runs from 1000-01 to 9998-12 (about 107,000 pages), all 200. |
| **Endless "Next"** | Every paginated list | "Next" is never disabled. Pages past the end return 200 with an empty state (soft 404). |
| **Random URL tokens** | Announcement links `?ref=<random>`; Help links `?session_ref=<random>` | A new URL on every page render. |
| **Near-duplicates** | Sort, order and filter combinations; invalid `?month=` falls back to the current month; `/profile` = `/profile/details` (Non-SPA) | Many URLs, same content. |
| **Destructive actions** | Cancel leave, delete claim, approve/reject, deactivate user, change password, sign out, create account | Changes data or ends the session. Hybrid and SPA ask for confirmation in a modal first. |
| **Soft 404 / client-only 403** (SPA) | Unknown paths, or a role opening `/admin/*` | HTTP 200; the error only appears after JavaScript runs. |

## Content that needs JavaScript or interaction to find

| Behaviour | Non-SPA | Hybrid | SPA |
|---|---|---|---|
| Hover-only user menu | ✓ (links in HTML) | ✓ (includes a JS-only button) | ✓ (two buttons, no links) |
| Content loaded after the page loads | – | Dashboard tables, all lists, calendar, approvals | Everything |
| Slow content (~1.2 s) | – | Dashboard announcements | Dashboard announcements |
| Infinite scroll | – (numbered pages) | Directory | Directory |
| Navigation with no `<a href>` | – | Directory cards, leave rows (modal), pagination/sort buttons, receipt buttons | Directory cards, leave rows (modal), receipt buttons |
| Content that appears on click | – | Leave quick-view, reject reason, confirm dialogs, profile tabs | Same |
| Dependent dropdown | Server round-trip (⟳ button) | XHR | XHR |
| Multi-step wizard | One URL per step | One URL, steps switched by JS | One URL, steps switched by JS |
| Code-split bundles | – | – | One chunk per section (`/assets/<Section>-<hash>.js`) |

## Forms (the same fields on every site)

| Form | Fields and rules |
|---|---|
| Login | `username`, `password`, `remember` (ignored) |
| Register | `full_name`, `username`, `email`, `password`, `confirm_password`, `department` → `manager_id` (dependent), `job_title`, `invite_code` (`GW-2026-0001`…`0010`), `agree_terms` (required) |
| Leave wizard | (1) `leave_type`: Annual/Medical/Compassionate/Unpaid. (2) `start_date`, `end_date`: from today up to a year ahead, 1–30 working days, within the balance (Annual 18, Medical 14, Compassionate 3), no overlap. (3) `reason`: 5–500 characters. |
| New claim | `category` → `subcategory` (dependent); `amount` 0.01–5000 with 2 decimals; `claim_date` within the last 90 days; `description` 5–300 characters; `receipt` .pdf/.png/.jpg up to 5 MB, **required above $25** |
| Profile | `phone` (`+65 9123 4567` format), `location` (≤ 60), `bio` (≤ 300) |
| Password | `current_password`, `new_password` (≥ 10 characters, letters + digits), `confirm_password` |
| Preferences | Two checkboxes and `pref_language` (en/zh/ms/ta) |
| Approval decision | approve / reject + `comment` (required to reject) |
| User admin | `username` (create only), `temp_password` (create only), `full_name`, `email`, `department`, `job_title`, `role`, `manager_id` |

Text that users type is shown again on other pages:
- Leave reasons on the leave detail page and in Approvals.
- Claim descriptions on the claim page and in Approvals.
- Bios on profiles.

This is how the old "source-to-sink" check works now. The text is **always escaped**, so there is no XSS.

## Scoring with the answer key

- Check page and endpoint coverage against `pages` and `api_endpoints` in each site's JSON. Match `{id}` against any number.
- `concrete-urls.json` lists, for alice, bob and carol:
  - every leave, claim, profile and user ID their UI links to;
  - the real number of list pages;
  - a `core_page_urls` list.

  These lists leave out the infinite and random trap URLs. Use them to measure how complete the crawl is for each role.
- Good crawler behaviour (to measure):
  - stays inside the target hosts (the CDN font and CSS hosts are third-party);
  - stops on the calendar, "Next" and `?ref=` traps;
  - doesn't trigger the tax export or other destructive actions, or recovers by signing in again;
  - reaches JavaScript-only content on Hybrid and SPA.

## How this maps to your original requirements

| Earlier requirement | Now |
|---|---|
| Req 2 – Poison pill | `tax-export-logout` trap (link on Non-SPA; background request on Hybrid and SPA) |
| Req 3 – Privilege mapping | Three roles, checked on the server; admin pages return 403 (SPA: hidden in the browser + API 403) |
| Req 4 – Source-to-sink reflection | User text appears on detail, approval and profile pages, escaped |

## Code layout

- [shared/gowork_core/](shared/gowork_core/)
  - Data model, seed data and business rules, used by all three sites.
  - `api.py` is the JSON API shared by Hybrid and the SPA.
- [shared/static/gowork.css](shared/static/gowork.css): the shared theme on top of Bootstrap 5.3.
- [non-spa/](non-spa/), [hybrid/](hybrid/), [pure-spa/](pure-spa/): one folder per site.
  - Every Dockerfile builds from the repo root, so it can copy `shared/`.
