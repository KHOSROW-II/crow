"""
Registry for external data sources.

Each source is an external SQLite database with a table that contains
phone numbers, national codes, or names to match against contacts.db.

Sources are stored in the `data_sources` table inside contacts.db so
they can be added/edited/removed at runtime.
"""

import json
import re
from pathlib import Path

from db import connect, DB_PATH, audit


BUILTIN_SOURCES = [
    {
        "name": "identity",
        "label": "Identity",
        "code": "I",
        "db_path": "identity.db",
        "table_name": "citizens",
        "pk_column": "id",
        "phone_fields": ["national_code", "field8", "field4", "field14"],
        "name_columns": ["name", "family"],
        "national_code_column": "national_code",
        "matchers": ["phone", "national_code", "name_family"],
        "create_missing": 0,
        "social_platform": None,
        "enabled": 1,
        "is_builtin": 1,
        "sort_order": 10,
    },
    {
        "name": "telegram",
        "label": "Telegram",
        "code": "T",
        "db_path": "telegram.db",
        "table_name": "telegram_users",
        "pk_column": "id",
        "phone_fields": ["phone"],
        "name_columns": ["first_name", "last_name"],
        "national_code_column": None,
        "matchers": ["phone"],
        "create_missing": 1,
        "social_platform": "telegram",
        "enabled": 1,
        "is_builtin": 1,
        "sort_order": 20,
    },
]


_IDENT_RE = re.compile(r"^[a-z][a-z0-9_]{1,30}$")
VALID_MATCHERS = {"phone", "national_code", "name_family"}


# ------------------------------------------------------------
# Schema / seeding
# ------------------------------------------------------------
def ensure_data_sources():
    """Called from db.ensure_schema(). Seeds the built-in sources."""
    with connect(DB_PATH) as conn:
        existing = {r["name"] for r in
                    conn.execute("SELECT name FROM data_sources")}
        for s in BUILTIN_SOURCES:
            if s["name"] in existing:
                continue
            _insert(conn, s)


# ------------------------------------------------------------
# Encoding / decoding
# ------------------------------------------------------------
def _encode(s):
    return {
        "name":                 (s.get("name") or "").strip().lower(),
        "label":                (s.get("label") or s.get("name") or "").strip(),
        "code":                 ((s.get("code") or "?").strip() or "?")[:2],
        "db_path":              (s.get("db_path") or "").strip(),
        "table_name":           (s.get("table_name") or "").strip(),
        "pk_column":            (s.get("pk_column") or "id").strip(),
        "phone_fields":         json.dumps(list(s.get("phone_fields") or [])),
        "name_columns":         json.dumps(list(s.get("name_columns") or [])),
        "national_code_column": s.get("national_code_column") or None,
        "matchers":             json.dumps(
                                    list(s.get("matchers") or ["phone"])),
        "create_missing":       1 if s.get("create_missing") else 0,
        "social_platform":      s.get("social_platform") or None,
        "enabled":              1 if s.get("enabled", 1) else 0,
        "is_builtin":           1 if s.get("is_builtin") else 0,
        "sort_order":           int(s.get("sort_order") or 100),
    }


def _decode(row):
    def _load(v, default):
        try:
            return json.loads(v) if v else default
        except Exception:
            return default
    row["phone_fields"] = _load(row.get("phone_fields"), [])
    row["name_columns"] = _load(row.get("name_columns"), [])
    row["matchers"]     = _load(row.get("matchers"), ["phone"])
    return row


# ------------------------------------------------------------
# Validation
# ------------------------------------------------------------
def _validate_name(name):
    name = (name or "").strip().lower()
    if not _IDENT_RE.match(name):
        raise ValueError(
            "Source name must start with a letter, contain only "
            "lowercase letters, digits, or underscore (2..31 chars)."
        )
    return name


