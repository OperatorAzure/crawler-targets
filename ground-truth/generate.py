"""Builds the crawler answer key for the three GoWork targets.

    python ground-truth/generate.py              # rewrite non-spa.json, hybrid.json, pure-spa.json
    python ground-truth/generate.py --concrete   # also write concrete-urls.json (needs no Docker)

The JSON files describe *what exists* (URL patterns, API endpoints, forms,
roles, traps, dynamic behaviour). `--concrete` re-creates the seed database
in a temp folder and expands those patterns into the exact URLs each test
account can reach today. The seed depends on today's date, so compare
against containers that were (re)started today.
"""

import json
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROLES_ALL = ["employee", "manager", "hr_admin"]
MANAGERS = ["manager", "hr_admin"]
HR = ["hr_admin"]

ACCOUNTS = [
    {"username": "alice", "password": "GoWork@2026", "role": "employee", "user_id": 3,
     "notes": "Software Engineer, reports to bob. Has 2 pages of leave and claims."},
    {"username": "bob", "password": "GoWork@2026", "role": "manager", "user_id": 2,
     "notes": "Engineering Manager with 12 active direct reports."},
    {"username": "carol", "password": "GoWork@2026", "role": "hr_admin", "user_id": 1,
     "notes": "HR Director. Sees every pending request and the user admin."},
    {"username": "li.tan", "password": "GoWork@2026", "role": "manager", "user_id": 4, "notes": "Finance manager."},
    {"username": "shu.nair", "password": "GoWork@2026", "role": "employee", "user_id": 15,
     "notes": "Deactivated account - login must fail."},
]
SEED = {"users": 40, "active_users": 38, "announcements": 6,
        "notes": "All seeded users share the password GoWork@2026. Leave/claim counts vary slightly with today's date."}

# --- forms (fields are the same on every site; only the transport differs) -------------------------

F_LOGIN = [
    {"name": "username", "type": "text", "required": True},
    {"name": "password", "type": "password", "required": True},
    {"name": "remember", "type": "checkbox", "required": False, "notes": "Ignored by the server."},
]
F_LEAVE = [
    {"name": "leave_type", "type": "radio", "step": 1, "options": ["Annual", "Medical", "Compassionate", "Unpaid"]},
    {"name": "start_date", "type": "date", "step": 2, "rules": "today <= start <= today+365"},
    {"name": "end_date", "type": "date", "step": 2,
     "rules": "end >= start; 1-30 working days; within yearly balance (Annual 18, Medical 14, Compassionate 3); no overlap with own pending/approved leave"},
    {"name": "reason", "type": "textarea", "step": 3, "rules": "5-500 chars"},
]
F_CLAIM = [
    {"name": "category", "type": "select", "options": ["Travel", "Meals", "Medical", "Training", "Equipment"]},
    {"name": "subcategory", "type": "select", "depends_on": "category",
     "options": {"Travel": ["Taxi / ride-hailing", "Flight", "Hotel", "Mileage"],
                 "Meals": ["Client entertainment", "Overtime meal"], "Medical": ["GP visit", "Dental", "Specialist"],
                 "Training": ["Course fee", "Books", "Exam fee"],
                 "Equipment": ["Hardware", "Software", "Office supplies"]}},
    {"name": "amount", "type": "number", "rules": "0.01-5000.00, max 2 decimals"},
    {"name": "claim_date", "type": "date", "rules": "today-90 <= date <= today"},
    {"name": "description", "type": "textarea", "rules": "5-300 chars"},
    {"name": "receipt", "type": "file", "rules": ".pdf/.png/.jpg/.jpeg, <= 5 MB, required when amount > 25"},
]
F_PROFILE = [
    {"name": "phone", "type": "tel", "rules": r"^\+?[0-9 ]{8,16}$"},
    {"name": "location", "type": "text", "rules": "<= 60 chars (datalist suggestions)"},
    {"name": "bio", "type": "textarea", "rules": "<= 300 chars"},
]
F_PASSWORD = [
    {"name": "current_password", "type": "password"},
    {"name": "new_password", "type": "password", "rules": ">= 10 chars, letters and digits, differs from current"},
    {"name": "confirm_password", "type": "password", "rules": "matches new_password"},
]
F_PREFS = [
    {"name": "pref_email_notifications", "type": "checkbox"},
    {"name": "pref_weekly_digest", "type": "checkbox"},
    {"name": "pref_language", "type": "select", "options": ["en", "zh", "ms", "ta"]},
]
F_DECISION = [
    {"name": "action", "type": "submit/button", "options": ["approve", "reject"]},
    {"name": "comment", "type": "text/textarea", "rules": "required (3-300 chars) when rejecting"},
]
F_USER = [
    {"name": "username", "type": "text", "create_only": True, "rules": "^[a-z][a-z0-9._]{2,19}$, unique"},
    {"name": "temp_password", "type": "password", "create_only": True, "rules": ">= 10 chars, letters and digits"},
    {"name": "full_name", "type": "text", "rules": "2-60 chars"},
    {"name": "email", "type": "email"},
    {"name": "department", "type": "select",
     "options": ["Engineering", "Finance", "Human Resources", "Marketing", "Sales", "Operations"]},
    {"name": "job_title", "type": "text", "rules": "2-60 chars"},
    {"name": "role", "type": "select", "options": ["employee", "manager", "hr_admin"]},
    {"name": "manager_id", "type": "select", "rules": "empty or an active manager/HR admin"},
]
F_SEARCH = [{"name": "q", "type": "search"}]
INVITE_CODES = [f"GW-2026-{n:04d}" for n in range(1, 11)]
F_REGISTER = [
    {"name": "full_name", "type": "text", "rules": "2-60 chars"},
    {"name": "username", "type": "text", "rules": "^[a-z][a-z0-9._]{2,19}$ (case-folded), unique"},
    {"name": "email", "type": "email", "rules": "valid, not already used by another account"},
    {"name": "password", "type": "password", "rules": ">= 10 chars, letters and digits"},
    {"name": "confirm_password", "type": "password", "rules": "matches password"},
    {"name": "department", "type": "select",
     "options": ["Engineering", "Finance", "Human Resources", "Marketing", "Sales", "Operations"]},
    {"name": "job_title", "type": "text", "rules": "2-60 chars"},
    {"name": "manager_id", "type": "select", "depends_on": "department",
     "rules": "required; the department's manager(s) or an HR admin"},
    {"name": "invite_code", "type": "text", "rules": "one of invite_codes (case-insensitive, reusable)"},
    {"name": "agree_terms", "type": "checkbox", "rules": "must be ticked"},
]
REGISTRATION = {
    "page": "/register (linked from the sign-in page as 'Create an account')",
    "result": "Creates an active *employee* account and signs the new user in immediately (lands on /dashboard with a welcome message).",
    "invite_codes": INVITE_CODES,
    "notes": "Registered accounts disappear when the containers restart. Signed-in users opening /register are sent to /dashboard.",
}


