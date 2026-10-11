"""Business rules shared by all three sites. Functions take a sqlite3
connection plus the acting user (a dict) and raise ServiceError subclasses
that each web layer turns into its own error page / JSON response."""

import calendar as _calendar
import math
import os
import re
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

from . import db
from .constants import (
    CLAIM_CATEGORIES, CLAIM_MAX_CENTS, CLAIM_STATUSES, DEPARTMENTS, ENTITLEMENTS, INVITE_CODES, LANGUAGES,
    LEAVE_STATUSES,
    LEAVE_TYPES, RECEIPT_EXTENSIONS, RECEIPT_MAX_BYTES, RECEIPT_REQUIRED_OVER_CENTS, ROLES,
)
from .pdf import make_pdf
from .security import hash_password, verify_password


class ServiceError(Exception):
    status = 400

    def __init__(self, message="Bad request", errors=None):
        super().__init__(message)
        self.message = message
        self.errors = errors or {}


class NotFound(ServiceError):
    status = 404

    def __init__(self, message="Not found"):
        super().__init__(message)


class Forbidden(ServiceError):
    status = 403

    def __init__(self, message="You don't have access to this page."):
        super().__init__(message)


class Invalid(ServiceError):
    status = 422

    def __init__(self, errors, message="Please fix the highlighted fields."):
        super().__init__(message, errors)


# --- helpers --------------------------------------------------------------------

USER_FIELDS = ("id, username, full_name, email, role, department, job_title, manager_id, phone, location, bio,"
               " joined_on, avatar_color, active, pref_email_notifications, pref_weekly_digest, pref_language")


def money(cents):
    return f"${cents / 100:,.2f}"


def initials(name):
    parts = name.split()
    return (parts[0][0] + (parts[-1][0] if len(parts) > 1 else "")).upper()


def _user_dict(row):
    if row is None:
        return None
    user = dict(row)
    user.pop("password_hash", None)
    user["initials"] = initials(user["full_name"])
    user["role_label"] = ROLES[user["role"]]
    return user


def _int(value, default=1, low=1, high=None):
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    number = max(low, number)
    return min(number, high) if high else number


def _parse_date(value):
    try:
        return date.fromisoformat(str(value).strip())
    except (TypeError, ValueError):
        return None


def paginate(conn, sql, params, page, per_page):
    """Out-of-range pages return an empty page with HTTP 200 (soft-404 trap)."""
    total = conn.execute(f"SELECT COUNT(*) FROM ({sql})", params).fetchone()[0]
    page = _int(page)
    rows = conn.execute(f"{sql} LIMIT ? OFFSET ?", [*params, per_page, (page - 1) * per_page]).fetchall()
    return {
        "items": [dict(r) for r in rows],
        "page": page,
        "pages": max(1, math.ceil(total / per_page)),
        "per_page": per_page,
        "total": total,
    }


def _order(sort, order, allowed, default, id_column):
    column = allowed.get(sort, allowed[default])
    direction = "ASC" if order == "asc" else "DESC"
    return f" ORDER BY {column} {direction}, {id_column} DESC"


def require_role(user, *roles):
    if user["role"] not in roles:
        raise Forbidden()


# --- auth & users ---------------------------------------------------------------

def authenticate(conn, username, password):
    row = conn.execute("SELECT * FROM users WHERE username = ?", ((username or "").strip().lower(),)).fetchone()
    if row is None or not row["active"] or not verify_password(password or "", row["password_hash"]):
        return None
    return _user_dict(row)


def get_user(conn, user_id):
    """Fetch an active user by id (used to load the session user)."""
    row = conn.execute(f"SELECT {USER_FIELDS}, token_version FROM users WHERE id = ? AND active = 1",
                       (user_id,)).fetchone()
    return _user_dict(row)


def bump_token_version(conn, user_id):
    conn.execute("UPDATE users SET token_version = token_version + 1 WHERE id = ?", (user_id,))
    conn.commit()


# --- dashboard & announcements --------------------------------------------------

