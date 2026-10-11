"""SQLite storage. The database is rebuilt from deterministic seed data on every
start, so every crawler run begins from the same state."""

import os
import random
import sqlite3
import tempfile
from datetime import date, datetime, timedelta

from .constants import CLAIM_CATEGORIES, DEFAULT_PASSWORD, ENTITLEMENTS
from .security import hash_password

DATA_DIR = os.environ.get("GOWORK_DATA_DIR", os.path.join(tempfile.gettempdir(), "gowork"))
DB_PATH = os.path.join(DATA_DIR, "gowork.db")
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")

SCHEMA = """
CREATE TABLE users (
    id INTEGER PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    full_name TEXT NOT NULL,
    email TEXT NOT NULL,
    role TEXT NOT NULL,
    department TEXT NOT NULL,
    job_title TEXT NOT NULL,
    manager_id INTEGER REFERENCES users(id),
    phone TEXT NOT NULL DEFAULT '',
    location TEXT NOT NULL DEFAULT '',
    bio TEXT NOT NULL DEFAULT '',
    joined_on TEXT NOT NULL,
    avatar_color TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,
    pref_email_notifications INTEGER NOT NULL DEFAULT 1,
    pref_weekly_digest INTEGER NOT NULL DEFAULT 0,
    pref_language TEXT NOT NULL DEFAULT 'en',
    token_version INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE leaves (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    leave_type TEXT NOT NULL,
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    days INTEGER NOT NULL,
    reason TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    approver_id INTEGER REFERENCES users(id),
    decided_at TEXT,
    decision_comment TEXT NOT NULL DEFAULT ''
);
CREATE TABLE claims (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    category TEXT NOT NULL,
    subcategory TEXT NOT NULL,
    amount_cents INTEGER NOT NULL,
    claim_date TEXT NOT NULL,
    description TEXT NOT NULL,
    receipt_name TEXT,
    receipt_path TEXT,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    approver_id INTEGER REFERENCES users(id),
    decided_at TEXT,
    decision_comment TEXT NOT NULL DEFAULT ''
);
CREATE TABLE announcements (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    summary TEXT NOT NULL,
    body TEXT NOT NULL,
    author_id INTEGER NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL,
    pinned INTEGER NOT NULL DEFAULT 0
);
"""


def connect():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def get_conn():
    """FastAPI dependency: one connection per request."""
    conn = connect()
    try:
        yield conn
    finally:
        conn.close()


def init_db():
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    for name in os.listdir(UPLOAD_DIR):
        os.remove(os.path.join(UPLOAD_DIR, name))
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    conn = connect()
    conn.executescript(SCHEMA)
    _seed(conn)
    conn.commit()
    conn.close()


# --- Seed data ----------------------------------------------------------------

