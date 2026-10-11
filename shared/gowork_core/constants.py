import os

ROLES = {
    "employee": "Employee",
    "manager": "Manager",
    "hr_admin": "HR Admin",
}

DEPARTMENTS = ["Engineering", "Finance", "Human Resources", "Marketing", "Sales", "Operations"]

LEAVE_TYPES = ["Annual", "Medical", "Compassionate", "Unpaid"]
LEAVE_STATUSES = ["Pending", "Approved", "Rejected", "Cancelled"]
# Yearly entitlement in working days; leave types not listed here are unlimited
ENTITLEMENTS = {"Annual": 18, "Medical": 14, "Compassionate": 3}

CLAIM_CATEGORIES = {
    "Travel": ["Taxi / ride-hailing", "Flight", "Hotel", "Mileage"],
    "Meals": ["Client entertainment", "Overtime meal"],
    "Medical": ["GP visit", "Dental", "Specialist"],
    "Training": ["Course fee", "Books", "Exam fee"],
    "Equipment": ["Hardware", "Software", "Office supplies"],
}
CLAIM_STATUSES = ["Pending", "Approved", "Rejected"]
CLAIM_MAX_CENTS = 5000_00
RECEIPT_REQUIRED_OVER_CENTS = 25_00
RECEIPT_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg"}
RECEIPT_MAX_BYTES = 5 * 1024 * 1024

LANGUAGES = {"en": "English", "zh": "中文", "ms": "Bahasa Melayu", "ta": "தமிழ்"}

DEFAULT_PASSWORD = "GoWork@2026"

# Employee ID / invite codes accepted by the public sign-up form (reusable)
INVITE_CODES = [f"GW-2026-{n:04d}" for n in range(1, 11)]

SESSION_IDLE_MINUTES = int(os.environ.get("SESSION_IDLE_MINUTES", "30"))
