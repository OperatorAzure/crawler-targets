"""Scores a crawl, exported from Burp Suite, against the GoWork answer key.

    python ground-truth/score.py crawls/spa-carol-23102026.xml
    python ground-truth/score.py crawls/hybrid-bob.xml --site hybrid --user bob --json report.json

Export the crawl from Burp: Proxy > HTTP history, select every row, right-click > "Save items"
(base64 on). Use one export per site and account, starting from freshly restarted containers.
The site is inferred from the port and the account from the sign-in requests; pass --site /
--user to override.

The session timeline labels every lost session with a likely cause (tax export, 60 s timeout, idle
timeout, logout, unknown) and reports whether and how fast the crawler signed back in. The cap
comes from the answer key; pass --max-session if the containers ran with another SESSION_MAX_SECONDS.

A page only counts as *reached* when the crawler got its content:
  - Non-SPA / Hybrid: the server returned the page with 200 (it redirects when you are signed out).
  - Pure SPA: every route returns the same index.html, so an HTML 200 proves nothing. A route
    counts once the API call that fills it succeeded (e.g. /leave/17 <- GET /api/leave/17 200).
Hybrid and the SPA also get credit for content reached only through the API (in-app navigation
does not always produce a page request).
"""

import argparse
import base64
import json
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from statistics import median
from urllib.parse import parse_qs, unquote, urlsplit

HERE = Path(__file__).resolve().parent
PORTS = {8001: "non-spa", 8002: "hybrid", 8003: "pure-spa", 8004: "pure-spa"}
SITE_PORTS = {"non-spa": {8001}, "hybrid": {8002}, "pure-spa": {8003, 8004}}
LOCAL_HOSTS = {"localhost", "127.0.0.1"}
PUBLIC_PAGES = {"/", "/login", "/register", "/help", "/terms", "/forbidden"}
PAGED_CORE = {"/leave", "/claims"}   # the lists whose ?page=N appear in core_page_urls
LIST_PAGES = {"/leave": "leave", "/claims": "claims", "/directory": "directory", "/admin/users": "admin_users_active"}
FILTER_PARAMS = {"sort", "order", "status", "type", "category", "department", "q", "role"}
SECRET_PARAMS = {"password", "temp_password", "new_password", "current_password", "confirm_password"}
EXPORT_PATHS = {"/export-taxes", "/api/export-taxes"}
UNREACHABLE = {"hr_admin": {"/forbidden"}}   # HR may open every page, so the app never sends them to /forbidden

# GET <api> 200 means the crawler saw the content of <page> (Hybrid and SPA share this API).
API_TO_PAGE = [
    ("/api/dashboard", "/dashboard"),
    ("/api/announcements/{id}", "/announcements/{id}"),
    ("/api/leave", "/leave"),
    ("/api/leave/{id}", "/leave/{id}"),
    ("/api/claims", "/claims"),
    ("/api/claims/{id}", "/claims/{id}"),
    ("/api/directory", "/directory"),
    ("/api/directory/{id}", "/directory/{id}"),
    ("/api/calendar", "/calendar"),
    ("/api/me", "/profile"),
    ("/api/admin/approvals", "/admin/approvals"),
    ("/api/admin/users", "/admin/users"),
    ("/api/admin/users/{id}", "/admin/users/{id}"),
    ("/api/auth/username-available", "/register"),
    ("/api/auth/register/managers", "/register"),
]
# SPA routes whose data call doesn't identify them on its own (from the useApi calls in pages/*.jsx).
SPA_ROUTE_APIS = {
    "/leave/apply": ["/api/leave/balances"],
    "/claims/new": ["/api/claims/categories"],
    "/admin/users/new": ["/api/admin/managers"],
    "/profile/{tab}": ["/api/me", "/api/meta"],
}


def template_re(template):
    parts = re.split(r"(\{[^}]+\})", template)
    out = "".join(r"\d+" if p == "{id}" else "[^/]+" if p.startswith("{") else re.escape(p) for p in parts)
    return re.compile(f"^{out}$")