def dashboard(conn, user):
    today = date.today().isoformat()
    data = {
        "balances": leave_balances(conn, user["id"]),
        "pending_leaves": conn.execute(
            "SELECT COUNT(*) FROM leaves WHERE user_id = ? AND status = 'Pending'", (user["id"],)).fetchone()[0],
        "pending_claims": conn.execute(
            "SELECT COUNT(*) FROM claims WHERE user_id = ? AND status = 'Pending'", (user["id"],)).fetchone()[0],
        "pending_claims_amount": money(conn.execute(
            "SELECT COALESCE(SUM(amount_cents), 0) FROM claims WHERE user_id = ? AND status = 'Pending'",
            (user["id"],)).fetchone()[0]),
        "upcoming_leave": _row(conn.execute(
            "SELECT * FROM leaves WHERE user_id = ? AND status = 'Approved' AND start_date >= ?"
            " ORDER BY start_date LIMIT 1", (user["id"], today)).fetchone()),
        "recent_leaves": [dict(r) for r in conn.execute(
            "SELECT * FROM leaves WHERE user_id = ? ORDER BY created_at DESC LIMIT 5", (user["id"],))],
        "recent_claims": [_claim_extra(dict(r)) for r in conn.execute(
            "SELECT * FROM claims WHERE user_id = ? ORDER BY created_at DESC LIMIT 5", (user["id"],))],
        "out_today": [dict(r) for r in conn.execute(
            "SELECT u.id, u.full_name, u.job_title, u.avatar_color, l.leave_type, l.end_date FROM leaves l"
            " JOIN users u ON u.id = l.user_id WHERE l.status = 'Approved' AND l.start_date <= ?"
            " AND l.end_date >= ? AND u.active = 1 ORDER BY u.full_name", (today, today))],
        "approvals_waiting": None,
    }
    for person in data["out_today"]:
        person["initials"] = initials(person["full_name"])
    if user["role"] in ("manager", "hr_admin"):
        approvals = pending_approvals(conn, user)
        data["approvals_waiting"] = len(approvals["leaves"]) + len(approvals["claims"])
    return data


def list_announcements(conn, limit=10):
    rows = conn.execute(
        "SELECT a.id, a.title, a.summary, a.created_at, a.pinned, u.full_name AS author_name FROM announcements a"
        " JOIN users u ON u.id = a.author_id ORDER BY a.pinned DESC, a.created_at DESC LIMIT ?", (limit,))
    return [dict(r) for r in rows]


def get_announcement(conn, announcement_id):
    row = conn.execute(
        "SELECT a.*, u.full_name AS author_name, u.job_title AS author_title FROM announcements a"
        " JOIN users u ON u.id = a.author_id WHERE a.id = ?", (announcement_id,)).fetchone()
    if row is None:
        raise NotFound("Announcement not found")
    return dict(row)


def _row(row):
    return dict(row) if row else None


# --- leave ----------------------------------------------------------------------

LEAVE_SQL = (
    "SELECT l.*, u.full_name AS owner_name, u.manager_id AS owner_manager_id, a.full_name AS approver_name"
    " FROM leaves l JOIN users u ON u.id = l.user_id LEFT JOIN users a ON a.id = l.approver_id"
)
LEAVE_SORTS = {"start_date": "l.start_date", "created_at": "l.created_at", "days": "l.days", "status": "l.status"}


def leave_balances(conn, user_id, year=None):
    year = str(year or date.today().year)
    balances = []
    for leave_type, entitlement in ENTITLEMENTS.items():
        used = conn.execute(
            "SELECT COALESCE(SUM(days), 0) FROM leaves WHERE user_id = ? AND leave_type = ?"
            " AND status IN ('Approved', 'Pending') AND substr(start_date, 1, 4) = ?",
            (user_id, leave_type, year)).fetchone()[0]
        balances.append({"type": leave_type, "entitlement": entitlement, "used": used,
                         "remaining": entitlement - used})
    return balances


def list_leaves(conn, user, status=None, leave_type=None, sort="start_date", order="desc", page=1, per_page=10):
    sql, params = LEAVE_SQL + " WHERE l.user_id = ?", [user["id"]]
    if status in LEAVE_STATUSES:
        sql += " AND l.status = ?"
        params.append(status)
    if leave_type in LEAVE_TYPES:
        sql += " AND l.leave_type = ?"
        params.append(leave_type)
    sql += _order(sort, order, LEAVE_SORTS, "start_date", "l.id")
    return paginate(conn, sql, params, page, per_page)


def _can_view(user, owner_id, owner_manager_id):
    return owner_id == user["id"] or user["role"] == "hr_admin" or (
        user["role"] == "manager" and owner_manager_id == user["id"])


def get_leave(conn, user, leave_id):
    row = conn.execute(LEAVE_SQL + " WHERE l.id = ?", (leave_id,)).fetchone()
    if row is None:
        raise NotFound("Leave request not found")
    leave = dict(row)
    if not _can_view(user, leave["user_id"], leave["owner_manager_id"]):
        raise NotFound("Leave request not found")  # don't reveal other people's requests exist
    leave["can_cancel"] = _leave_cancellable(user, leave)
    return leave


