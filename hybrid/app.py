"""GoWork - Hybrid edition.

Pages are rendered on the server (layout, navigation, detail pages), but most
lists, forms and actions run in the browser against the JSON API under /api.
Sessions live server-side behind an HttpOnly cookie; every state-changing API
call must send the X-CSRF-Token header from the page's <meta> tag.
"""

import secrets
import sys
import time
from datetime import date, datetime
from pathlib import Path
from urllib.parse import quote

HERE = Path(__file__).resolve().parent
SHARED = HERE.parent / "shared"
sys.path.insert(0, str(SHARED))

from fastapi import Body, Depends, FastAPI, Request  # noqa: E402
from fastapi.exceptions import RequestValidationError  # noqa: E402
from fastapi.responses import JSONResponse, RedirectResponse, Response  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from fastapi.templating import Jinja2Templates  # noqa: E402
from starlette.exceptions import HTTPException as StarletteHTTPException  # noqa: E402

from gowork_core import db, services as svc  # noqa: E402
from gowork_core.api import build_public_router, build_router  # noqa: E402
from gowork_core.constants import (  # noqa: E402
    CLAIM_CATEGORIES, CLAIM_STATUSES, DEPARTMENTS, EXPORT_TRAP, LEAVE_STATUSES, LEAVE_TYPES, ROLES,
    SESSION_IDLE_MINUTES, session_too_old,
)

app = FastAPI(title="GoWork Hybrid", docs_url=None, redoc_url=None, openapi_url=None)
templates = Jinja2Templates(directory=str(HERE / "templates"))
db.init_db()

SESSIONS = {}  # session id -> {"user_id", "csrf", "last_seen", "auth_at"}
COOKIE = "gw_sid"
UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


class Unauthorized(svc.ServiceError):
    status = 401

    def __init__(self, message="Your session has expired. Please sign in again."):
        super().__init__(message)


class LoginRequired(Exception):
    def __init__(self, expired):
        self.expired = expired


# --- sessions ---------------------------------------------------------------------

def _load_session(request: Request):
    sid = request.cookies.get(COOKIE)
    session = SESSIONS.get(sid) if sid else None
    if session is None:
        return None
    now = time.time()
    if now - session["last_seen"] > SESSION_IDLE_MINUTES * 60 or session_too_old(session["auth_at"], now):
        SESSIONS.pop(sid, None)
        return None
    session["last_seen"] = now
    request.state.sid = sid
    request.state.session = session
    return session


def api_user(request: Request, conn=Depends(db.get_conn)):
    session = _load_session(request)
    user = svc.get_user(conn, session["user_id"]) if session else None
    if user is None:
        raise Unauthorized()
    if request.method in UNSAFE_METHODS and not secrets.compare_digest(
            request.headers.get("X-CSRF-Token", ""), session["csrf"]):
        raise svc.Forbidden("CSRF token missing or invalid. Refresh the page and try again.")
    return user


def page_user(request: Request, conn=Depends(db.get_conn)):
    session = _load_session(request)
    user = svc.get_user(conn, session["user_id"]) if session else None
    if user is None:
        raise LoginRequired(expired=COOKIE in request.cookies)
    return user


def page_role(*roles):
    def dependency(user=Depends(page_user)):
        svc.require_role(user, *roles)
        return user
    return dependency


def _safe_next(target):
    if target and target.startswith("/") and not target.startswith("//") and "\\" not in target:
        return target
    return "/dashboard"


# --- rendering --------------------------------------------------------------------

def _fdate(value):
    if not value:
        return "—"
    try:
        if "T" in value:
            return datetime.fromisoformat(value).strftime("%d %b %Y, %H:%M")
        return date.fromisoformat(value).strftime("%d %b %Y")
    except ValueError:
        return value


templates.env.filters["fdate"] = _fdate


def render(request: Request, name, user=None, status_code=200, **context):
    session = getattr(request.state, "session", None)
    context.update(
        user=user, csrf_token=session["csrf"] if session else "", random_ref=lambda: secrets.token_hex(4),
        today=date.today().isoformat(), ROLES=ROLES,
    )
    return templates.TemplateResponse(request, name, context, status_code=status_code)


def _error_page(request: Request, code, message):
    user = None
    conn = db.connect()
    try:
        session = _load_session(request)
        user = svc.get_user(conn, session["user_id"]) if session else None
    finally:
        conn.close()
    return render(request, "error.html", user=user, status_code=code, code=code, message=message)