def page(path, roles=None, query=None, auth=True, kind="html", notes="", **extra):
    return {"path": path, "roles": roles or (ROLES_ALL if auth else ["anonymous"]), "auth_required": auth,
            "query_params": query or [], "content": kind, "notes": notes, **extra}


def api(method, path, roles=None, notes="", **extra):
    return {"method": method, "path": path, "roles": roles or ROLES_ALL, "notes": notes, **extra}


# Shared JSON API (hybrid: cookie + CSRF header, SPA: bearer token)
SHARED_API = [
    api("GET", "/api/meta"),
    api("GET", "/api/me"),
    api("PUT", "/api/me/profile", body="profile form"),
    api("PUT", "/api/me/password", body="password form"),
    api("PUT", "/api/me/preferences", body="preferences form"),
    api("GET", "/api/dashboard"),
    api("GET", "/api/announcements", query=["limit"], notes="Deliberately slow: ~1.2 s server delay."),
    api("GET", "/api/announcements/{id}", ids="1-6"),
    api("GET", "/api/leave", query=["status", "type", "sort", "order", "page"]),
    api("GET", "/api/leave/balances"),
    api("POST", "/api/leave/validate", body="leave form + step (1-3)"),
    api("POST", "/api/leave", body="leave form", status=201),
    api("GET", "/api/leave/{id}", notes="Own leave; managers: direct reports; HR: everyone. Others get 404."),
    api("POST", "/api/leave/{id}/cancel", destructive=True),
    api("GET", "/api/claims", query=["status", "category", "sort", "order", "page"]),
    api("GET", "/api/claims/categories"),
    api("GET", "/api/claims/categories/{category}", notes="Dependent dropdown source; unknown category -> 404."),
    api("POST", "/api/claims", body="multipart claim form", status=201),
    api("GET", "/api/claims/{id}", notes="Same visibility rules as leave."),
    api("GET", "/api/claims/{id}/receipt", content="file (pdf/png/jpg)"),
    api("DELETE", "/api/claims/{id}", destructive=True, notes="Own pending claims only."),
    api("GET", "/api/directory", query=["q", "department", "page"]),
    api("GET", "/api/directory/{id}", notes="Active users only."),
    api("GET", "/api/calendar", query=["month"]),
    api("GET", "/api/admin/approvals", roles=MANAGERS),
    api("POST", "/api/admin/approvals/{kind}/{id}", roles=MANAGERS, kind=["leave", "claim"], body="decision form",
        destructive=True),
    api("GET", "/api/admin/users", roles=HR, query=["q", "role", "status", "page"]),
    api("GET", "/api/admin/managers", roles=HR),
    api("POST", "/api/admin/users", roles=HR, body="user form", status=201),
    api("GET", "/api/admin/users/{id}", roles=HR),
    api("PUT", "/api/admin/users/{id}", roles=HR, body="user form (edit)"),
    api("POST", "/api/admin/users/{id}/status", roles=HR, body='{"active": bool}', destructive=True),
]

PUBLIC_REGISTER_API = [
    api("POST", "/api/auth/register", roles=["anonymous"], body="registration form (JSON)", status=201),
    api("GET", "/api/auth/username-available", roles=["anonymous"], query=["username"],
        notes="Live check used while typing; returns {username, available, message}."),
    api("GET", "/api/auth/register/managers", roles=["anonymous"], query=["department"],
        notes="Options for 'Reports to'; unknown department -> empty list."),
]
COMMON_TRAPS = [
    {"id": "tax-export-logout", "type": "session-killer",
     "effect": "Downloading the tax statement ends the session; every request afterwards is unauthenticated."},
    {"id": "infinite-calendar", "type": "infinite-space",
     "trigger": "Team calendar prev/next month links (/calendar?month=YYYY-MM)",
     "effect": "Months run from 1000-01 to 9998-12 (~107,000 distinct pages), each returning 200."},
    {"id": "endless-next-page", "type": "infinite-space",
     "trigger": "'Next' on every paginated list is never disabled",
     "effect": "page=N+1 forever; pages past the end return 200 with an empty-state message (soft 404)."},
    {"id": "random-ref-params", "type": "unique-url-per-visit",
     "trigger": "Announcement links carry ?ref=<random hex>; Help centre links carry ?session_ref=<random hex>",
     "effect": "A new URL on every page render for the same content."},
    {"id": "near-duplicates", "type": "duplicate-content",
     "trigger": "sort/order/status/type/category/department/q combinations on list pages; invalid ?month= falls back to the current month",
     "effect": "Many URLs, same or overlapping content."},
    {"id": "destructive-actions", "type": "state-changing",
     "trigger": "Cancel leave, delete claim, approve/reject, deactivate user, change password, sign out, create account (/register)",
     "effect": "Following them changes data or ends the session."},
]