FIRST_NAMES = [
    "Wei Ling", "Rajesh", "Siti", "Marcus", "Priya", "Jun Hao", "Nurul", "Daniel", "Mei Xin",
    "Arjun", "Farah", "Kenneth", "Hui Min", "Vikram", "Aisha", "Ryan", "Shu Fen", "Harish",
    "Zara", "Benjamin", "Li Ting", "Imran", "Chloe", "Ganesh", "Amanda", "Hafiz", "Rachel",
    "Suresh", "Joanne", "Irfan", "Grace", "Kumar", "Natalie", "Azlan", "Sophia", "Darren",
]
LAST_NAMES = [
    "Tan", "Lim", "Lee", "Ng", "Wong", "Goh", "Chua", "Koh", "Teo", "Ong", "Ho", "Chan", "Yeo",
    "Sim", "Rahman", "Pillai", "Ismail", "Nair", "Abdullah", "Fernandez", "Singh", "Low", "Chong",
]
TITLES = {
    "Engineering": ["Software Engineer", "Senior Software Engineer", "QA Engineer", "DevOps Engineer", "Data Engineer"],
    "Finance": ["Accountant", "Financial Analyst", "Payroll Specialist"],
    "Human Resources": ["HR Executive", "Talent Acquisition Specialist"],
    "Marketing": ["Marketing Executive", "Content Strategist", "Graphic Designer"],
    "Sales": ["Account Executive", "Sales Development Rep", "Account Manager"],
    "Operations": ["Operations Executive", "Facilities Coordinator", "Procurement Officer"],
}
DEPT_WEIGHTS = {"Engineering": 10, "Finance": 4, "Human Resources": 2, "Marketing": 4, "Sales": 6, "Operations": 4}
COLORS = ["#0f766e", "#7c3aed", "#db2777", "#ea580c", "#2563eb", "#16a34a", "#ca8a04", "#0891b2"]
LOCATIONS = ["Singapore HQ · Level 12", "Singapore HQ · Level 14", "Jurong East Office", "Remote"]
BIOS = [
    "Coffee enthusiast and weekend cyclist.",
    "Ask me about our quarterly planning process.",
    "Happy to help new joiners find their way around.",
    "Loves board games, hiking and a good spreadsheet.",
    "Currently learning Japanese. 頑張ります!",
    "",
]
LEAVE_REASONS = {
    "Annual": ["Family holiday", "Trip to Penang", "Personal matters", "Wedding anniversary", "Visiting relatives", "Rest and recharge"],
    "Medical": ["Flu and fever", "Dental surgery", "Medical appointment", "Recovering from minor surgery"],
    "Compassionate": ["Bereavement in the family", "Family emergency"],
    "Unpaid": ["Extended travel", "Further studies"],
}
REJECT_COMMENTS = ["Clashes with the release week.", "Team coverage is too thin on these dates.", "Please resubmit with supporting documents."]
CLAIM_DESCRIPTIONS = {
    "Travel": ["Client visit to Changi Business Park", "Airport transfer for conference", "Site visit", "Regional sales trip"],
    "Meals": ["Dinner with client team", "Late night release support", "Team lunch with partner"],
    "Medical": ["Polyclinic consultation", "Dental check-up", "Physiotherapy session"],
    "Training": ["AWS certification exam", "Online course subscription", "Reference books for project"],
    "Equipment": ["USB-C dock for home office", "Licence renewal", "Stationery for workshop"],
}
CLAIM_RANGES = {"Travel": (8, 900), "Meals": (15, 180), "Medical": (20, 250), "Training": (30, 1200), "Equipment": (10, 450)}
ANNOUNCEMENTS = [
    ("Year-end performance review cycle opens", "Self-reviews are due by the end of the month.",
     "The year-end performance review cycle is now open. Please complete your self-review in the Performance "
     "module and schedule a check-in with your manager. Reviews close at the end of the month.", 2, 1),
    ("New claims policy: receipts above $25", "Receipts are now mandatory for claims above $25.",
     "From this month, every expense claim above $25 must include a receipt (PDF, PNG or JPG, max 5 MB). "
     "Claims without receipts will be returned for resubmission.", 6, 0),
    ("Wellness Week: free health screenings", "Book a slot at the Level 12 pantry.",
     "Wellness Week is back! Free basic health screenings, massage chairs and fruit baskets all week. "
     "Book your screening slot with the HR team.", 11, 0),
    ("IT maintenance this Saturday", "VPN and email unavailable 10pm-2am.",
     "Scheduled maintenance will take VPN, email and the intranet offline between 10pm and 2am on Saturday. "
     "Please save your work before then.", 15, 0),
    ("Welcome our new joiners", "Say hello to the five colleagues who joined this month.",
     "Please join us in welcoming our new colleagues across Engineering, Sales and Operations. "
     "Find them in the Directory and say hello!", 21, 0),
    ("Office closure on public holiday", "Both offices are closed on the public holiday.",
     "Singapore HQ and Jurong East Office will be closed on the upcoming public holiday. "
     "Urgent IT issues can be raised through the help desk hotline.", 30, 0),
]


def working_days(start, end):
    days, d = 0, start
    while d <= end:
        if d.weekday() < 5:
            days += 1
        d += timedelta(days=1)
    return days


def _add_working_days(start, count):
    d, added = start, 1
    while added < count:
        d += timedelta(days=1)
        if d.weekday() < 5:
            added += 1
    return d


