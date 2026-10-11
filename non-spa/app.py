"""GoWork - Non-SPA edition.

Every page is rendered on the server and every action is a plain HTML form,
so the site works with JavaScript disabled. Sessions are signed Flask cookies
with an idle timeout; every POST form carries a CSRF token.
"""

import os
import secrets
import sys
import time
from datetime import date, datetime
from functools import wraps
from pathlib import Path
from urllib.parse import urlencode

SHARED = Path(__file__).resolve().parent.parent / "shared"
sys.path.insert(0, str(SHARED))

from flask import Flask, Response, abort, flash, g, redirect, render_template, request, session, url_for  # noqa: E402

from gowork_core import db, services as svc  # noqa: E402
from gowork_core.constants import (  # noqa: E402
    CLAIM_CATEGORIES, CLAIM_STATUSES, DEPARTMENTS, ENTITLEMENTS, LANGUAGES, LEAVE_STATUSES, LEAVE_TYPES, ROLES,
    SESSION_IDLE_MINUTES,
)

app = Flask(__name__, static_folder=str(SHARED / "static"), static_url_path="/static")
app.config.update(
    SECRET_KEY=os.environ.get("SECRET_KEY") or secrets.token_hex(32),
    SESSION_COOKIE_NAME="gowork_session",
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    MAX_CONTENT_LENGTH=6 * 1024 * 1024,
)
db.init_db()

PUBLIC_ENDPOINTS = {"login", "register", "terms", "static", "help_page"}


# --- request lifecycle ------------------------------------------------------------

@app.before_request
def load_session():
    g.conn = db.connect()
    g.user = None
    user_id = session.get("user_id")
    if user_id:
        if time.time() - session.get("last_seen", 0) > SESSION_IDLE_MINUTES * 60:
            session.clear()
            if request.endpoint not in PUBLIC_ENDPOINTS:
                return redirect(url_for("login", expired=1))
        else:
            g.user = svc.get_user(g.conn, user_id)
            if g.user is None:  # deactivated while signed in
                session.clear()
            else:
                session["last_seen"] = time.time()
    session.setdefault("csrf", secrets.token_urlsafe(32))
    if request.method == "POST":
        if not secrets.compare_digest(request.form.get("csrf_token", ""), session["csrf"]):
            abort(400, "Your form expired. Go back, refresh the page and try again.")


@app.teardown_request
def close_db(_exc):
    conn = g.pop("conn", None)
    if conn is not None:
        conn.close()


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.user is None:
            return redirect(url_for("login", next=request.full_path.rstrip("?")))
        return view(*args, **kwargs)
    return wrapped


def roles_required(*roles):
    def decorator(view):
        @wraps(view)
        @login_required
        def wrapped(*args, **kwargs):
            if g.user["role"] not in roles:
                abort(403)
            return view(*args, **kwargs)
        return wrapped
    return decorator


def _safe_next(target):
    if target and target.startswith("/") and not target.startswith("//") and "\\" not in target:
        return target
    return url_for("dashboard")


# --- template helpers -------------------------------------------------------------

@app.context_processor
def template_globals():
    def url_with(**changes):
        args = request.args.to_dict()
        for key, value in changes.items():
            if value is None:
                args.pop(key, None)
            else:
                args[key] = value
        return request.path + ("?" + urlencode(args) if args else "")

    return {
        "user": g.get("user"),
        "csrf_token": session.get("csrf", ""),
        "url_with": url_with,
        "random_ref": lambda: secrets.token_hex(4),
        "today": date.today().isoformat(),
        "ROLES": ROLES,
    }


@app.template_filter("fdate")
def format_date(value):
    if not value:
        return "—"
    try:
        if "T" in value:
            return datetime.fromisoformat(value).strftime("%d %b %Y, %H:%M")
        return date.fromisoformat(value).strftime("%d %b %Y")
    except ValueError:
        return value


# --- errors -----------------------------------------------------------------------

@app.errorhandler(svc.ServiceError)
def service_error(error):
    return render_template("error.html", code=error.status, message=error.message), error.status