def non_spa():
    return {
        "site": "non-spa",
        "base_url": "http://localhost:8001",
        "architecture": "Flask, every page rendered on the server, plain HTML forms, no JavaScript.",
        "auth": {
            "login": {"url": "/login", "method": "POST", "content_type": "application/x-www-form-urlencoded",
                      "fields": ["csrf_token (hidden)", "next (hidden)", "username", "password", "remember"],
                      "success": "302 to ?next (same-site paths only) or /dashboard", "failure": "401 + form again"},
            "session": {"type": "signed cookie", "cookie": "gowork_session", "http_only": True, "same_site": "Lax",
                        "idle_timeout_minutes": 30, "on_expiry": "302 /login?expired=1"},
            "unauthenticated": "302 /login?next=<original path>",
            "csrf": "Hidden csrf_token field in every POST form (tied to the session). Missing/wrong -> 400.",
            "logout": "GET /logout (link in the user menu) -> 302 /login",
        },
        "accounts": ACCOUNTS,
        "registration": REGISTRATION,
        "seed": SEED,
        "pages": [
            page("/", auth=False, kind="redirect", notes="302 to /dashboard or /login"),
            page("/login", auth=False),
            page("/register", auth=False, notes="Public sign-up; signed-in users are redirected to /dashboard."),
            page("/terms", auth=False, fragments=["use", "accounts", "data", "retention", "contact"]),
            page("/help", auth=False, query=["session_ref"], fragments=["leave", "claims", "password", "approvals", "privacy"]),
            page("/dashboard"),
            page("/announcements/{id}", query=["ref"], ids="1-6"),
            page("/leave", query=["status", "type", "sort", "order", "page"]),
            page("/leave/{id}", notes="Own leave; managers: direct reports; HR: everyone. Others get 404."),
            page("/leave/apply", query=["step", "reset"], notes="3-step wizard; draft kept in the session. Can't skip ahead."),
            page("/claims", query=["status", "category", "sort", "order", "page"]),
            page("/claims/new", query=["category"]),
            page("/claims/{id}"),
            page("/claims/{id}/receipt", kind="file (pdf/png/jpg)"),
            page("/directory", query=["q", "department", "page"]),
            page("/directory/{id}", notes="Active users only."),
            page("/calendar", query=["month"]),
            page("/profile"),
            page("/profile/details", notes="Duplicate of /profile."),
            page("/profile/security"),
            page("/profile/preferences"),
            page("/export-taxes", query=["year"], kind="file (pdf)", trap="tax-export-logout"),
            page("/logout", kind="redirect", destructive=True),
            page("/admin/approvals", roles=MANAGERS),
            page("/admin/users", roles=HR, query=["q", "role", "status", "page"]),
            page("/admin/users/new", roles=HR),
            page("/admin/users/{id}", roles=HR),
        ],
        "api_endpoints": [],
        "forms": [
            {"id": "login", "page": "/login", "action": "POST /login", "fields": F_LOGIN},
            {"id": "register", "page": "/register", "action": "POST /register", "auth_required": False,
             "fields": F_REGISTER + [{"name": "action", "type": "submit", "options": ["refresh", "submit"]},
                                     {"name": "csrf_token", "type": "hidden"}],
             "notes": "No JavaScript: the 'refresh' button posts the form back so the server fills in 'Reports to'. HTML5 required/pattern attributes. Success -> 302 /dashboard, signed in."},
            {"id": "topbar-search", "page": "(every page)", "action": "GET /directory", "fields": F_SEARCH},
            {"id": "leave-filters", "page": "/leave", "action": "GET /leave", "fields": ["status", "type", "sort (hidden)", "order (hidden)"]},
            {"id": "leave-wizard", "page": "/leave/apply", "action": "POST /leave/apply (hidden step=1|2|3)", "fields": F_LEAVE,
             "notes": "Each step is its own POST + redirect. Fields also have HTML5 validation."},
            {"id": "leave-cancel", "page": "/leave/{id}", "action": "POST /leave/{id}/cancel", "fields": [], "destructive": True},
            {"id": "claim-filters", "page": "/claims", "action": "GET /claims", "fields": ["status", "category", "sort (hidden)", "order (hidden)"]},
            {"id": "claim-new", "page": "/claims/new", "action": "POST /claims/new", "enctype": "multipart/form-data",
             "fields": F_CLAIM + [{"name": "action", "type": "submit", "options": ["refresh", "submit"]}],
             "notes": "No JavaScript: the 'refresh' button posts the form back so the server fills in the sub-categories."},
            {"id": "claim-delete", "page": "/claims/{id}", "action": "POST /claims/{id}/delete", "fields": [], "destructive": True},
            {"id": "directory-search", "page": "/directory", "action": "GET /directory", "fields": ["q", "department"]},
            {"id": "profile-details", "page": "/profile", "action": "POST /profile", "fields": F_PROFILE},
            {"id": "profile-password", "page": "/profile/security", "action": "POST /profile/security", "fields": F_PASSWORD, "destructive": True},
            {"id": "profile-preferences", "page": "/profile/preferences", "action": "POST /profile/preferences", "fields": F_PREFS},
            {"id": "approval-decision", "page": "/admin/approvals", "action": "POST /admin/approvals/{leave|claim}/{id}",
             "fields": F_DECISION, "roles": MANAGERS, "destructive": True, "notes": "One small form per table row."},
            {"id": "user-filters", "page": "/admin/users", "action": "GET /admin/users", "fields": ["q", "role", "status"], "roles": HR},
            {"id": "user-create", "page": "/admin/users/new", "action": "POST /admin/users/new", "fields": F_USER, "roles": HR},
            {"id": "user-edit", "page": "/admin/users/{id}", "action": "POST /admin/users/{id}", "fields": F_USER[2:], "roles": HR},
            {"id": "user-status", "page": "/admin/users/{id}", "action": "POST /admin/users/{id}/status",
             "fields": [{"name": "active", "type": "hidden", "options": ["0", "1"]}], "roles": HR, "destructive": True},
        ],
        "role_restricted": [
            {"path": "/admin/approvals", "roles": MANAGERS, "others_get": "403 page", "nav_link_hidden_for_others": True},
            {"path": "/admin/users*", "roles": HR, "others_get": "403 page", "nav_link_hidden_for_others": True},
            {"path": "/leave/{id}, /claims/{id}, /claims/{id}/receipt", "roles": "owner, owner's manager, hr_admin",
             "others_get": "404 page (existence not revealed)"},
        ],
        "traps": [
            {**COMMON_TRAPS[0], "trigger": "GET /export-taxes?year=2025 - link inside the CSS hover user menu",
             "response": "200 application/pdf attachment + session cookie cleared"},
            *COMMON_TRAPS[1:],
            {"id": "logout-link", "type": "session-killer", "trigger": "GET /logout in the user menu", "effect": "Ends the session."},
            {"id": "profile-alias", "type": "duplicate-content", "trigger": "/profile and /profile/details", "effect": "Same page, two URLs."},
        ],
        "dynamic_content": [
            {"where": "user menu", "how": "CSS :hover / :focus-within. The links are in the HTML source, just hidden."},
            {"where": "/claims/new", "how": "Sub-category list filled in by a server round-trip (the refresh button), not by JavaScript."},
            {"where": "/register", "how": "'Reports to' list filled in by a server round-trip (the refresh button)."},
        ],
        "static_assets": ["/static/gowork.css"],
        "external_resources": ["fonts.googleapis.com / fonts.gstatic.com (Inter)", "cdn.jsdelivr.net (Bootstrap 5.3.3 CSS, Bootstrap Icons 1.11.3)"],
        "error_behaviour": {"unknown_url": "404 HTML page", "forbidden": "403 HTML page", "bad_csrf": "400 HTML page",
                            "upload_too_large": "413 HTML page (> 6 MB request)"},
    }