def _leave_cancellable(user, leave):
    return leave["user_id"] == user["id"] and (
        leave["status"] == "Pending"
        or (leave["status"] == "Approved" and leave["start_date"] > date.today().isoformat()))


def validate_leave(conn, user, data, step=3):
    """Validate the leave wizard up to `step` (1 = type, 2 = dates, 3 = reason)."""
    errors, cleaned = {}, {}
    leave_type = (data.get("leave_type") or "").strip()
    if leave_type not in LEAVE_TYPES:
        errors["leave_type"] = "Choose a leave type."
    cleaned["leave_type"] = leave_type

    if step >= 2:
        start, end = _parse_date(data.get("start_date")), _parse_date(data.get("end_date"))
        today = date.today()
        if not start:
            errors["start_date"] = "Enter a valid start date."
        elif start < today:
            errors["start_date"] = "Start date can't be in the past."
        elif start > today + timedelta(days=365):
            errors["start_date"] = "Leave can only be booked up to 12 months ahead."
        if not end:
            errors["end_date"] = "Enter a valid end date."
        elif start and end < start:
            errors["end_date"] = "End date must be on or after the start date."
        if start and end and "start_date" not in errors and "end_date" not in errors:
            days = db.working_days(start, end)
            if days == 0:
                errors["end_date"] = "The selected dates contain no working days."
            elif days > 30:
                errors["end_date"] = "A single request can't exceed 30 working days."
            elif leave_type in ENTITLEMENTS:
                balance = next(b for b in leave_balances(conn, user["id"], start.year) if b["type"] == leave_type)
                if days > balance["remaining"]:
                    errors["end_date"] = (f"Only {balance['remaining']} {leave_type.lower()} day(s) left in"
                                          f" {start.year}; this request needs {days}.")
            overlap = conn.execute(
                "SELECT id FROM leaves WHERE user_id = ? AND status IN ('Pending', 'Approved')"
                " AND start_date <= ? AND end_date >= ?", (user["id"], end.isoformat(), start.isoformat())).fetchone()
            if overlap and "end_date" not in errors:
                errors["start_date"] = f"These dates overlap with leave request #{overlap['id']}."
            cleaned.update(start_date=start.isoformat(), end_date=end.isoformat(), days=days)

    if step >= 3:
        reason = (data.get("reason") or "").strip()
        if not 5 <= len(reason) <= 500:
            errors["reason"] = "Reason must be between 5 and 500 characters."
        cleaned["reason"] = reason

    if errors:
        raise Invalid(errors)
    return cleaned


def create_leave(conn, user, data):
    leave = validate_leave(conn, user, data, step=3)
    cur = conn.execute(
        "INSERT INTO leaves (user_id, leave_type, start_date, end_date, days, reason, status, created_at)"
        " VALUES (?,?,?,?,?,?, 'Pending', ?)",
        (user["id"], leave["leave_type"], leave["start_date"], leave["end_date"], leave["days"], leave["reason"],
         datetime.now().isoformat(timespec="seconds")))
    conn.commit()
    return cur.lastrowid


def cancel_leave(conn, user, leave_id):
    leave = get_leave(conn, user, leave_id)
    if not leave["can_cancel"]:
        raise ServiceError("This leave request can no longer be cancelled.")
    conn.execute("UPDATE leaves SET status = 'Cancelled' WHERE id = ?", (leave_id,))
    conn.commit()


# --- claims ---------------------------------------------------------------------

CLAIM_SQL = (
    "SELECT c.*, u.full_name AS owner_name, u.manager_id AS owner_manager_id, a.full_name AS approver_name"
    " FROM claims c JOIN users u ON u.id = c.user_id LEFT JOIN users a ON a.id = c.approver_id"
)
CLAIM_SORTS = {"claim_date": "c.claim_date", "amount": "c.amount_cents", "created_at": "c.created_at",
               "status": "c.status"}


def _claim_extra(claim):
    claim["amount"] = money(claim["amount_cents"])
    claim.pop("receipt_path", None)
    return claim


