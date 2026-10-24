"""GoWork - Pure SPA backend (JSON only; the React app is served by nginx).

Auth uses short-lived JWT access tokens sent as `Authorization: Bearer ...`
plus rotating refresh tokens. Logging out revokes the refresh token;
exporting a tax statement revokes *every* token for that user (unless
EXPORT_TRAP=0). Every token carries its sign-in time, and both token types
stop working SESSION_MAX_SECONDS after sign-in, however often they are refreshed.
"""

import os
import secrets
import sys
import time
import uuid
from pathlib import Path

SHARED = Path(__file__).resolve().parent.parent.parent / "shared"
if not SHARED.exists():  # inside Docker the shared core is copied to /shared
    SHARED = Path("/shared")
sys.path.insert(0, str(SHARED))

import jwt  # noqa: E402
from fastapi import Body, Depends, FastAPI, Request  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import Response  # noqa: E402

from gowork_core import db, services as svc  # noqa: E402
from gowork_core.api import build_public_router, build_router, install_error_handlers  # noqa: E402
from gowork_core.constants import EXPORT_TRAP, SESSION_IDLE_MINUTES, SESSION_MAX_SECONDS, session_too_old  # noqa: E402

ACCESS_MINUTES = int(os.environ.get("ACCESS_TOKEN_MINUTES", "10"))
REFRESH_MINUTES = SESSION_IDLE_MINUTES  # sliding: each refresh issues a fresh refresh token
SECRET = os.environ.get("JWT_SECRET") or secrets.token_hex(32)
REVOKED_REFRESH = set()  # jti of refresh tokens that were used or logged out

app = FastAPI(title="GoWork API", docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("CORS_ORIGINS", "http://localhost:8003").split(","),
    allow_methods=["*"],
    allow_headers=["Authorization", "Content-Type"],
)
install_error_handlers(app)
db.init_db()


class Unauthorized(svc.ServiceError):
    status = 401

    def __init__(self, message="Your session has expired. Please sign in again."):
        super().__init__(message)


def _issue_tokens(user, auth_at=None):
    now = int(time.time())
    auth_at = now if auth_at is None else auth_at   # refreshes keep the original sign-in time
    claims = {"sub": str(user["id"]), "ver": user["token_version"], "iat": now, "auth": auth_at}

    def expiry(minutes):
        exp = now + minutes * 60
        return min(exp, auth_at + SESSION_MAX_SECONDS) if SESSION_MAX_SECONDS > 0 else exp

    access_exp = expiry(ACCESS_MINUTES)
    access = jwt.encode({**claims, "type": "access", "exp": access_exp}, SECRET, "HS256")
    refresh = jwt.encode({**claims, "type": "refresh", "jti": uuid.uuid4().hex, "exp": expiry(REFRESH_MINUTES)},
                         SECRET, "HS256")
    public = {k: v for k, v in user.items() if k != "token_version"}
    return {"access_token": access, "refresh_token": refresh, "token_type": "bearer",
            "expires_in": access_exp - now, "user": public}


def _decode(token, kind):
    try:
        payload = jwt.decode(token or "", SECRET, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise Unauthorized()
    if payload.get("type") != kind:
        raise Unauthorized()
    # Crawler trap: the session is revoked SESSION_MAX_SECONDS after sign-in, refreshed or not
    if session_too_old(payload.get("auth", 0), time.time()):
        raise Unauthorized()
    return payload


def _user_for(conn, payload):
    user = svc.get_user(conn, int(payload["sub"]))
    if user is None or user["token_version"] != payload["ver"]:
        raise Unauthorized()
    return user


def current_user(request: Request, conn=Depends(db.get_conn)):
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        raise Unauthorized("Sign in to continue.")
    return _user_for(conn, _decode(header[7:], "access"))


@app.post("/api/auth/login")
def login(data: dict = Body(...), conn=Depends(db.get_conn)):
    user = svc.authenticate(conn, data.get("username"), data.get("password"))
    if user is None:
        raise Unauthorized("Incorrect username or password.")
    return _issue_tokens(svc.get_user(conn, user["id"]))


@app.post("/api/auth/register", status_code=201)
def register(data: dict = Body(...), conn=Depends(db.get_conn)):
    return _issue_tokens(svc.get_user(conn, svc.register(conn, data)))


@app.post("/api/auth/refresh")
def refresh(data: dict = Body(...), conn=Depends(db.get_conn)):
    payload = _decode(data.get("refresh_token"), "refresh")
    if payload["jti"] in REVOKED_REFRESH:
        raise Unauthorized()
    user = _user_for(conn, payload)
    REVOKED_REFRESH.add(payload["jti"])  # rotation: each refresh token works once
    return _issue_tokens(user, auth_at=payload["auth"])


@app.post("/api/auth/logout")
def logout(data: dict = Body(default={})):
    try:
        REVOKED_REFRESH.add(_decode(data.get("refresh_token"), "refresh")["jti"])
    except Unauthorized:
        pass  # already invalid - logging out is still a success
    return {"status": "signed out"}


@app.get("/api/export-taxes")
def export_taxes(year: str = "", user=Depends(current_user), conn=Depends(db.get_conn)):
    # Crawler trap: the download revokes every access and refresh token for this user (unless EXPORT_TRAP=0).
    filename, pdf = svc.tax_statement(conn, user, year)
    if EXPORT_TRAP:
        svc.bump_token_version(conn, user["id"])
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


app.include_router(build_public_router())
app.include_router(build_router(current_user))