def fill(template, path, target):
    """Copies the {id} values matched in `path` into `target`'s placeholders."""
    values = iter(re.findall(r"\d+", path))
    return re.sub(r"\{[^}]+\}", lambda _: next(values, "?"), target)


class Req:
    def __init__(self, item):
        self.time = item.findtext("time") or ""
        self.host = (item.findtext("host") or "").lower()
        self.port = int(item.findtext("port") or 0)
        self.method = item.findtext("method") or ""
        self.status = int(item.findtext("status") or 0)
        self.mime = (item.findtext("mimetype") or "").upper()
        url = urlsplit(item.findtext("path") or "/")
        self.path = unquote(url.path) or "/"
        self.raw = item.findtext("path") or "/"
        self.query = parse_qs(url.query, keep_blank_values=True)
        self.request = _decode(item.find("request"))
        self.response = _decode(item.find("response"))
        self.api = self.path.startswith("/api/") or self.port == 8004
        self.asset = self.path.startswith(("/assets/", "/static/")) or "." in self.path.rsplit("/", 1)[-1]
        self.page = not self.api and not self.asset and self.method == "GET"

    def header(self, name):
        m = re.search(rf"^{name}:\s*(.*?)\r?$", self.response.split("\r\n\r\n", 1)[0], re.I | re.M)
        return m.group(1) if m else ""

    def body(self):
        return self.request.split("\r\n\r\n", 1)[1] if "\r\n\r\n" in self.request else ""


def _decode(node):
    if node is None or not node.text:
        return ""
    return base64.b64decode(node.text).decode("latin-1") if node.get("base64") == "true" else node.text


def load_burp(path):
    return [Req(item) for item in ET.parse(path).getroot().iter("item")]


def login_username(r):
    """Username of a successful sign-in/registration request, else None."""
    ok = (r.path in ("/api/auth/login", "/api/auth/register") and r.status in (200, 201)) or (
        r.path in ("/login", "/register") and r.method == "POST" and r.status == 302
        and not urlsplit(r.header("Location")).path.endswith(("/login", "/register")))
    if not ok:
        return None
    body = r.body()
    try:
        return json.loads(body).get("username")
    except (ValueError, AttributeError):
        return (parse_qs(body).get("username") or [None])[0]


def burp_time(r):
    """Burp's '<day> Oct 23 14:05:01 SGT 2026' as a datetime (whole seconds), else None."""
    m = re.match(r"\w+ (\w+) (\d+) ([\d:]+) \S+ (\d{4})", r.time)
    return datetime.strptime(" ".join(m.groups()), "%b %d %H:%M:%S %Y") if m else None


def burp_date(requests):
    for r in requests:
        t = burp_time(r)
        if t:
            return t.strftime("%Y-%m-%d")
    return None


def page_keys(path, query):
    """The core_page_urls entries a page/list URL stands for."""
    if path in PAGED_CORE:
        page = (query.get("page") or ["1"])[0]
        return {path, f"{path}?page={page}"}
    return {path}