@app.exception_handler(LoginRequired)
async def login_required(request: Request, error: LoginRequired):
    target = request.url.path + (f"?{request.url.query}" if request.url.query else "")
    return RedirectResponse(f"/login?next={quote(target)}" + ("&expired=1" if error.expired else ""), 302)


@app.exception_handler(svc.ServiceError)
async def service_error(request: Request, error: svc.ServiceError):
    if request.url.path.startswith("/api/"):
        return JSONResponse({"detail": error.message, "errors": error.errors}, status_code=error.status)
    return _error_page(request, error.status, error.message)


@app.exception_handler(StarletteHTTPException)
async def http_error(request: Request, error: StarletteHTTPException):
    messages = {404: "We couldn't find the page you were looking for.", 405: "That action isn't allowed here."}
    message = messages.get(error.status_code, error.detail)
    if request.url.path.startswith("/api/"):
        return JSONResponse({"detail": message}, status_code=error.status_code)
    return _error_page(request, error.status_code, message)


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, error: RequestValidationError):
    if request.url.path.startswith("/api/"):
        return JSONResponse({"detail": "Invalid request", "errors": {
            ".".join(str(p) for p in e["loc"][1:]): e["msg"] for e in error.errors()}}, status_code=422)
    return _error_page(request, 404, "We couldn't find the page you were looking for.")


# --- auth API ---------------------------------------------------------------------

@app.post("/api/auth/login")
def api_login(data: dict = Body(...), conn=Depends(db.get_conn)):
    user = svc.authenticate(conn, data.get("username"), data.get("password"))
    if user is None:
        return JSONResponse({"detail": "Incorrect username or password."}, status_code=401)
    return _start_session(JSONResponse({"status": "ok", "next": _safe_next(data.get("next"))}), user["id"])


@app.post("/api/auth/register", status_code=201)
def api_register(data: dict = Body(...), conn=Depends(db.get_conn)):
    user_id = svc.register(conn, data)
    return _start_session(JSONResponse({"status": "created", "id": user_id, "next": "/dashboard"}, status_code=201),
                          user_id)


def _start_session(response, user_id):
    sid = secrets.token_urlsafe(32)
    now = time.time()
    SESSIONS[sid] = {"user_id": user_id, "csrf": secrets.token_urlsafe(32), "last_seen": now, "auth_at": now}
    response.set_cookie(COOKIE, sid, httponly=True, samesite="lax")
    return response


@app.post("/api/auth/logout")
def api_logout(request: Request, user=Depends(api_user)):
    SESSIONS.pop(request.state.sid, None)
    response = JSONResponse({"status": "signed out"})
    response.delete_cookie(COOKIE)
    return response


@app.get("/api/export-taxes")
def export_taxes(request: Request, year: str = "", user=Depends(api_user), conn=Depends(db.get_conn)):
    # Crawler trap: this background download destroys the session, so the next API call gets a 401
    # (unless EXPORT_TRAP=0).
    filename, pdf = svc.tax_statement(conn, user, year)
    response = Response(pdf, media_type="application/pdf",
                        headers={"Content-Disposition": f'attachment; filename="{filename}"'})
    if EXPORT_TRAP:
        SESSIONS.pop(request.state.sid, None)
        response.delete_cookie(COOKIE)
    return response


app.include_router(build_public_router())
app.include_router(build_router(api_user))


# --- pages ------------------------------------------------------------------------

@app.get("/")
def index(request: Request):
    return RedirectResponse("/dashboard" if _load_session(request) else "/login", 302)


@app.get("/login")
def login_page(request: Request, next: str = "", expired: str = "", signed_out: str = ""):
    if _load_session(request):
        return RedirectResponse(_safe_next(next), 302)
    return render(request, "login.html", next=next, expired=expired, signed_out=signed_out)


@app.get("/register")
def register_page(request: Request):
    if _load_session(request):
        return RedirectResponse("/dashboard", 302)
    return render(request, "register.html", DEPARTMENTS=DEPARTMENTS)


@app.get("/terms")
def terms_page(request: Request, conn=Depends(db.get_conn)):
    session = _load_session(request)
    return render(request, "terms.html", user=svc.get_user(conn, session["user_id"]) if session else None)


@app.get("/logout")
def logout(request: Request):
    SESSIONS.pop(request.cookies.get(COOKIE), None)
    response = RedirectResponse("/login?signed_out=1", 302)
    response.delete_cookie(COOKIE)
    return response