def hybrid():
    return {
        "site": "hybrid",
        "base_url": "http://localhost:8002",
        "architecture": "FastAPI + Jinja: layout, detail pages and the first directory page are rendered on the server; lists, the wizard, tabs and actions run in JavaScript against /api.",
        "auth": {
            "login": {"url": "/login (page)", "submits": "fetch POST /api/auth/login", "content_type": "application/json",
                      "fields": ["username", "password", "next", "remember"],
                      "success": "200 {status, next} + Set-Cookie gw_sid; the page then goes to `next`",
                      "failure": "401 {detail}"},
            "session": {"type": "server-side, in memory", "cookie": "gw_sid", "http_only": True, "same_site": "Lax",
                        "idle_timeout_minutes": 30},
            "unauthenticated": "Pages: 302 /login?next=<path>[&expired=1]. API: 401 JSON; common.js then goes to /login?expired=1&next=...",
            "csrf": "<meta name=\"csrf-token\"> on every page; POST/PUT/DELETE to /api/* must send it as X-CSRF-Token (403 otherwise). /api/auth/login is exempt.",
            "logout": "GET /logout link -> 302 /login?signed_out=1 (also POST /api/auth/logout)",
        },
        "accounts": ACCOUNTS,
        "registration": REGISTRATION,
        "seed": SEED,
        "pages": [
            page("/", auth=False, kind="redirect"),
            page("/login", auth=False, query=["next", "expired", "signed_out"]),
            page("/register", auth=False, notes="Rendered on the server, submitted by register.js; signed-in users are redirected to /dashboard."),
            page("/terms", auth=False, fragments=["use", "accounts", "data", "retention", "contact"]),
            page("/help", auth=False, fragments=["leave", "claims", "password", "approvals", "privacy"], query=["session_ref"]),
            page("/dashboard", notes="Stat cards rendered on the server; tables and announcements loaded by JavaScript."),
            page("/announcements/{id}", query=["ref"], ids="1-6"),
            page("/leave", query=["status", "type", "sort", "order", "page"], notes="Table is built by JavaScript; query string updated with history.replaceState."),
            page("/leave/apply", notes="Wizard is one page; steps switch in JavaScript."),
            page("/leave/{id}", notes="Rendered on the server. Only linked from the quick-view modal, dashboard and approvals."),
            page("/claims", query=["status", "category", "sort", "order", "page"]),
            page("/claims/new"),
            page("/claims/{id}"),
            page("/directory", query=["q", "department"], notes="Page 1 rendered on the server; more pages added by infinite scroll."),
            page("/directory/{id}", notes="Directory cards are <div data-href> with click handlers (no <a>). Also linked from calendar, approvals, profiles."),
            page("/calendar", query=["month"], notes="Grid and prev/next links built by JavaScript."),
            page("/profile", fragments=["details", "security", "preferences"], notes="Tabs are <button>s; each panel is fetched when first opened."),
            page("/logout", kind="redirect", destructive=True),
            page("/admin/approvals", roles=MANAGERS),
            page("/admin/users", roles=HR, query=["q", "role", "status", "page"]),
            page("/admin/users/new", roles=HR),
            page("/admin/users/{id}", roles=HR),
        ],
        "api_endpoints": [
            api("POST", "/api/auth/login", roles=["anonymous"]),
            *PUBLIC_REGISTER_API,
            api("POST", "/api/auth/logout", destructive=True),
            api("GET", "/api/export-taxes", query=["year"], content="file (pdf)", trap="tax-export-logout"),
            *SHARED_API,
        ],
        "forms": [
            {"id": "login", "page": "/login", "action": "fetch POST /api/auth/login (JSON)", "fields": F_LOGIN},
            {"id": "register", "page": "/register", "action": "fetch POST /api/auth/register (JSON)", "auth_required": False,
             "fields": F_REGISTER, "notes": "Checked in the browser first. Success -> 201 + gw_sid cookie, then the page goes to /dashboard."},
            {"id": "topbar-search", "page": "(every page)", "action": "GET /directory", "fields": F_SEARCH, "transport": "html-form"},
            {"id": "leave-filters", "page": "/leave", "action": "GET /api/leave on <select> change", "fields": ["status", "type"], "transport": "fetch"},
            {"id": "leave-wizard", "page": "/leave/apply", "action": "POST /api/leave/validate per step, then POST /api/leave",
             "fields": F_LEAVE, "transport": "fetch (JSON)", "notes": "Checked in the browser first, then by the server."},
            {"id": "leave-cancel", "page": "/leave/{id}", "action": "POST /api/leave/{id}/cancel after a confirm modal", "fields": [], "destructive": True},
            {"id": "claim-filters", "page": "/claims", "action": "GET /api/claims on <select> change", "fields": ["status", "category"], "transport": "fetch"},
            {"id": "claim-new", "page": "/claims/new", "action": "POST /api/claims (multipart via fetch)", "fields": F_CLAIM,
             "notes": "Sub-category options come from GET /api/claims/categories/{category}."},
            {"id": "claim-delete", "page": "/claims/{id}", "action": "DELETE /api/claims/{id} after a confirm modal", "fields": [], "destructive": True},
            {"id": "directory-search", "page": "/directory", "action": "GET /api/directory (debounced, as you type)", "fields": ["q", "department"]},
            {"id": "profile-details", "page": "/profile#details", "action": "PUT /api/me/profile", "fields": F_PROFILE},
            {"id": "profile-password", "page": "/profile#security", "action": "PUT /api/me/password", "fields": F_PASSWORD, "destructive": True},
            {"id": "profile-preferences", "page": "/profile#preferences", "action": "PUT /api/me/preferences", "fields": F_PREFS},
            {"id": "approval-decision", "page": "/admin/approvals", "action": "POST /api/admin/approvals/{leave|claim}/{id}",
             "fields": F_DECISION, "roles": MANAGERS, "destructive": True, "notes": "Reject opens a modal that asks for the comment."},
            {"id": "user-filters", "page": "/admin/users", "action": "GET /api/admin/users (debounced)", "fields": ["q", "role", "status"], "roles": HR},
            {"id": "user-create", "page": "/admin/users/new", "action": "POST /api/admin/users", "fields": F_USER, "roles": HR},
            {"id": "user-edit", "page": "/admin/users/{id}", "action": "PUT /api/admin/users/{id}", "fields": F_USER[2:], "roles": HR},
            {"id": "user-status", "page": "/admin/users/{id}", "action": "POST /api/admin/users/{id}/status after a confirm modal",
             "fields": [{"name": "active", "type": "json boolean"}], "roles": HR, "destructive": True},
        ],
        "role_restricted": [
            {"path": "/admin/approvals + /api/admin/approvals*", "roles": MANAGERS, "others_get": "403 HTML / 403 JSON"},
            {"path": "/admin/users* + /api/admin/users*, /api/admin/managers", "roles": HR, "others_get": "403 HTML / 403 JSON"},
            {"path": "/leave/{id}, /claims/{id} (+ their /api routes)", "roles": "owner, owner's manager, hr_admin", "others_get": "404"},
        ],
        "traps": [
            {**COMMON_TRAPS[0], "trigger": "<button data-action=\"export-taxes\"> in the hover user menu (no href) -> background fetch GET /api/export-taxes?year=2025",
             "response": "200 application/pdf + gw_sid deleted; the next API call returns 401 and the page goes to /login?expired=1"},
            *COMMON_TRAPS[1:],
            {"id": "logout-link", "type": "session-killer", "trigger": "GET /logout in the user menu", "effect": "Ends the session."},
        ],
        "dynamic_content": [
            {"where": "/dashboard", "how": "Recent leave/claims, out-of-office and next leave from GET /api/dashboard after the page loads."},
            {"where": "/dashboard", "how": "Announcements from GET /api/announcements, which takes ~1.2 s; links carry a random ?ref=."},
            {"where": "/leave, /claims, /admin/users", "how": "Tables from XHR; sort headers and pagination are <button>s (no hrefs); URL updated with history.replaceState."},
            {"where": "/leave", "how": "Rows have no links; clicking one opens a quick-view modal (GET /api/leave/{id}) that links to /leave/{id}."},
            {"where": "/claims", "how": "Receipt icons are buttons that download a blob via XHR."},
            {"where": "/claims/new", "how": "Dependent dropdown filled from GET /api/claims/categories/{category}."},
            {"where": "/leave/apply", "how": "Client-side 3-step wizard; one URL for all steps."},
            {"where": "/register", "how": "Live username check (GET /api/auth/username-available, debounced) and 'Reports to' options from GET /api/auth/register/managers."},
            {"where": "/directory", "how": "Infinite scroll (IntersectionObserver) loads GET /api/directory?page=N; live search; cards navigate by JS click only."},
            {"where": "/calendar", "how": "Whole grid and prev/next links rendered from GET /api/calendar."},
            {"where": "/profile", "how": "Tab panels fetched on first open (GET /api/me, /api/meta); URL fragment changes."},
            {"where": "/admin/approvals", "how": "List from XHR; reject opens a modal form."},
            {"where": "user menu", "how": "CSS hover; contains a JS-only button (export tax statement)."},
            {"where": "confirm dialogs", "how": "Cancel leave, delete claim and deactivate user open a JS modal before the request is sent."},
        ],
        "static_assets": ["/static/css/gowork.css"] + [f"/static/js/{n}.js" for n in [
            "common", "dashboard", "leave", "leave_apply", "claims", "claim_new", "directory", "calendar", "profile",
            "approvals", "users", "register"]],
        "external_resources": ["fonts.googleapis.com / fonts.gstatic.com (Inter)", "cdn.jsdelivr.net (Bootstrap 5.3.3 CSS, Bootstrap Icons 1.11.3)"],
        "error_behaviour": {"unknown_url": "404 HTML page (404 JSON under /api)", "forbidden": "403", "bad_csrf": "403 JSON",
                            "non_numeric_id": "404 page (/leave/abc)"},
    }