def _next_weekday(d):
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def _seed(conn):
    rng = random.Random(2026)
    today = date.today()
    password_hash = lambda: hash_password(DEFAULT_PASSWORD)  # noqa: E731 - per-user salt
    users = []  # (id, role, department, manager_id)

    def add_user(username, full_name, role, department, job_title, manager_id, active=1):
        user_id = len(users) + 1
        joined = date(2016, 1, 1) + timedelta(days=rng.randint(0, 3600))
        conn.execute(
            "INSERT INTO users (id, username, password_hash, full_name, email, role, department, job_title,"
            " manager_id, phone, location, bio, joined_on, avatar_color, active)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (user_id, username, password_hash(), full_name, f"{username}@gowork.example", role, department,
             job_title, manager_id, f"+65 {rng.randint(8000, 9999)} {rng.randint(1000, 9999)}",
             rng.choice(LOCATIONS), rng.choice(BIOS), joined.isoformat(), rng.choice(COLORS), active),
        )
        users.append((user_id, role, department, manager_id))
        return user_id

    carol = add_user("carol", "Carol Tan", "hr_admin", "Human Resources", "HR Director", None)
    bob = add_user("bob", "Bob Lim", "manager", "Engineering", "Engineering Manager", None)
    add_user("alice", "Alice Ng", "employee", "Engineering", "Software Engineer", bob)

    dept_managers = {"Human Resources": carol, "Engineering": bob}
    used_usernames = {"carol", "bob", "alice"}
    name_pool = [(f, l) for f in FIRST_NAMES for l in LAST_NAMES]
    rng.shuffle(name_pool)

    def next_name():
        while True:
            first, last = name_pool.pop()
            username = f"{first.split()[0].lower()}.{last.lower()}"
            if username not in used_usernames:
                used_usernames.add(username)
                return username, f"{first} {last}"

    for dept in ["Finance", "Marketing", "Sales", "Operations"]:
        username, name = next_name()
        dept_managers[dept] = add_user(username, name, "manager", dept, f"{dept} Manager", carol)

    depts = list(DEPT_WEIGHTS)
    for i in range(33):
        dept = rng.choices(depts, weights=list(DEPT_WEIGHTS.values()))[0]
        username, name = next_name()
        add_user(username, name, "employee", dept, rng.choice(TITLES[dept]), dept_managers[dept],
                 active=0 if i in (7, 21) else 1)

    # Leaves
    for user_id, role, _, manager_id in users:
        approver = manager_id or carol
        if user_id == carol:
            approver = bob  # someone has to approve the HR director
        is_alice = user_id == 3
        count = 15 if is_alice else rng.randint(2, 6)
        cursor = today - timedelta(days=400 if is_alice else rng.randint(60, 300))
        used = {}
        has_future_pending = False
        for _ in range(count):
            cursor += timedelta(days=rng.randint(8, 30) if is_alice else rng.randint(10, 45))
            start = _next_weekday(cursor)
            if start > today + timedelta(days=75):
                break
            days = rng.choice([1, 1, 2, 3, 5])
            end = _add_working_days(start, days)
            cursor = end
            leave_type = rng.choices(list(LEAVE_REASONS), weights=[65, 25, 5, 5])[0]
            key = (start.year, leave_type)
            if leave_type in ENTITLEMENTS and used.get(key, 0) + days > ENTITLEMENTS[leave_type]:
                leave_type = "Unpaid"
                key = (start.year, leave_type)
            used[key] = used.get(key, 0) + days
            if start <= today:
                status = rng.choices(["Approved", "Rejected", "Cancelled"], weights=[75, 10, 15])[0]
            else:
                status = rng.choices(["Pending", "Approved"], weights=[70, 30])[0]
            has_future_pending |= status == "Pending"
            _insert_leave(conn, rng, user_id, leave_type, start, end, days, status, approver)
        if is_alice and not has_future_pending:
            start = _next_weekday(max(cursor, today) + timedelta(days=10))
            _insert_leave(conn, rng, user_id, "Annual", start, start, 1, "Pending", approver)

    # Claims
    for user_id, _, _, manager_id in users:
        approver = manager_id or (bob if user_id == carol else carol)
        count = 14 if user_id == 3 else rng.randint(1, 5)
        for _ in range(count):
            claim_date = today - timedelta(days=rng.randint(1, 120))
            category = rng.choice(list(CLAIM_CATEGORIES))
            low, high = CLAIM_RANGES[category]
            amount_cents = rng.randint(low * 100, high * 100)
            if (today - claim_date).days > 14:
                status = rng.choices(["Approved", "Rejected", "Pending"], weights=[70, 15, 15])[0]
            else:
                status = "Pending"
            created = datetime.combine(claim_date + timedelta(days=rng.randint(0, 3)), datetime.min.time())
            decided = (created + timedelta(days=rng.randint(1, 6))).isoformat() if status != "Pending" else None
            conn.execute(
                "INSERT INTO claims (user_id, category, subcategory, amount_cents, claim_date, description,"
                " receipt_name, status, created_at, approver_id, decided_at, decision_comment)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (user_id, category, rng.choice(CLAIM_CATEGORIES[category]), amount_cents, claim_date.isoformat(),
                 rng.choice(CLAIM_DESCRIPTIONS[category]),
                 f"receipt_{claim_date:%Y%m%d}_{rng.randint(100, 999)}.pdf" if amount_cents > 2500 else None,
                 status, created.isoformat(), approver if status != "Pending" else None, decided,
                 rng.choice(REJECT_COMMENTS) if status == "Rejected" else ""),
            )

    for title, summary, body, days_ago, pinned in ANNOUNCEMENTS:
        created = datetime.combine(today - timedelta(days=days_ago), datetime.min.time()) + timedelta(hours=9)
        conn.execute(
            "INSERT INTO announcements (title, summary, body, author_id, created_at, pinned) VALUES (?,?,?,?,?,?)",
            (title, summary, body, carol, created.isoformat(), pinned),
        )


def _insert_leave(conn, rng, user_id, leave_type, start, end, days, status, approver):
    created = datetime.combine(start - timedelta(days=rng.randint(5, 30)), datetime.min.time()) + timedelta(hours=10)
    decided = None
    if status in ("Approved", "Rejected"):
        decided = (created + timedelta(days=rng.randint(1, 4))).isoformat()
    conn.execute(
        "INSERT INTO leaves (user_id, leave_type, start_date, end_date, days, reason, status, created_at,"
        " approver_id, decided_at, decision_comment) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (user_id, leave_type, start.isoformat(), end.isoformat(), days, rng.choice(LEAVE_REASONS[leave_type]),
         status, created.isoformat(), approver if decided else None, decided,
         rng.choice(REJECT_COMMENTS) if status == "Rejected" else ""),
    )