def list_claims(conn, user, status=None, category=None, sort="claim_date", order="desc", page=1, per_page=10):
    sql, params = CLAIM_SQL + " WHERE c.user_id = ?", [user["id"]]
    if status in CLAIM_STATUSES:
        sql += " AND c.status = ?"
        params.append(status)
    if category in CLAIM_CATEGORIES:
        sql += " AND c.category = ?"
        params.append(category)
    sql += _order(sort, order, CLAIM_SORTS, "claim_date", "c.id")
    result = paginate(conn, sql, params, page, per_page)
    result["items"] = [_claim_extra(c) for c in result["items"]]
    result["total_amount"] = money(conn.execute(
        "SELECT COALESCE(SUM(amount_cents), 0) FROM claims WHERE user_id = ? AND status = 'Approved'"
        " AND substr(claim_date, 1, 4) = ?", (user["id"], str(date.today().year))).fetchone()[0])
    return result


def _get_claim_row(conn, user, claim_id):
    row = conn.execute(CLAIM_SQL + " WHERE c.id = ?", (claim_id,)).fetchone()
    if row is None or not _can_view(user, row["user_id"], row["owner_manager_id"]):
        raise NotFound("Claim not found")
    return dict(row)


def get_claim(conn, user, claim_id):
    claim = _get_claim_row(conn, user, claim_id)
    claim["can_delete"] = claim["user_id"] == user["id"] and claim["status"] == "Pending"
    return _claim_extra(claim)


def validate_claim(data, receipt_name=None, receipt_size=0):
    errors = {}
    category = (data.get("category") or "").strip()
    subcategory = (data.get("subcategory") or "").strip()
    if category not in CLAIM_CATEGORIES:
        errors["category"] = "Choose a category."
    elif subcategory not in CLAIM_CATEGORIES[category]:
        errors["subcategory"] = "Choose a sub-category."

    amount_cents = 0
    try:
        amount = Decimal(str(data.get("amount") or "").replace(",", "").replace("$", "").strip())
        if amount != amount.quantize(Decimal("0.01")):
            raise InvalidOperation
        amount_cents = int(amount * 100)
        if not 1 <= amount_cents <= CLAIM_MAX_CENTS:
            errors["amount"] = f"Amount must be between $0.01 and {money(CLAIM_MAX_CENTS)}."
    except InvalidOperation:
        errors["amount"] = "Enter an amount like 42.50."

    claim_date = _parse_date(data.get("claim_date"))
    today = date.today()
    if not claim_date:
        errors["claim_date"] = "Enter a valid date."
    elif claim_date > today:
        errors["claim_date"] = "The expense date can't be in the future."
    elif claim_date < today - timedelta(days=90):
        errors["claim_date"] = "Claims must be submitted within 90 days of the expense."

    description = (data.get("description") or "").strip()
    if not 5 <= len(description) <= 300:
        errors["description"] = "Description must be between 5 and 300 characters."

    if receipt_name:
        if os.path.splitext(receipt_name)[1].lower() not in RECEIPT_EXTENSIONS:
            errors["receipt"] = "Receipt must be a PDF, PNG or JPG file."
        elif receipt_size > RECEIPT_MAX_BYTES:
            errors["receipt"] = "Receipt must be 5 MB or smaller."
    elif amount_cents > RECEIPT_REQUIRED_OVER_CENTS:
        errors["receipt"] = f"A receipt is required for claims above {money(RECEIPT_REQUIRED_OVER_CENTS)}."

    if errors:
        raise Invalid(errors)
    return {"category": category, "subcategory": subcategory, "amount_cents": amount_cents,
            "claim_date": claim_date.isoformat(), "description": description}


def create_claim(conn, user, data, receipt_name=None, receipt_bytes=None):
    claim = validate_claim(data, receipt_name, len(receipt_bytes or b""))
    receipt_path = None
    if receipt_name:
        receipt_name = re.sub(r"[^A-Za-z0-9._-]", "_", os.path.basename(receipt_name))[-80:]
        receipt_path = os.path.join(db.UPLOAD_DIR, f"{uuid.uuid4().hex}_{receipt_name}")
        with open(receipt_path, "wb") as f:
            f.write(receipt_bytes)
    cur = conn.execute(
        "INSERT INTO claims (user_id, category, subcategory, amount_cents, claim_date, description, receipt_name,"
        " receipt_path, status, created_at) VALUES (?,?,?,?,?,?,?,?, 'Pending', ?)",
        (user["id"], claim["category"], claim["subcategory"], claim["amount_cents"], claim["claim_date"],
         claim["description"], receipt_name, receipt_path, datetime.now().isoformat(timespec="seconds")))
    conn.commit()
    return cur.lastrowid