@app.get("/help")
def help_page(request: Request, conn=Depends(db.get_conn)):
    session = _load_session(request)
    return render(request, "help.html", user=svc.get_user(conn, session["user_id"]) if session else None)


@app.get("/dashboard")
def dashboard(request: Request, user=Depends(page_user), conn=Depends(db.get_conn)):
    # Stat cards are rendered here; the lists below them are fetched by dashboard.js
    return render(request, "dashboard.html", user, data=svc.dashboard(conn, user))


@app.get("/announcements/{announcement_id}")
def announcement(request: Request, announcement_id: int, user=Depends(page_user), conn=Depends(db.get_conn)):
    return render(request, "announcement.html", user, a=svc.get_announcement(conn, announcement_id),
                  others=svc.list_announcements(conn, 6))


@app.get("/leave")
def leave_list(request: Request, user=Depends(page_user), conn=Depends(db.get_conn)):
    return render(request, "leave_list.html", user, balances=svc.leave_balances(conn, user["id"]),
                  LEAVE_STATUSES=LEAVE_STATUSES, LEAVE_TYPES=LEAVE_TYPES)


@app.get("/leave/apply")
def leave_apply(request: Request, user=Depends(page_user), conn=Depends(db.get_conn)):
    return render(request, "leave_apply.html", user, LEAVE_TYPES=LEAVE_TYPES,
                  balances={b["type"]: b for b in svc.leave_balances(conn, user["id"])})


@app.get("/leave/{leave_id}")
def leave_detail(request: Request, leave_id: int, user=Depends(page_user), conn=Depends(db.get_conn)):
    return render(request, "leave_detail.html", user, leave=svc.get_leave(conn, user, leave_id))


@app.get("/claims")
def claims_list(request: Request, user=Depends(page_user)):
    return render(request, "claims_list.html", user, CLAIM_STATUSES=CLAIM_STATUSES,
                  CLAIM_CATEGORIES=CLAIM_CATEGORIES)


@app.get("/claims/new")
def claim_new(request: Request, user=Depends(page_user)):
    return render(request, "claim_new.html", user, CLAIM_CATEGORIES=CLAIM_CATEGORIES)


@app.get("/claims/{claim_id}")
def claim_detail(request: Request, claim_id: int, user=Depends(page_user), conn=Depends(db.get_conn)):
    return render(request, "claim_detail.html", user, claim=svc.get_claim(conn, user, claim_id))


@app.get("/directory")
def directory(request: Request, q: str = "", department: str = "", user=Depends(page_user),
              conn=Depends(db.get_conn)):
    # First page is server-rendered; directory.js loads the rest with infinite scroll
    return render(request, "directory.html", user, result=svc.directory(conn, q, department, 1),
                  DEPARTMENTS=DEPARTMENTS)


@app.get("/directory/{user_id}")
def profile_view(request: Request, user_id: int, user=Depends(page_user), conn=Depends(db.get_conn)):
    return render(request, "profile_view.html", user, p=svc.get_profile(conn, user_id))


@app.get("/calendar")
def team_calendar(request: Request, user=Depends(page_user)):
    return render(request, "calendar.html", user)


@app.get("/profile")
def profile(request: Request, user=Depends(page_user), conn=Depends(db.get_conn)):
    return render(request, "profile.html", user, me=svc.get_profile(conn, user["id"]))


@app.get("/admin/approvals")
def approvals(request: Request, user=Depends(page_role("manager", "hr_admin"))):
    return render(request, "approvals.html", user)


@app.get("/admin/users")
def users(request: Request, user=Depends(page_role("hr_admin"))):
    return render(request, "users.html", user)


@app.get("/admin/users/new")
def user_new(request: Request, user=Depends(page_role("hr_admin")), conn=Depends(db.get_conn)):
    return render(request, "user_form.html", user, target=None, managers=svc.manager_choices(conn),
                  DEPARTMENTS=DEPARTMENTS)


@app.get("/admin/users/{user_id}")
def user_edit(request: Request, user_id: int, user=Depends(page_role("hr_admin")), conn=Depends(db.get_conn)):
    return render(request, "user_form.html", user, target=svc.get_user_admin(conn, user, user_id),
                  managers=svc.manager_choices(conn), DEPARTMENTS=DEPARTMENTS)


app.mount("/static/css", StaticFiles(directory=str(SHARED / "static")), name="shared-static")
app.mount("/static", StaticFiles(directory=str(HERE / "static")), name="static")