def validate_source(s):
    """Raise ValueError on invalid fields. Returns the encoded dict."""
    name = _validate_name(s.get("name"))
    label = (s.get("label") or name).strip()
    code = ((s.get("code") or "?").strip() or "?")[:2]
    db_path = (s.get("db_path") or "").strip()
    table_name = (s.get("table_name") or "").strip()

    if not db_path:
        raise ValueError("Database path is required.")
    if not table_name:
        raise ValueError("Table name is required.")

    matchers = [m for m in (s.get("matchers") or []) if m in VALID_MATCHERS]
    if not matchers:
        raise ValueError("At least one matcher (phone / national_code / "
                         "name_family) is required.")

    if "phone" in matchers and not s.get("phone_fields"):
        raise ValueError("phone matcher requires at least one phone field.")
    if "name_family" in matchers:
        cols = list(s.get("name_columns") or [])
        if len(cols) < 2 or not cols[0] or not cols[1]:
            raise ValueError("name_family matcher requires two name columns.")
    if "national_code" in matchers and not s.get("national_code_column"):
        raise ValueError("national_code matcher requires a national_code column.")

    return _encode({**s, "name": name, "label": label, "code": code,
                    "db_path": db_path, "table_name": table_name,
                    "matchers": matchers})


# ------------------------------------------------------------
# Low-level
# ------------------------------------------------------------
def _insert(conn, s):
    enc = _encode(s)
    conn.execute("""
        INSERT INTO data_sources
            (name, label, code, db_path, table_name, pk_column,
             phone_fields, name_columns, national_code_column, matchers,
             create_missing, social_platform, enabled, is_builtin, sort_order)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        enc["name"], enc["label"], enc["code"], enc["db_path"],
        enc["table_name"], enc["pk_column"], enc["phone_fields"],
        enc["name_columns"], enc["national_code_column"], enc["matchers"],
        enc["create_missing"], enc["social_platform"], enc["enabled"],
        enc["is_builtin"], enc["sort_order"],
    ))


# ------------------------------------------------------------
# Public API
# ------------------------------------------------------------
def list_sources(only_enabled=False):
    with connect(DB_PATH) as conn:
        q = "SELECT * FROM data_sources"
        if only_enabled:
            q += " WHERE enabled=1"
        q += " ORDER BY sort_order, name"
        rows = [dict(r) for r in conn.execute(q)]
    return [_decode(r) for r in rows]


def get_source(name):
    name = (name or "").strip().lower()
    with connect(DB_PATH) as conn:
        r = conn.execute(
            "SELECT * FROM data_sources WHERE name=?", (name,)
        ).fetchone()
    return _decode(dict(r)) if r else None


def add_source(s):
    enc = validate_source(s)
    if get_source(enc["name"]):
        raise ValueError(f"Source '{enc['name']}' already exists.")
    with connect(DB_PATH) as conn:
        _insert(conn, enc)
    audit("add_source", enc["name"])
    return enc["name"]


def update_source(name, s):
    name = (name or "").strip().lower()
    if not get_source(name):
        raise ValueError(f"Source '{name}' not found.")
    enc = validate_source({**s, "name": name})
    with connect(DB_PATH) as conn:
        conn.execute("""
            UPDATE data_sources SET
                label=?, code=?, db_path=?, table_name=?, pk_column=?,
                phone_fields=?, name_columns=?, national_code_column=?,
                matchers=?, create_missing=?, social_platform=?,
                enabled=?, sort_order=?, updated_at=CURRENT_TIMESTAMP
            WHERE name=?
        """, (
            enc["label"], enc["code"], enc["db_path"], enc["table_name"],
            enc["pk_column"], enc["phone_fields"], enc["name_columns"],
            enc["national_code_column"], enc["matchers"], enc["create_missing"],
            enc["social_platform"], enc["enabled"], enc["sort_order"], name,
        ))
    audit("update_source", name)
    return name


def remove_source(name):
    name = (name or "").strip().lower()
    src = get_source(name)
    if not src:
        raise ValueError(f"Source '{name}' not found.")
    if src["is_builtin"]:
        raise ValueError(f"'{name}' is built-in and cannot be removed.")
    with connect(DB_PATH) as conn:
        conn.execute("DELETE FROM data_sources WHERE name=?", (name,))
        conn.execute(
            "DELETE FROM contact_links WHERE source_db=?",
            (f"{name}_db",)
        )
    audit("remove_source", name)


def source_label_map():
    """Return {'contacts':'C', 'identity_db':'I', 'telegram_db':'T', ...}."""
    labels = {"contacts": "C"}
    for s in list_sources():
        labels[f"{s['name']}_db"] = s["code"]
    return labels


def source_db_names():
    return [f"{s['name']}_db" for s in list_sources()]


def source_exists(name):
    return get_source(name) is not None