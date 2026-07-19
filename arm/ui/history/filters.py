"""Pure helpers for parsing the History page filter query params.

Kept DB- and Flask-free so they can be unit-tested directly. The history
route uses these to normalise ?status=&from=&to= before building its
SQLAlchemy query, and to thread the active filter through pagination links.
"""
from datetime import datetime

ALLOWED_STATUSES = ("all", "success", "fail", "active")


def normalize_status(raw):
    """Return raw if it is a recognised status filter, else 'all'."""
    return raw if raw in ALLOWED_STATUSES else "all"


def parse_date(raw):
    """Parse a 'YYYY-MM-DD' string to a datetime; return None if empty/invalid."""
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%d")
    except (ValueError, TypeError):
        return None


def build_page_args(status, date_from, date_to):
    """Non-empty filter params to forward through pagination url_for() calls."""
    args = {}
    if status and status != "all":
        args["status"] = status
    if date_from:
        args["from"] = date_from
    if date_to:
        args["to"] = date_to
    return args