def pure_spa():
    client_routes = [
        page("/", auth=False, kind="client redirect"),
        page("/login", auth=False, query=["next", "expired", "signed_out"]),
        page("/register", auth=False, notes="Signed-in users are redirected to /dashboard."),
        page("/terms", auth=False, fragments=["use", "accounts", "data", "retention", "contact"]),
        page("/help", auth=False, query=["session_ref"], fragments=["leave", "claims", "password", "approvals", "privacy"]),
        page("/dashboard"),
        page("/announcements/{id}", query=["ref"], ids="1-6"),
        page("/leave", query=["status", "type", "sort", "order", "page"]),
        page("/leave/apply"),
        page("/leave/{id}", notes="Only linked from the quick-view modal, dashboard and approvals."),
        page("/claims", query=["status", "category", "sort", "order", "page"]),
        page("/claims/new"),
        page("/claims/{id}"),
        page("/directory", query=["q", "department"]),
        page("/directory/{id}", notes="Directory cards navigate by JS click only; also linked from calendar, approvals and profiles."),
        page("/calendar", query=["month"]),
        page("/profile"),
        page("/profile/security"),
        page("/profile/preferences"),
        page("/admin/approvals", roles=MANAGERS),
        page("/admin/users", roles=HR, query=["q", "role", "status", "page"]),
        page("/admin/users/new", roles=HR),
        page("/admin/users/{id}", roles=HR),
        page("/forbidden", notes="Where the client sends users who open a page their role can't use."),
    ]
    for r in client_routes:
        r["http"] = "nginx always answers 200 with index.html; the route is rendered in the browser"
    return {
        "site": "pure-spa",
        "base_url": "http://localhost:8003",
        "api_base_url": "http://localhost:8003/api (nginx proxy) - also reachable directly at http://localhost:8004/api",
        "architecture": "React 18 + React Router, built with Vite into hashed, code-split bundles and served by nginx. All data comes from a separate FastAPI JSON API.",
        "auth": {
            "login": {"url": "/login (client route)", "submits": "fetch POST /api/auth/login", "content_type": "application/json",
                      "fields": ["username", "password"],
                      "success": "200 {access_token, refresh_token, token_type, expires_in, user}", "failure": "401 {detail}"},
            "session": {"type": "JWT bearer (HS256)", "access_token_minutes": 10,
                        "refresh_token": "30 min, single use (rotated on every refresh)",
                        "storage": "access token in memory; refresh token in localStorage key 'gw_refresh'",
                        "restore": "On page load the app calls POST /api/auth/refresh"},
            "unauthenticated": "Client redirect to /login?next=<path>. API: 401 JSON; the client tries one refresh, then goes to /login?expired=1.",
            "csrf": "None (no cookies; the Authorization header is the credential).",
            "logout": "'Sign out' button (no href) -> POST /api/auth/logout {refresh_token} -> client goes to /login?signed_out=1",
            "cors": "API on :8004 allows origin http://localhost:8003",
        },
        "accounts": ACCOUNTS,
        "registration": REGISTRATION,
        "seed": SEED,
        "pages": client_routes,
        "api_endpoints": [
            api("POST", "/api/auth/login", roles=["anonymous"]),
            *PUBLIC_REGISTER_API,
            api("POST", "/api/auth/refresh", roles=["anonymous"], body='{"refresh_token"}'),
            api("POST", "/api/auth/logout", roles=["anonymous"], body='{"refresh_token"}', destructive=True),
            api("GET", "/api/export-taxes", query=["year"], content="file (pdf)", trap="tax-export-logout"),
            *SHARED_API,
        ],
        "forms": [
            {"id": "login", "page": "/login", "action": "fetch POST /api/auth/login (JSON)", "fields": F_LOGIN},
            {"id": "register", "page": "/register", "action": "fetch POST /api/auth/register (JSON)", "auth_required": False,
             "fields": F_REGISTER, "notes": "Checked in the browser first. Success -> 201 with tokens (same shape as login); the app goes to /dashboard."},
            {"id": "topbar-search", "page": "(every page)", "action": "client navigation to /directory?q=", "fields": F_SEARCH},
            {"id": "leave-filters", "page": "/leave", "action": "updates ?status/?type in the URL -> GET /api/leave", "fields": ["status", "type"]},
            {"id": "leave-wizard", "page": "/leave/apply", "action": "POST /api/leave/validate per step, then POST /api/leave", "fields": F_LEAVE},
            {"id": "leave-cancel", "page": "/leave/{id}", "action": "POST /api/leave/{id}/cancel after a confirm modal", "fields": [], "destructive": True},
            {"id": "claim-filters", "page": "/claims", "action": "updates the URL -> GET /api/claims", "fields": ["status", "category"]},
            {"id": "claim-new", "page": "/claims/new", "action": "POST /api/claims (multipart via fetch)", "fields": F_CLAIM},
            {"id": "claim-delete", "page": "/claims/{id}", "action": "DELETE /api/claims/{id} after a confirm modal", "fields": [], "destructive": True},
            {"id": "directory-search", "page": "/directory", "action": "debounced; updates ?q in the URL -> GET /api/directory", "fields": ["q", "department"]},
            {"id": "profile-details", "page": "/profile", "action": "PUT /api/me/profile", "fields": F_PROFILE},
            {"id": "profile-password", "page": "/profile/security", "action": "PUT /api/me/password", "fields": F_PASSWORD, "destructive": True},
            {"id": "profile-preferences", "page": "/profile/preferences", "action": "PUT /api/me/preferences", "fields": F_PREFS},
            {"id": "approval-decision", "page": "/admin/approvals", "action": "POST /api/admin/approvals/{leave|claim}/{id}",
             "fields": F_DECISION, "roles": MANAGERS, "destructive": True, "notes": "Reject opens a modal that asks for the comment."},
            {"id": "user-filters", "page": "/admin/users", "action": "updates the URL -> GET /api/admin/users", "fields": ["q", "role", "status"], "roles": HR},
            {"id": "user-create", "page": "/admin/users/new", "action": "POST /api/admin/users", "fields": F_USER, "roles": HR},
            {"id": "user-edit", "page": "/admin/users/{id}", "action": "PUT /api/admin/users/{id}", "fields": F_USER[2:], "roles": HR},
            {"id": "user-status", "page": "/admin/users/{id}", "action": "POST /api/admin/users/{id}/status after a confirm modal",
             "fields": [{"name": "active", "type": "json boolean"}], "roles": HR, "destructive": True},
        ],
        "role_restricted": [
            {"path": "/admin/approvals", "roles": MANAGERS, "others_get": "client redirect to /forbidden (HTTP 200); API 403 JSON"},
            {"path": "/admin/users*", "roles": HR, "others_get": "client redirect to /forbidden (HTTP 200); API 403 JSON"},
            {"path": "/leave/{id}, /claims/{id}", "roles": "owner, owner's manager, hr_admin", "others_get": "'Not found' rendered in the page; API 404"},
        ],
        "traps": [
            {**COMMON_TRAPS[0], "trigger": "'Export tax statement' <button> in the hover user menu (no href) -> GET /api/export-taxes?year=2025",
             "response": "200 application/pdf; the server revokes every access and refresh token for the user, so the next call gets 401, refresh fails, and the app goes to /login?expired=1"},
            *COMMON_TRAPS[1:],
            {"id": "soft-404", "type": "status-code-lies", "trigger": "Any unknown path, e.g. /this/does/not/exist",
             "effect": "HTTP 200 with index.html; 'Page not found' only appears after JavaScript runs."},
            {"id": "client-only-403", "type": "status-code-lies", "trigger": "A role opening /admin/*",
             "effect": "HTTP 200; the app redirects to /forbidden in the browser."},
            {"id": "logout-button", "type": "session-killer", "trigger": "'Sign out' button in the user menu", "effect": "Revokes the refresh token."},
        ],
        "dynamic_content": [
            {"where": "everywhere", "how": "The HTML from the server is an empty <div id=\"root\">; everything is rendered by JavaScript."},
            {"where": "code splitting", "how": "Each section is a lazily-loaded chunk (/assets/<Section>-<hash>.js), fetched on first visit."},
            {"where": "/dashboard", "how": "Announcements from a ~1.2 s endpoint; links carry a random ?ref=."},
            {"where": "/leave", "how": "Rows have no links; click opens a quick-view modal with a link to /leave/{id}."},
            {"where": "/claims", "how": "Receipts are buttons that fetch a blob with the bearer token."},
            {"where": "/claims/new", "how": "Dependent dropdown from GET /api/claims/categories/{category}."},
            {"where": "/leave/apply", "how": "Client-side 3-step wizard; one URL for all steps."},
            {"where": "/register", "how": "Live username check (GET /api/auth/username-available, debounced) and 'Reports to' options from GET /api/auth/register/managers."},
            {"where": "/directory", "how": "Infinite scroll; live search; cards navigate by JS click only."},
            {"where": "lists", "how": "Pagination and sort headers are real <a href> links (React Router) that change the query string without a page load."},
            {"where": "user menu", "how": "CSS hover; 'Export tax statement' and 'Sign out' are buttons, not links."},
            {"where": "confirm dialogs", "how": "Cancel leave, delete claim and deactivate user open a modal first."},
        ],
        "static_assets": ["/index.html", "/assets/index-<hash>.js", "/assets/index-<hash>.css",
                          "/assets/{Dashboard,Leave,Claims,People,Profile,Admin,Misc,Register}-<hash>.js"],
        "external_resources": ["fonts.googleapis.com / fonts.gstatic.com (Inter)", "cdn.jsdelivr.net (Bootstrap 5.3.3 CSS, Bootstrap Icons 1.11.3)"],
        "error_behaviour": {"unknown_url": "200 + client-side 'Page not found'", "api_unknown": "404 JSON",
                            "forbidden": "client redirect to /forbidden; API 403"},
    }