@app.errorhandler(400)
@app.errorhandler(403)
@app.errorhandler(404)
@app.errorhandler(405)
@app.errorhandler(413)
def http_error(error):
    messages = {
        403: "You don't have access to this page.",
        404: "We couldn't find the page you were looking for.",
        413: "That upload is too large. Receipts must be 5 MB or smaller.",
    }
    message = messages.get(error.code) or error.description
    return render_template("error.html", code=error.code, message=message), error.code


# --- auth -------------------------------------------------------------------------

@app.route("/")
def index():
    return redirect(url_for("dashboard" if g.user else "login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if g.user:
        return redirect(_safe_next(request.args.get("next")))
    error = None
    if request.method == "POST":
        user = svc.authenticate(g.conn, request.form.get("username"), request.form.get("password"))
        if user:
            session.clear()
            session.update(user_id=user["id"], last_seen=time.time(), csrf=secrets.token_urlsafe(32))
            return redirect(_safe_next(request.form.get("next")))
        error = "Incorrect username or password."
    return render_template(
        "login.html", error=error, next=request.values.get("next", ""), username=request.form.get("username", ""),
        expired=request.args.get("expired"),
    ), 401 if error else 200


@app.route("/register", methods=["GET", "POST"])
def register():
    if g.user:
        return redirect(url_for("dashboard"))
    errors, form = {}, request.form
    if request.method == "POST" and request.form.get("action") == "submit":
        try:
            user_id = svc.register(g.conn, request.form)
            session.clear()
            session.update(user_id=user_id, last_seen=time.time(), csrf=secrets.token_urlsafe(32))
            flash(f"Welcome to GoWork, {request.form['full_name'].split()[0]}! Your account is ready.", "success")
            return redirect(url_for("dashboard"))
        except svc.Invalid as e:
            errors = e.errors
    # No JavaScript: the "Reports to" list is refilled by the server when the refresh button is pressed
    return render_template("register.html", form=form, errors=errors, DEPARTMENTS=DEPARTMENTS,
                           managers=svc.register_managers(g.conn, form.get("department"))), 422 if errors else 200


@app.route("/terms")
def terms():
    return render_template("terms.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("You've been signed out.", "success")
    return redirect(url_for("login"))


@app.route("/help")
def help_page():
    return render_template("help.html")


# --- dashboard --------------------------------------------------------------------

@app.route("/dashboard")
@login_required
def dashboard():
    return render_template("dashboard.html", data=svc.dashboard(g.conn, g.user),
                           announcements=svc.list_announcements(g.conn, 5))


@app.route("/export-taxes")
@login_required
def export_taxes():
    # Crawler trap: downloading the tax statement ends the session.
    filename, pdf = svc.tax_statement(g.conn, g.user, request.args.get("year"))
    session.clear()
    return Response(pdf, mimetype="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@app.route("/announcements/<int:announcement_id>")
@login_required
def announcement(announcement_id):
    return render_template("announcement.html", a=svc.get_announcement(g.conn, announcement_id),
                           others=svc.list_announcements(g.conn, 6))


# --- leave ------------------------------------------------------------------------

@app.route("/leave")
@login_required
def leave_list():
    args = request.args
    result = svc.list_leaves(g.conn, g.user, status=args.get("status"), leave_type=args.get("type"),
                             sort=args.get("sort", "start_date"), order=args.get("order", "desc"),
                             page=args.get("page"))
    return render_template("leave_list.html", result=result, balances=svc.leave_balances(g.conn, g.user["id"]),
                           LEAVE_STATUSES=LEAVE_STATUSES, LEAVE_TYPES=LEAVE_TYPES)


@app.route("/leave/<int:leave_id>")
@login_required
def leave_detail(leave_id):
    return render_template("leave_detail.html", leave=svc.get_leave(g.conn, g.user, leave_id))


@app.route("/leave/<int:leave_id>/cancel", methods=["POST"])
@login_required
def leave_cancel(leave_id):
    svc.cancel_leave(g.conn, g.user, leave_id)
    flash("Leave request cancelled.", "success")
    return redirect(url_for("leave_detail", leave_id=leave_id))


WIZARD_FIELDS = {1: ["leave_type"], 2: ["start_date", "end_date"], 3: ["reason"]}


@app.route("/leave/apply", methods=["GET", "POST"])
@login_required
def leave_apply():
    draft = dict(session.get("leave_draft", {}))
    step = svc._int(request.values.get("step"), default=1, high=3)
    errors = {}
    if request.method == "POST":
        draft.update({field: request.form.get(field, "") for field in WIZARD_FIELDS[step]})
        try:
            if step == 3:
                leave_id = svc.create_leave(g.conn, g.user, draft)
                session.pop("leave_draft", None)
                flash("Leave request submitted for approval.", "success")
                return redirect(url_for("leave_detail", leave_id=leave_id))
            svc.validate_leave(g.conn, g.user, draft, step)
            session["leave_draft"] = draft
            return redirect(url_for("leave_apply", step=step + 1))
        except svc.Invalid as e:
            errors = e.errors
    else:
        if request.args.get("reset"):
            session.pop("leave_draft", None)
            draft = {}
        # Don't allow skipping ahead of unfinished steps
        if step >= 2 and not draft.get("leave_type"):
            step = 1
        elif step == 3 and not draft.get("end_date"):
            step = 2
    summary = None
    if step == 3:
        try:
            summary = svc.validate_leave(g.conn, g.user, draft, 2)
        except svc.Invalid:
            summary = None
    return render_template("leave_apply.html", step=step, draft=draft, errors=errors, summary=summary,
                           LEAVE_TYPES=LEAVE_TYPES, ENTITLEMENTS=ENTITLEMENTS,
                           balances={b["type"]: b for b in svc.leave_balances(g.conn, g.user["id"])}), \
        422 if errors else 200


# --- claims -----------------------------------------------------------------------

@app.route("/claims")
@login_required
def claims_list():
    args = request.args
    result = svc.list_claims(g.conn, g.user, status=args.get("status"), category=args.get("category"),
                             sort=args.get("sort", "claim_date"), order=args.get("order", "desc"),
                             page=args.get("page"))
    return render_template("claims_list.html", result=result, CLAIM_STATUSES=CLAIM_STATUSES,
                           CLAIM_CATEGORIES=CLAIM_CATEGORIES)


@app.route("/claims/new", methods=["GET", "POST"])
@login_required
def claim_new():
    form = request.form if request.method == "POST" else request.args
    errors = {}
    if request.method == "POST" and request.form.get("action") == "submit":
        upload = request.files.get("receipt")
        has_file = upload is not None and upload.filename
        try:
            claim_id = svc.create_claim(g.conn, g.user, request.form, upload.filename if has_file else None,
                                        upload.read() if has_file else None)
            flash("Claim submitted for approval.", "success")
            return redirect(url_for("claim_detail", claim_id=claim_id))
        except svc.Invalid as e:
            errors = e.errors
    category = form.get("category", "")
    return render_template("claim_new.html", form=form, errors=errors, CLAIM_CATEGORIES=CLAIM_CATEGORIES,
                           subcategories=CLAIM_CATEGORIES.get(category, [])), 422 if errors else 200


@app.route("/claims/<int:claim_id>")
@login_required
def claim_detail(claim_id):
    return render_template("claim_detail.html", claim=svc.get_claim(g.conn, g.user, claim_id))


@app.route("/claims/<int:claim_id>/receipt")
@login_required
def claim_receipt(claim_id):
    filename, content, media_type = svc.claim_receipt(g.conn, g.user, claim_id)
    return Response(content, mimetype=media_type, headers={"Content-Disposition": f'inline; filename="{filename}"'})


@app.route("/claims/<int:claim_id>/delete", methods=["POST"])
@login_required
def claim_delete(claim_id):
    svc.delete_claim(g.conn, g.user, claim_id)
    flash("Claim deleted.", "success")
    return redirect(url_for("claims_list"))


# --- people -----------------------------------------------------------------------

@app.route("/directory")
@login_required
def directory():
    result = svc.directory(g.conn, request.args.get("q"), request.args.get("department"), request.args.get("page"))
    return render_template("directory.html", result=result, DEPARTMENTS=DEPARTMENTS)


@app.route("/directory/<int:user_id>")
@login_required
def profile_view(user_id):
    return render_template("profile_view.html", p=svc.get_profile(g.conn, user_id))


@app.route("/calendar")
@login_required
def team_calendar():
    return render_template("calendar.html", cal=svc.calendar_month(g.conn, request.args.get("month")))


# --- my profile -------------------------------------------------------------------

@app.route("/profile", methods=["GET", "POST"])
@app.route("/profile/<tab>", methods=["GET", "POST"])
@login_required
def profile(tab="details"):
    if tab not in ("details", "security", "preferences"):
        abort(404)
    errors, form = {}, request.form
    if request.method == "POST":
        action = {"details": svc.update_profile, "security": svc.change_password,
                  "preferences": svc.update_preferences}[tab]
        try:
            action(g.conn, g.user, request.form)
            flash({"details": "Profile updated.", "security": "Password changed.",
                   "preferences": "Preferences saved."}[tab], "success")
            return redirect(request.path)
        except svc.Invalid as e:
            errors = e.errors
    return render_template("profile.html", tab=tab, errors=errors, form=form, LANGUAGES=LANGUAGES,
                           me=svc.get_profile(g.conn, g.user["id"])), 422 if errors else 200


# --- admin ------------------------------------------------------------------------

@app.route("/admin/approvals")
@roles_required("manager", "hr_admin")
def approvals():
    return render_template("approvals.html", data=svc.pending_approvals(g.conn, g.user))


@app.route("/admin/approvals/<kind>/<int:item_id>", methods=["POST"])
@roles_required("manager", "hr_admin")
def approval_decide(kind, item_id):
    action = request.form.get("action")
    try:
        svc.decide(g.conn, g.user, kind, item_id, action, request.form.get("comment"))
        flash(f"{kind.title()} #{item_id} {'approved' if action == 'approve' else 'rejected'}.", "success")
    except svc.Invalid as e:
        flash(next(iter(e.errors.values())), "error")
    return redirect(url_for("approvals"))


@app.route("/admin/users")
@roles_required("hr_admin")
def users():
    args = request.args
    result = svc.list_users(g.conn, g.user, args.get("q"), args.get("role"), args.get("status", "active"),
                            args.get("page"))
    return render_template("users.html", result=result)


@app.route("/admin/users/new", methods=["GET", "POST"])
@app.route("/admin/users/<int:user_id>", methods=["GET", "POST"])
@roles_required("hr_admin")
def user_form(user_id=None):
    target = svc.get_user_admin(g.conn, g.user, user_id) if user_id else None
    errors, form = {}, request.form if request.method == "POST" else (target or {})
    if request.method == "POST":
        try:
            if target:
                svc.update_user(g.conn, g.user, user_id, request.form)
                flash("User updated.", "success")
            else:
                user_id = svc.create_user(g.conn, g.user, request.form)
                flash("User created. Share the temporary password with them securely.", "success")
            return redirect(url_for("user_form", user_id=user_id))
        except svc.Invalid as e:
            errors = e.errors
    return render_template("user_form.html", target=target, form=form, errors=errors, DEPARTMENTS=DEPARTMENTS,
                           managers=svc.manager_choices(g.conn)), 422 if errors else 200


@app.route("/admin/users/<int:user_id>/status", methods=["POST"])
@roles_required("hr_admin")
def user_status(user_id):
    active = request.form.get("active") == "1"
    svc.set_user_active(g.conn, g.user, user_id, active)
    flash("User reactivated." if active else "User deactivated and signed out everywhere.", "success")
    return redirect(url_for("user_form", user_id=user_id))


if __name__ == "__main__":
    app.run(port=8001, debug=True)