def delete_claim(conn, user, claim_id):
    claim = _get_claim_row(conn, user, claim_id)
    if claim["user_id"] != user["id"] or claim["status"] != "Pending":
        raise ServiceError("Only your own pending claims can be deleted.")
    if claim["receipt_path"] and os.path.exists(claim["receipt_path"]):
        os.remove(claim["receipt_path"])
    conn.execute("DELETE FROM claims WHERE id = ?", (claim_id,))
    conn.commit()


def claim_receipt(conn, user, claim_id):
    """Return (filename, bytes, media_type). Seeded claims get a generated placeholder PDF."""
    claim = _get_claim_row(conn, user, claim_id)
    if not claim["receipt_name"]:
        raise NotFound("This claim has no receipt")
    if claim["receipt_path"] and os.path.exists(claim["receipt_path"]):
        with open(claim["receipt_path"], "rb") as f:
            content = f.read()
    else:
        content = make_pdf([
            "GoWork Expense Receipt", "", f"Claim #{claim['id']} - {claim['owner_name']}",
            f"{claim['category']} / {claim['subcategory']}", f"Date: {claim['claim_date']}",
            f"Amount: {money(claim['amount_cents'])}", f"Description: {claim['description']}",
        ])
    ext = os.path.splitext(claim["receipt_name"])[1].lower()
    media_type = {".pdf": "application/pdf", ".png": "image/png"}.get(ext, "image/jpeg")
    return claim["receipt_name"], content, media_type


# --- directory & calendar -------------------------------------------------------

def directory(conn, q="", department=None, page=1, per_page=12):
    sql = (f"SELECT {USER_FIELDS} FROM users WHERE active = 1")
    params = []
    q = (q or "").strip()
    if q:
        sql += " AND (full_name LIKE ? OR job_title LIKE ? OR department LIKE ? OR username LIKE ?)"
        params += [f"%{q}%"] * 4
    if department in DEPARTMENTS:
        sql += " AND department = ?"
        params.append(department)
    sql += " ORDER BY full_name, id"
    result = paginate(conn, sql, params, page, per_page)
    result["items"] = [_public_profile(_user_dict(u)) for u in result["items"]]
    result["q"], result["department"] = q, department if department in DEPARTMENTS else None
    return result


def _public_profile(user):
    for private in ("pref_email_notifications", "pref_weekly_digest", "pref_language"):
        user.pop(private, None)
    return user


def get_profile(conn, user_id):
    row = conn.execute(f"SELECT {USER_FIELDS} FROM users WHERE id = ? AND active = 1", (user_id,)).fetchone()
    if row is None:
        raise NotFound("Employee not found")
    profile = _public_profile(_user_dict(row))
    manager = conn.execute("SELECT id, full_name, job_title FROM users WHERE id = ?",
                           (profile["manager_id"],)).fetchone()
    profile["manager"] = dict(manager) if manager else None
    profile["reports"] = [dict(r) for r in conn.execute(
        "SELECT id, full_name, job_title FROM users WHERE manager_id = ? AND active = 1 ORDER BY full_name",
        (user_id,))]
    return profile


def calendar_month(conn, month=None):
    """Team calendar. prev/next links continue forever (crawler trap)."""
    try:
        year, mon = (int(p) for p in str(month).split("-"))
        if not 1000 <= year <= 9998:
            raise ValueError
        first = date(year, mon, 1)
    except (TypeError, ValueError):
        today = date.today()
        first = date(today.year, today.month, 1)
    days_in_month = _calendar.monthrange(first.year, first.month)[1]
    last = first.replace(day=days_in_month)
    rows = conn.execute(
        "SELECT l.user_id, l.leave_type, l.start_date, l.end_date, u.full_name FROM leaves l"
        " JOIN users u ON u.id = l.user_id WHERE l.status = 'Approved' AND u.active = 1"
        " AND l.start_date <= ? AND l.end_date >= ? ORDER BY u.full_name",
        (last.isoformat(), first.isoformat())).fetchall()

    weeks = []
    for week in _calendar.Calendar().monthdatescalendar(first.year, first.month):
        cells = []
        for d in week:
            iso = d.isoformat()
            entries = [{"user_id": r["user_id"], "name": r["full_name"], "leave_type": r["leave_type"]}
                       for r in rows if r["start_date"] <= iso <= r["end_date"] and d.weekday() < 5]
            cells.append({"date": iso, "day": d.day, "in_month": d.month == first.month,
                          "today": d == date.today(), "entries": entries})
        weeks.append(cells)

    prev_month = (first - timedelta(days=1)).replace(day=1) if (first.year, first.month) > (1000, 1) else None
    next_month = last + timedelta(days=1) if (last.year, last.month) < (9998, 12) else None
    return {
        "month": f"{first:%Y-%m}",
        "label": f"{_calendar.month_name[first.month]} {first.year}",
        "prev": f"{prev_month:%Y-%m}" if prev_month else None,
        "next": f"{next_month:%Y-%m}" if next_month else None,
        "weeks": weeks,
        "total": len(rows),
    }