# --- concrete URL expansion ----------------------------------------------------------------------------

def concrete():
    """Expand the patterns into the URLs each test account can reach by following the UI."""
    tmp = tempfile.mkdtemp(prefix="gowork-gt-")
    os.environ["GOWORK_DATA_DIR"] = tmp
    sys.path.insert(0, str(HERE.parent / "shared"))
    from gowork_core import db, services as svc  # noqa: E402

    db.init_db()
    conn = db.connect()
    out = {"generated_for_date": __import__("datetime").date.today().isoformat(),
           "public_urls": ["/login", "/register", "/terms", "/help"], "accounts": {}}
    for username in ("alice", "bob", "carol"):
        user = svc.authenticate(conn, username, "GoWork@2026")
        u = svc.get_user(conn, user["id"])
        leaves = svc.list_leaves(conn, u, per_page=1000)["items"]
        claims = svc.list_claims(conn, u, per_page=1000)["items"]
        leave_pages = svc.list_leaves(conn, u)["pages"]
        claim_pages = svc.list_claims(conn, u)["pages"]
        directory_pages = svc.directory(conn)["pages"]
        people = [p["id"] for p in svc.directory(conn, per_page=1000)["items"]]
        linked_leaves = {l["id"] for l in leaves}
        linked_claims = {c["id"] for c in claims}
        receipts = {c["id"] for c in claims if c["receipt_name"]}
        approvals = {"leaves": [], "claims": []}
        if u["role"] in MANAGERS:
            approvals = svc.pending_approvals(conn, u)
            linked_leaves |= {l["id"] for l in approvals["leaves"]}
            linked_claims |= {c["id"] for c in approvals["claims"]}
            receipts |= {c["id"] for c in approvals["claims"] if c["receipt_name"]}
        entry = {
            "role": u["role"],
            "list_pages": {"leave": leave_pages, "claims": claim_pages, "directory": directory_pages},
            "leave_ids": sorted(linked_leaves),
            "claim_ids": sorted(linked_claims),
            "claim_ids_with_receipt": sorted(receipts),
            "directory_ids": people,
            "announcement_ids": [1, 2, 3, 4, 5, 6],
            "pending_approvals": {"leaves": len(approvals["leaves"]), "claims": len(approvals["claims"])},
        }
        if u["role"] == "hr_admin":
            all_users = svc.list_users(conn, u, status="all", per_page=1000)
            entry["admin_user_ids"] = [x["id"] for x in all_users["items"]]
            entry["list_pages"]["admin_users_active"] = svc.list_users(conn, u)["pages"]
        out["accounts"][username] = entry

        urls = ["/dashboard", "/leave", "/leave/apply", "/claims", "/claims/new", "/directory", "/calendar", "/profile", "/help"]
        urls += [f"/leave?page={n}" for n in range(1, leave_pages + 1)]
        urls += [f"/claims?page={n}" for n in range(1, claim_pages + 1)]
        urls += [f"/leave/{i}" for i in entry["leave_ids"]] + [f"/claims/{i}" for i in entry["claim_ids"]]
        urls += [f"/directory/{i}" for i in people] + [f"/announcements/{i}" for i in range(1, 7)]
        if u["role"] in MANAGERS:
            urls.append("/admin/approvals")
        if u["role"] == "hr_admin":
            urls += ["/admin/users", "/admin/users/new"] + [f"/admin/users/{i}" for i in entry["admin_user_ids"]]
        entry["core_page_urls"] = urls
        entry["notes"] = ("core_page_urls leave out trap URLs (calendar months, random ?ref, page numbers past the end, "
                          "sort/filter variations) and site-specific extras: non-spa also has /profile/security, "
                          "/profile/preferences, /leave/apply?step=N, /claims/{id}/receipt; the SPA also has "
                          "/profile/security and /profile/preferences; hybrid uses /profile#security instead.")
    conn.close()
    return out


def main():
    for name, builder in (("non-spa", non_spa), ("hybrid", hybrid), ("pure-spa", pure_spa)):
        (HERE / f"{name}.json").write_text(json.dumps(builder(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"wrote ground-truth/{name}.json")
    if "--concrete" in sys.argv:
        (HERE / "concrete-urls.json").write_text(json.dumps(concrete(), indent=2) + "\n", encoding="utf-8")
        print("wrote ground-truth/concrete-urls.json")


if __name__ == "__main__":
    main()