def score(requests, site, user, max_session=None):
    key = json.loads((HERE / f"{site}.json").read_text(encoding="utf-8"))
    concrete = json.loads((HERE / "concrete-urls.json").read_text(encoding="utf-8"))
    account = concrete["accounts"].get(user, {})
    role = next((a["role"] for a in key["accounts"] if a["username"] == user), account.get("role", "employee"))
    page_templates = [(p["path"], template_re(p["path"]), p) for p in key["pages"]]
    endpoints = [(e, template_re(e["path"])) for e in key.get("api_endpoints", [])]
    api_to_page = [(template_re(a), p) for a, p in API_TO_PAGE]
    spa = site == "pure-spa"

    destructive = [(e["method"], template_re(e["path"])) for e in key.get("api_endpoints", []) if e.get("destructive")]
    for f in key["forms"]:
        m = re.search(r"\b(GET|POST|PUT|DELETE)\s+(/\S+)", f.get("action", ""))
        if f.get("destructive") and m:
            destructive.append((m.group(1), template_re(m.group(2).replace("{leave|claim}", "{kind}"))))
    destructive.append(("GET", template_re("/logout")))

    in_scope = [r for r in requests if r.host in LOCAL_HOSTS and r.port in SITE_PORTS[site]]
    out_of_scope = Counter(f"{r.host}:{r.port}" for r in requests if r not in in_scope)

    # Session limits come from the answer key; the scorer can't see which settings the containers ran with.
    session_key = key["auth"]["session"]
    if max_session is None:
        max_session = session_key.get("max_session_seconds", 0)
    idle_limit = timedelta(minutes=session_key.get("idle_timeout_minutes", 30))

    # Walk the crawl in order, tracking whether the session is alive.
    alive, events, dead_requests = False, [], 0
    signed_in_at = last_request_at = None
    export_pending = False   # a tax export came back 200; the next signed-in request shows whether it ended the session
    export_kills = export_harmless = 0
    losses, outage, lost_at = [], None, None   # every lost session; the one not recovered from yet, and when

    def cause_of_loss(now):
        """Best guess at why the session died, since the sites answer every cause the same way."""
        if export_pending:
            return "tax export"
        due = []
        if now and signed_in_at and max_session:
            due.append((signed_in_at + timedelta(seconds=max_session), f"{max_session} s timeout"))
        if now and last_request_at:
            due.append((last_request_at + idle_limit, "idle timeout"))
        # Burp stamps whole seconds, so allow one second of rounding
        due = [d for d in due if d[0] <= now + timedelta(seconds=1)]
        return min(due)[1] if due else "unknown"

    def lose(stamp, now, cause, what):
        nonlocal alive, outage, lost_at, export_pending, export_kills
        if cause == "tax export":
            export_kills += 1
        export_pending, alive = False, False
        events.append((stamp, f"{what} - cause: {cause}"))
        outage = {"cause": cause, "lost": stamp, "recovered": None, "how": None, "seconds": None, "requests_while_out": 0}
        losses.append(outage)
        lost_at = now

    def recover(stamp, now, how):
        nonlocal outage
        if outage:
            outage["recovered"], outage["how"] = stamp, how
            if now and lost_at:
                outage["seconds"] = int((now - lost_at).total_seconds())
            outage = None

    reached, requested, shells = set(), set(), []
    api_hits = defaultdict(Counter)
    current_page = None   # SPA: (path, query, credited?) of the last full page load
    unknown_pages = Counter()
    for r in in_scope:
        stamp, now = r.time[11:19], burp_time(r)
        name = login_username(r)
        # SPA requests sent without the bearer token (a download re-fetch, a fresh tab, a public endpoint
        # like /api/meta) say nothing about whether the session is alive
        tokenless = spa and not re.search(r"^Authorization:", r.request, re.I | re.M)
        if not alive and not name and not r.asset and r.path not in PUBLIC_PAGES and r.path != "/api/auth/login":
            dead_requests += 1
            if outage:
                outage["requests_while_out"] += 1
        # A 2xx that only a signed-in user gets (SPA pages are the same index.html either way, so only its API counts)
        signed_in_ok = (200 <= r.status < 300 and not tokenless and r.path not in PUBLIC_PAGES and r.path not in EXPORT_PATHS
                        and not r.path.startswith("/api/auth/") and (r.api or (r.page and not spa)))
        if name:
            if outage:
                events.append((stamp, f"signed in again as {name}"))
                recover(stamp, now, "sign-in")
            elif not alive:
                events.append((stamp, f"signed in as {name}"))
            alive, signed_in_at, export_pending = True, now, False
        elif r.method == "GET" and r.path in EXPORT_PATHS and r.status == 200:
            events.append((stamp, "TRAP: tax export downloaded"))
            export_pending = True
        elif (r.path == "/logout" and r.status in (200, 302)) or (r.path == "/api/auth/logout" and r.status < 300):
            if alive:
                lose(stamp, now, "logout", "signed out (logout link/button)")
        elif r.path == "/api/auth/refresh":
            if r.status == 200 and not alive:
                events.append((stamp, "session restored by refresh token"))
                recover(stamp, now, "refresh token")
                alive = True
            elif r.status == 401 and alive:
                lose(stamp, now, cause_of_loss(now), "refresh token rejected -> signed out")
        elif tokenless and r.status == 401:
            pass
        elif r.status == 401 or (r.status == 302 and "/login" in r.header("Location") and r.path != "/logout"):
            if alive:
                lose(stamp, now, cause_of_loss(now), f"lost session ({r.status} on {r.method} {r.path})")
        elif signed_in_ok:
            if export_pending:
                events.append((stamp, "tax export left the session alive (EXPORT_TRAP=0)"))
                export_pending, export_harmless = False, export_harmless + 1
            alive = True
        if not r.asset and now:
            last_request_at = now

        if r.api:
            if spa and name:
                reached.add(r.path[len("/api/auth"):])   # /login or /register
            for e, rx in endpoints:
                if e["method"] == r.method and rx.match(r.path):
                    api_hits[(e["method"], e["path"])][r.status] += 1
                    break
            if r.method == "GET" and 200 <= r.status < 300:
                for rx, page in api_to_page:
                    if rx.match(r.path):
                        reached.update(page_keys(fill(page, r.path, page), r.query))
                        if spa and current_page:
                            current_page[2] = True
                if spa and current_page and not current_page[2]:
                    for route, apis in SPA_ROUTE_APIS.items():
                        if template_re(route).match(current_page[0]) and any(template_re(a).match(r.path) for a in apis):
                            reached.update(page_keys(current_page[0], current_page[1]))
                            current_page[2] = True
            continue

        if not r.page:
            continue
        if not any(rx.match(r.path) for _, rx, _ in page_templates):
            unknown_pages[r.raw] += 1
        if r.status != 200:
            continue
        requested.update(page_keys(r.path, r.query))
        if spa:
            if current_page and not current_page[2] and current_page[0] not in PUBLIC_PAGES:
                shells.append(current_page[0])
            current_page = [r.path, r.query, r.path in PUBLIC_PAGES]
            if r.path in PUBLIC_PAGES:
                reached.add(r.path)
        else:
            reached.update(page_keys(r.path, r.query))
    if spa and current_page and not current_page[2] and current_page[0] not in PUBLIC_PAGES:
        shells.append(current_page[0])

    # Coverage against the concrete URLs for this account.
    core = set(account.get("core_page_urls", [])) | set(concrete.get("public_urls", []))
    core_reached = core & reached
    core_requested = core & requested

    # Coverage of the URL patterns and API endpoints this role may use.
    allowed = lambda roles: role in roles or "anonymous" in roles
    pattern_rows = []
    for template, rx, p in page_templates:
        if (allowed(p["roles"]) and p.get("content") != "redirect" and not (p.get("destructive") or p.get("trap"))
                and template not in UNREACHABLE.get(role, ())):
            pattern_rows.append((template, any(rx.match(urlsplit(u).path) for u in reached)))
    api_rows = []
    for e, _ in endpoints:
        if allowed(e["roles"]):
            hits = api_hits.get((e["method"], e["path"]), Counter())
            ok = sum(n for s, n in hits.items() if 200 <= s < 300)
            api_rows.append({"method": e["method"], "path": e["path"], "ok": ok, "other": sum(hits.values()) - ok,
                             "avoid": bool(e.get("destructive") or e.get("trap"))})

    # Traps.
    def params(name):
        return [v for r in in_scope for v in r.query.get(name, [])]
    tax = [r for r in in_scope if r.path in EXPORT_PATHS]
    months = set(params("month"))
    beyond = []
    for r in in_scope:
        base = r.path[4:] if r.path.startswith("/api/") else r.path
        limit = account.get("list_pages", {}).get(LIST_PAGES.get(base, ""), None)
        page = (r.query.get("page") or [""])[0]
        if limit and page.isdigit() and int(page) > limit:
            beyond.append(f"{r.path}?page={page}")
    ref_urls = [r for r in in_scope if "ref" in r.query or "session_ref" in r.query]
    ref_dupes = len(ref_urls) - len({r.path for r in ref_urls})
    filtered = {r.raw for r in in_scope if FILTER_PARAMS & set(r.query)}
    destroyed = [f"{r.method} {r.raw} -> {r.status}" for r in in_scope
                 if any(m == r.method and rx.match(r.path) for m, rx in destructive)]
    secrets = sorted({r.raw.split("?")[0] + " (" + ", ".join(sorted(SECRET_PARAMS & set(r.query))) + ")"
                      for r in in_scope if SECRET_PARAMS & set(r.query)})
    secret_count = sum(1 for r in in_scope if SECRET_PARAMS & set(r.query))
    forbidden = [(t, p) for t, _, p in page_templates if not allowed(p["roles"])]
    privilege = sorted({u for u in reached for t, p in forbidden if template_re(t).match(urlsplit(u).path)})

    return {
        "site": site, "user": user, "role": role,
        "date": {"crawl": burp_date(in_scope), "answer_key": concrete.get("generated_for_date")},
        "requests": {"total": len(requests), "in_scope": len(in_scope), "out_of_scope": dict(out_of_scope),
                     "status": dict(sorted(Counter(r.status for r in in_scope).items())),
                     "while_signed_out": dead_requests,
                     "assets": sum(1 for r in in_scope if r.asset)},
        "session": events,
        "reauth": {"max_session_seconds": max_session, "losses": losses},
        "core": {"total": len(core), "reached": sorted(core_reached), "requested_only": sorted(core_requested - core_reached),
                 "missed": sorted(core - core_requested - core_reached)},
        "spa_empty_shells": shells,
        "patterns": pattern_rows, "api": api_rows,
        "traps": {
            "tax_export": {"requests": len(tax), "triggered": sum(r.status == 200 for r in tax),
                           "ended_session": export_kills, "harmless": export_harmless},
            "calendar_months": len(months),
            "pages_past_end": beyond,
            "random_ref": {"requests": len(ref_urls), "duplicate_visits": ref_dupes},
            "filter_sort_variants": len(filtered),
            "destructive": destroyed,
            "unknown_paths": dict(unknown_pages),
            "secrets_in_url": {"requests": secret_count, "urls": secrets},
            "pages_above_role": privilege,
        },
    }