# --- my profile -----------------------------------------------------------------

def update_profile(conn, user, data):
    errors = {}
    phone = (data.get("phone") or "").strip()
    location = (data.get("location") or "").strip()
    bio = (data.get("bio") or "").strip()
    if not re.fullmatch(r"\+?[0-9 ]{8,16}", phone):
        errors["phone"] = "Enter a phone number like +65 9123 4567."
    if len(location) > 60:
        errors["location"] = "Location must be 60 characters or fewer."
    if len(bio) > 300:
        errors["bio"] = "Bio must be 300 characters or fewer."
    if errors:
        raise Invalid(errors)
    conn.execute("UPDATE users SET phone = ?, location = ?, bio = ? WHERE id = ?", (phone, location, bio, user["id"]))
    conn.commit()


def change_password(conn, user, data):
    errors = {}
    row = conn.execute("SELECT password_hash FROM users WHERE id = ?", (user["id"],)).fetchone()
    current, new, confirm = data.get("current_password") or "", data.get("new_password") or "", data.get(
        "confirm_password") or ""
    if not verify_password(current, row["password_hash"]):
        errors["current_password"] = "Current password is incorrect."
    if password_problem(new):
        errors["new_password"] = password_problem(new)
    elif new == current:
        errors["new_password"] = "New password must be different from the current one."
    if new != confirm:
        errors["confirm_password"] = "Passwords don't match."
    if errors:
        raise Invalid(errors)
    conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (hash_password(new), user["id"]))
    conn.commit()


def update_preferences(conn, user, data):
    language = data.get("pref_language") or "en"
    if language not in LANGUAGES:
        raise Invalid({"pref_language": "Choose a language."})
    conn.execute(
        "UPDATE users SET pref_email_notifications = ?, pref_weekly_digest = ?, pref_language = ? WHERE id = ?",
        (1 if _truthy(data.get("pref_email_notifications")) else 0,
         1 if _truthy(data.get("pref_weekly_digest")) else 0, language, user["id"]))
    conn.commit()


def _truthy(value):
    return value in (True, 1, "1", "on", "true", "yes")


def tax_statement(conn, user, year=None):
    year = _int(year, default=date.today().year - 1, low=2000, high=date.today().year)
    salary = 4200_00 + (user["id"] * 37_131) % 6000_00
    lines = [
        "GoWork Pte Ltd", f"Form IR8A - Year of Assessment {year + 1}", "",
        f"Employee: {user['full_name']} (ID {user['id']:05d})", f"Department: {user['department']}",
        f"Designation: {user['job_title']}", "",
        f"Gross salary ({year}): {money(salary * 12)}", f"Bonus: {money(salary)}",
        f"CPF employee contributions: {money(int(salary * 12 * 0.2))}", "",
        "This statement was generated electronically and does not require a signature.",
    ]
    return f"IR8A_{year}_{user['username']}.pdf", make_pdf(lines)


# --- approvals (manager / HR admin) ---------------------------------------------

def _team_filter(user, alias):
    if user["role"] == "hr_admin":
        return f"{alias}.user_id != ?", [user["id"]]
    return "u.manager_id = ?", [user["id"]]


def pending_approvals(conn, user):
    require_role(user, "manager", "hr_admin")
    where, params = _team_filter(user, "l")
    leaves = [dict(r) for r in conn.execute(
        LEAVE_SQL + f" WHERE l.status = 'Pending' AND u.active = 1 AND {where} ORDER BY l.start_date", params)]
    where, params = _team_filter(user, "c")
    claims = [_claim_extra(dict(r)) for r in conn.execute(
        CLAIM_SQL + f" WHERE c.status = 'Pending' AND u.active = 1 AND {where} ORDER BY c.created_at", params)]
    return {"leaves": leaves, "claims": claims}


