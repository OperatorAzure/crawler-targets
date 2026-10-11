"""JSON API shared by the hybrid site and the pure-SPA backend.

Each site supplies its own `current_user` dependency (cookie session + CSRF
for hybrid, bearer JWT for the SPA) plus its own /api/auth/* and
/api/export-taxes endpoints.
"""

import time
from typing import Optional

from fastapi import APIRouter, Body, Depends, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse, Response

from . import services as svc
from .constants import CLAIM_CATEGORIES, DEPARTMENTS, ENTITLEMENTS, LANGUAGES, LEAVE_STATUSES, LEAVE_TYPES, ROLES
from .db import get_conn


def install_error_handlers(app):
    @app.exception_handler(svc.ServiceError)
    async def service_error(_request: Request, error: svc.ServiceError):
        return JSONResponse({"detail": error.message, "errors": error.errors}, status_code=error.status)


def build_router(current_user):
    r = APIRouter(prefix="/api")
    Conn = Depends(get_conn)
    User = Depends(current_user)

    @r.get("/meta")
    def meta():
        return {"leave_types": LEAVE_TYPES, "leave_statuses": LEAVE_STATUSES, "entitlements": ENTITLEMENTS,
                "claim_categories": CLAIM_CATEGORIES, "departments": DEPARTMENTS, "roles": ROLES,
                "languages": LANGUAGES}

    @r.get("/me")
    def me(user=User, conn=Conn):
        profile = {**svc.get_profile(conn, user["id"]), **user}
        profile.pop("token_version", None)
        return profile

    @r.put("/me/profile")
    def update_profile(data: dict = Body(...), user=User, conn=Conn):
        svc.update_profile(conn, user, data)
        return {"status": "saved"}

    @r.put("/me/password")
    def change_password(data: dict = Body(...), user=User, conn=Conn):
        svc.change_password(conn, user, data)
        return {"status": "saved"}

    @r.put("/me/preferences")
    def update_preferences(data: dict = Body(...), user=User, conn=Conn):
        svc.update_preferences(conn, user, data)
        return {"status": "saved"}

    @r.get("/dashboard")
    def dashboard(user=User, conn=Conn):
        return svc.dashboard(conn, user)

    @r.get("/announcements")
    def announcements(limit: int = 5, user=User, conn=Conn):
        time.sleep(1.2)  # deliberately slow: content appears well after page load
        return {"items": svc.list_announcements(conn, max(1, min(limit, 20)))}

    @r.get("/announcements/{announcement_id}")
    def announcement(announcement_id: int, user=User, conn=Conn):
        return svc.get_announcement(conn, announcement_id)

    # leave
    @r.get("/leave")
    def leaves(status: Optional[str] = None, type: Optional[str] = None, sort: str = "start_date",
               order: str = "desc", page: int = 1, user=User, conn=Conn):
        return svc.list_leaves(conn, user, status, type, sort, order, page)

    @r.get("/leave/balances")
    def balances(user=User, conn=Conn):
        return {"items": svc.leave_balances(conn, user["id"])}

    @r.post("/leave/validate")
    def validate_leave(data: dict = Body(...), user=User, conn=Conn):
        step = svc._int(data.get("step"), default=3, high=3)
        return {"ok": True, **svc.validate_leave(conn, user, data, step)}

    @r.post("/leave", status_code=201)
    def create_leave(data: dict = Body(...), user=User, conn=Conn):
        return {"id": svc.create_leave(conn, user, data)}

    @r.get("/leave/{leave_id}")
    def leave(leave_id: int, user=User, conn=Conn):
        return svc.get_leave(conn, user, leave_id)

    @r.post("/leave/{leave_id}/cancel")
    def cancel_leave(leave_id: int, user=User, conn=Conn):
        svc.cancel_leave(conn, user, leave_id)
        return {"status": "cancelled"}

    # claims
    @r.get("/claims")
    def claims(status: Optional[str] = None, category: Optional[str] = None, sort: str = "claim_date",
               order: str = "desc", page: int = 1, user=User, conn=Conn):
        return svc.list_claims(conn, user, status, category, sort, order, page)

    @r.get("/claims/categories")
    def categories(user=User):
        return {"items": list(CLAIM_CATEGORIES)}

    @r.get("/claims/categories/{category}")
    def subcategories(category: str, user=User):
        if category not in CLAIM_CATEGORIES:
            raise svc.NotFound("Unknown category")
        return {"items": CLAIM_CATEGORIES[category]}

    @r.post("/claims", status_code=201)
    async def create_claim(category: str = Form(""), subcategory: str = Form(""), amount: str = Form(""),
                           claim_date: str = Form(""), description: str = Form(""),
                           receipt: Optional[UploadFile] = File(None), user=User, conn=Conn):
        content = await receipt.read() if receipt and receipt.filename else None
        data = {"category": category, "subcategory": subcategory, "amount": amount, "claim_date": claim_date,
                "description": description}
        return {"id": svc.create_claim(conn, user, data, receipt.filename if content is not None else None, content)}

    @r.get("/claims/{claim_id}")
    def claim(claim_id: int, user=User, conn=Conn):
        return svc.get_claim(conn, user, claim_id)

    @r.get("/claims/{claim_id}/receipt")
    def receipt(claim_id: int, user=User, conn=Conn):
        filename, content, media_type = svc.claim_receipt(conn, user, claim_id)
        return Response(content, media_type=media_type,
                        headers={"Content-Disposition": f'inline; filename="{filename}"'})

    @r.delete("/claims/{claim_id}")
    def delete_claim(claim_id: int, user=User, conn=Conn):
        svc.delete_claim(conn, user, claim_id)
        return {"status": "deleted"}

    # people
    @r.get("/directory")
    def directory(q: str = "", department: Optional[str] = None, page: int = 1, user=User, conn=Conn):
        return svc.directory(conn, q, department, page)

    @r.get("/directory/{user_id}")
    def profile(user_id: int, user=User, conn=Conn):
        return svc.get_profile(conn, user_id)

    @r.get("/calendar")
    def calendar(month: Optional[str] = None, user=User, conn=Conn):
        return svc.calendar_month(conn, month)

    # admin
    @r.get("/admin/approvals")
    def approvals(user=User, conn=Conn):
        return svc.pending_approvals(conn, user)

    @r.post("/admin/approvals/{kind}/{item_id}")
    def decide(kind: str, item_id: int, data: dict = Body(...), user=User, conn=Conn):
        svc.decide(conn, user, kind, item_id, data.get("action"), data.get("comment"))
        return {"status": "saved"}

    @r.get("/admin/users")
    def users(q: str = "", role: Optional[str] = None, status: str = "active", page: int = 1, user=User,
              conn=Conn):
        return svc.list_users(conn, user, q, role, status, page)

    @r.get("/admin/managers")
    def managers(user=User, conn=Conn):
        svc.require_role(user, "hr_admin")
        return {"items": svc.manager_choices(conn)}

    @r.post("/admin/users", status_code=201)
    def create_user(data: dict = Body(...), user=User, conn=Conn):
        return {"id": svc.create_user(conn, user, data)}

    @r.get("/admin/users/{user_id}")
    def admin_user(user_id: int, user=User, conn=Conn):
        return svc.get_user_admin(conn, user, user_id)

    @r.put("/admin/users/{user_id}")
    def update_user(user_id: int, data: dict = Body(...), user=User, conn=Conn):
        svc.update_user(conn, user, user_id, data)
        return {"status": "saved"}

    @r.post("/admin/users/{user_id}/status")
    def user_status(user_id: int, data: dict = Body(...), user=User, conn=Conn):
        svc.set_user_active(conn, user, user_id, bool(data.get("active")))
        return {"status": "saved"}

    return r


def build_public_router():
    """Unauthenticated helpers used by the sign-up page (no session needed)."""
    r = APIRouter(prefix="/api/auth")
    Conn = Depends(get_conn)

    @r.get("/username-available")
    def username_available(username: str = "", conn=Conn):
        return svc.username_available(conn, username)

    @r.get("/register/managers")
    def register_managers(department: str = "", conn=Conn):
        return {"items": svc.register_managers(conn, department)}

    return r