def plural(n, word):
    return f"{n} {word}" + ("" if n == 1 else "s")


def pct(n, d):
    return f"{n}/{d} ({100 * n / d:.0f}%)" if d else "0/0"


def print_report(s):
    rq, c, t = s["requests"], s["core"], s["traps"]
    print(f"GoWork crawl score  site={s['site']}  user={s['user']} ({s['role']})")
    if s["date"]["crawl"] != s["date"]["answer_key"]:
        print(f"  WARNING: crawl date {s['date']['crawl']} != answer key date {s['date']['answer_key']}; "
              "regenerate concrete-urls.json for the crawl day.")
    print(f"\nRequests: {rq['in_scope']} in scope, status {rq['status']}")
    print(f"  made while signed out: {rq['while_signed_out']}   assets: {rq['assets']}"
          + ("  (none: Burp's filter hid scripts, or the browser cache served them)" if not rq["assets"] else ""))
    if rq["out_of_scope"]:
        print(f"  out of scope: {rq['out_of_scope']}")

    print("\nSession timeline:")
    for stamp, what in s["session"] or [("", "never signed in")]:
        print(f"  {stamp}  {what}")

    ra = s["reauth"]
    cap = f"sessions capped at {ra['max_session_seconds']} s after sign-in" if ra["max_session_seconds"] else "no session cap"
    print(f"\nRe-authentication ({cap}):")
    if not ra["losses"]:
        print("  the session was never lost")
    else:
        causes = Counter(x["cause"] for x in ra["losses"])
        back = [x for x in ra["losses"] if x["recovered"]]
        timed = [x["seconds"] for x in back if x["seconds"] is not None]
        print(f"  sessions lost: {len(ra['losses'])} (" + ", ".join(f"{c} x{n}" for c, n in causes.most_common()) + ")")
        print(f"  recovered: {pct(len(back), len(ra['losses']))}"
              + (f", median {median(timed):g} s to get back in" if timed else "")
              + f", {plural(sum(x['requests_while_out'] for x in ra['losses']), 'request')} made while signed out")
        for x in ra["losses"]:
            out = plural(x["requests_while_out"], "request") + " while out"
            if x["recovered"]:
                took = f"{x['seconds']} s, " if x["seconds"] is not None else ""
                after = f"back in by {x['how']} at {x['recovered']} ({took}{out})"
            else:
                after = f"NEVER RECOVERED ({out})"
            print(f"    {x['lost']}  {x['cause']:<14} -> {after}")

    print(f"\nCore URLs for {s['user']}: reached {pct(len(c['reached']), c['total'])}")
    if c["requested_only"]:
        print(f"  requested but content never loaded: {len(c['requested_only'])}")
    by_kind = Counter(re.sub(r"/\d+$", "/{id}", u.split("?")[0]) for u in c["missed"] + c["requested_only"])
    if by_kind:
        print("  not reached, by pattern: " + ", ".join(f"{k} x{n}" for k, n in sorted(by_kind.items())))
    if s["spa_empty_shells"]:
        print(f"  SPA routes loaded with no data (blank or login screen): {len(s['spa_empty_shells'])}")

    print(f"\nURL patterns reached: {pct(sum(ok for _, ok in s['patterns']), len(s['patterns']))}")
    print("  missing: " + (", ".join(t for t, ok in s["patterns"] if not ok) or "none"))
    if s["api"]:
        expect = [a for a in s["api"] if not a["avoid"]]
        print(f"\nAPI endpoints with a 2xx: {pct(sum(a['ok'] > 0 for a in expect), len(expect))}"
              " (destructive/trap endpoints excluded)")
        failed = [f"{a['method']} {a['path']}" for a in expect if not a["ok"] and a["other"]]
        if failed:
            print("  only non-2xx: " + ", ".join(failed))
        print("  never called: " + (", ".join(f"{a['method']} {a['path']}" for a in expect if not a["ok"] and not a["other"]) or "none"))

    print("\nTraps:")
    tx = t["tax_export"]
    print(f"  tax export:            {tx['triggered']} downloads ({tx['ended_session']} ended the session, "
          f"{tx['harmless']} harmless), {tx['requests']} requests")
    print(f"  calendar months:       {t['calendar_months']} distinct")
    print(f"  pages past the end:    {len(t['pages_past_end'])}")
    print(f"  random ?ref URLs:      {t['random_ref']['requests']} requests, {t['random_ref']['duplicate_visits']} repeat visits of the same page")
    print(f"  filter/sort variants:  {t['filter_sort_variants']}")
    print(f"  destructive actions:   {len(t['destructive'])}" + "".join(f"\n    {d}" for d in t["destructive"]))
    if t["unknown_paths"]:
        print(f"  unknown paths:         {', '.join(f'{u} x{n}' for u, n in t['unknown_paths'].items())}")
    if t["secrets_in_url"]["requests"]:
        print(f"  passwords in URL:      {t['secrets_in_url']['requests']} requests, e.g. {t['secrets_in_url']['urls'][0]}")
    if t["pages_above_role"]:
        print(f"  PRIVILEGE: reached pages above {s['role']}: {', '.join(t['pages_above_role'])}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("export", help="Burp 'Save items' XML export")
    ap.add_argument("--site", choices=sorted(SITE_PORTS), help="default: from the port")
    ap.add_argument("--user", help="default: from the sign-in requests")
    ap.add_argument("--max-session", type=int, metavar="SECONDS",
                    help="SESSION_MAX_SECONDS the containers ran with (default: from the answer key; 0 = off)")
    ap.add_argument("--json", metavar="FILE", help="also write the full report as JSON")
    args = ap.parse_args()

    requests = load_burp(args.export)
    site = args.site or Counter(PORTS[r.port] for r in requests if r.port in PORTS).most_common(1)[0][0]
    user = args.user or (Counter(filter(None, map(login_username, requests))).most_common(1) or [("?", 0)])[0][0]
    report = score(requests, site, user, args.max_session)
    print_report(report)
    if args.json:
        Path(args.json).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(f"\nwrote {args.json}")


if __name__ == "__main__":
    sys.exit(main())