def decide(conn, user, kind, item_id, action, comment=""):
    require_role(user, "manager", "hr_admin")
    if kind not in ("leave", "claim"):
        raise NotFound()
    table = "leaves" if kind == "leave" else "claims"
    sql = (LEAVE_SQL + " WHERE l.id = ?") if kind == "leave" else (CLAIM_SQL + " WHERE c.id = ?")
    item = conn.execute(sql, (item_id,)).fetchone()
    if item is None or item["user_id"] == user["id"] or not _can_view(user, item["user_id"], item["owner_manager_id"]):
        raise NotFound(f"{kind.title()} not found")
    if item["status"] != "Pending":
        raise ServiceError(f"This {kind} has already been {item['status'].lower()}.")
    comment = (comment or "").strip()
    errors = {}
    if action not in ("approve", "reject"):
        errors["action"] = "Choose approve or reject."
    if action == "reject" and not 3 <= len(comment) <= 300:
        errors["comment"] = "Give a reason (3-300 characters) when rejecting."
    if len(comment) > 300:
        errors["comment"] = "Comment must be 300 characters or fewer."
    if errors:
        raise Invalid(errors)
    conn.execute(
        f"UPDATE {table} SET status = ?, approver_id = ?, decided_at = ?, decision_comment = ? WHERE id = ?",
        ("Approved" if action == "approve" else "Rejected", user["id"], datetime.now().isoformat(timespec="seconds"),
         comment, item_id))
    conn.commit()


# --- user administration (HR admin) ---------------------------------------------

def list_users(conn, user, q="", role=None, status="active", page=1, per_page=15):
    require_role(user, "hr_admin")
    sql = (f"SELECT {USER_FIELDS} FROM users WHERE 1 = 1")
    params = []
    q = (q or "").strip()
    if q:
        sql += " AND (full_name LIKE ? OR username LIKE ? OR email LIKE ?)"
        params += [f"%{q}%"] * 3
    if role in ROLES:
        sql += " AND role = ?"
        params.append(role)
    if status in ("active", "inactive"):
        sql += " AND active = ?"
        params.append(1 if status == "active" else 0)
    sql += " ORDER BY full_name, id"
    result = paginate(conn, sql, params, page, per_page)
    result["items"] = [_user_dict(u) for u in result["items"]]
    return result


def get_user_admin(conn, user, user_id):
    require_role(user, "hr_admin")
    row = conn.execute(f"SELECT {USER_FIELDS} FROM users WHERE id = ?", (user_id,)).fetchone()
    if row is None:
        raise NotFound("User not found")
    return _user_dict(row)


def username_problem(conn, username):
    if not re.fullmatch(r"[a-z][a-z0-9._]{2,19}", username or ""):
        return "3-20 characters: lowercase letters, numbers, dots or underscores."
    if conn.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone():
        return "That username is already taken."
    return None


def password_problem(password):
    if len(password) < 10 or not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        return "Use at least 10 characters with letters and numbers."
    return None


def manager_choices(conn):
    return [dict(r) for r in conn.execute(
        "SELECT id, full_name, department FROM users WHERE role IN ('manager', 'hr_admin') AND active = 1"
        " ORDER BY full_name")]


def _validate_user(conn, data, creating, user_id=None):
    errors = {}
    cleaned = {
        "full_name": (data.get("full_name") or "").strip(),
        "email": (data.get("email") or "").strip().lower(),
        "department": data.get("department") or "",
        "job_title": (data.get("job_title") or "").strip(),
        "role": data.get("role") or "",
        "manager_id": _int(data.get("manager_id"), default=None) if data.get("manager_id") else None,
    }
    if not 2 <= len(cleaned["full_name"]) <= 60:
        errors["full_name"] = "Full name must be 2-60 characters."
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[a-z]{2,}", cleaned["email"]):
        errors["email"] = "Enter a valid email address."
    if cleaned["department"] not in DEPARTMENTS:
        errors["department"] = "Choose a department."
    if not 2 <= len(cleaned["job_title"]) <= 60:
        errors["job_title"] = "Job title must be 2-60 characters."
    if cleaned["role"] not in ROLES:
        errors["role"] = "Choose a role."
    if cleaned["manager_id"] is not None:
        if cleaned["manager_id"] == user_id:
            errors["manager_id"] = "A user can't be their own manager."
        elif cleaned["manager_id"] not in {m["id"] for m in manager_choices(conn)}:
            errors["manager_id"] = "Choose an active manager."
    if creating:
        username = (data.get("username") or "").strip().lower()
        if username_problem(conn, username):
            errors["username"] = username_problem(conn, username)
        password = data.get("temp_password") or ""
        if password_problem(password):
            errors["temp_password"] = password_problem(password)
        cleaned.update(username=username, password_hash=hash_password(password) if not errors else "")
    if errors:
        raise Invalid(errors)
    return cleaned


def _insert_user(conn, u):
    colors = ["#0f766e", "#7c3aed", "#db2777", "#ea580c", "#2563eb"]
    cur = conn.execute(
        "INSERT INTO users (username, password_hash, full_name, email, role, department, job_title, manager_id,"
        " joined_on, avatar_color) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (u["username"], u["password_hash"], u["full_name"], u["email"], u["role"], u["department"], u["job_title"],
         u["manager_id"], date.today().isoformat(), colors[len(u["username"]) % len(colors)]))
    conn.commit()
    return cur.lastrowid


def create_user(conn, user, data):
    require_role(user, "hr_admin")
    return _insert_user(conn, _validate_user(conn, data, creating=True))


def update_user(conn, user, user_id, data):
    get_user_admin(conn, user, user_id)
    u = _validate_user(conn, data, creating=False, user_id=user_id)
    if user_id == user["id"] and u["role"] != "hr_admin":
        raise Invalid({"role": "You can't remove your own HR admin role."})
    conn.execute(
        "UPDATE users SET full_name = ?, email = ?, role = ?, department = ?, job_title = ?, manager_id = ?"
        " WHERE id = ?",
        (u["full_name"], u["email"], u["role"], u["department"], u["job_title"], u["manager_id"], user_id))
    conn.commit()


def set_user_active(conn, user, user_id, active):
    target = get_user_admin(conn, user, user_id)
    if target["id"] == user["id"]:
        raise ServiceError("You can't deactivate your own account.")
    conn.execute("UPDATE users SET active = ?, token_version = token_version + 1 WHERE id = ?",
                 (1 if active else 0, user_id))
    conn.commit()


# --- self-registration (public) -------------------------------------------------

def register_managers(conn, department):
    """Who a new joiner can report to: their department's manager(s), then HR."""
    if department not in DEPARTMENTS:
        return []
    return [dict(r) for r in conn.execute(
        "SELECT id, full_name, job_title, department FROM users WHERE active = 1"
        " AND ((role = 'manager' AND department = ?) OR role = 'hr_admin') ORDER BY role = 'hr_admin', full_name",
        (department,))]


def username_available(conn, username):
    username = (username or "").strip().lower()
    problem = username_problem(conn, username)
    return {"username": username, "available": problem is None, "message": problem or "Username is available."}


def register(conn, data):
    """Create an employee account from the public sign-up form. Returns the new user id."""
    errors = {}
    full_name = (data.get("full_name") or "").strip()
    username = (data.get("username") or "").strip().lower()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    department = data.get("department") or ""
    job_title = (data.get("job_title") or "").strip()
    manager_id = _int(data.get("manager_id"), default=None) if data.get("manager_id") else None
    invite_code = (data.get("invite_code") or "").strip().upper()

    if not 2 <= len(full_name) <= 60:
        errors["full_name"] = "Full name must be 2-60 characters."
    if username_problem(conn, username):
        errors["username"] = username_problem(conn, username)
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[a-z]{2,}", email):
        errors["email"] = "Enter a valid email address."
    elif conn.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone():
        errors["email"] = "An account with this email already exists."
    if password_problem(password):
        errors["password"] = password_problem(password)
    if password != (data.get("confirm_password") or ""):
        errors["confirm_password"] = "Passwords don't match."
    if department not in DEPARTMENTS:
        errors["department"] = "Choose a department."
    if not 2 <= len(job_title) <= 60:
        errors["job_title"] = "Job title must be 2-60 characters."
    if manager_id is None:
        errors["manager_id"] = "Choose who you report to."
    elif department in DEPARTMENTS and manager_id not in {m["id"] for m in register_managers(conn, department)}:
        errors["manager_id"] = "Choose a manager from your department or HR."
    if invite_code not in INVITE_CODES:
        errors["invite_code"] = "That employee ID / invite code isn't valid. Ask HR for yours."
    if not _truthy(data.get("agree_terms")):
        errors["agree_terms"] = "You need to accept the Terms & Privacy notice."
    if errors:
        raise Invalid(errors)
    return _insert_user(conn, {
        "username": username, "password_hash": hash_password(password), "full_name": full_name, "email": email,
        "role": "employee", "department": department, "job_title": job_title, "manager_id": manager_id,
    })
