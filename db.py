"""
Database layer: schema, connections, normalization, platform registry,
custom tables, data-source registry, and one-time migrations.
"""

import re
import sqlite3
from pathlib import Path
from contextlib import contextmanager

import os as _os

WORKDIR      = Path(_os.environ.get("CONTACTS_WORKDIR", "."))
DB_PATH      = str(WORKDIR / "contacts.db")
IDENTITY_DB  = str(WORKDIR / "identity.db")
TELEGRAM_DB  = str(WORKDIR / "telegram.db")
INPUT_JSON   = str(WORKDIR / "tempinput.json")

IDENTITY_TABLE = "citizens"
TELEGRAM_TABLE = "telegram_users"

IDENTITY_PHONE_FIELDS = ["national_code", "field8", "field4", "field14"]

BUILTIN_PLATFORMS = [
    ("splus",     "Splus",     10),
    ("bale",      "Bale",      20),
    ("rubika",    "Rubika",    30),
    ("telegram",  "Telegram",  40),
    ("instagram", "Instagram", 50),
]

CUSTOM_COL_TYPES = ("text", "integer", "real", "date", "bool")


SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS contacts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    phone_number    TEXT NOT NULL UNIQUE,
    status          TEXT NOT NULL DEFAULT 'unchecked'
                    CHECK (status IN ('unchecked','checking','verified','invalid','anonymous')),
    name            TEXT,
    last_name       TEXT,
    name_norm       TEXT,
    last_name_norm  TEXT,
    national_code   TEXT,
    photo_path      TEXT,
    notes           TEXT,
    pinned          INTEGER NOT NULL DEFAULT 0,
    special         INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS contact_socials (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    contact_id      INTEGER NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
    platform        TEXT NOT NULL,
    exists_status   TEXT NOT NULL DEFAULT 'unknown'
                    CHECK (exists_status IN ('unknown','yes','no')),
    username        TEXT,
    display_name    TEXT,
    user_id         TEXT,
    verified_status TEXT NOT NULL DEFAULT 'unchecked'
                    CHECK (verified_status IN ('unchecked','checking','verified','invalid','anonymous')),
    raw_data        TEXT,
    updated_at      TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (contact_id, platform)
);

CREATE TABLE IF NOT EXISTS contact_links (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    contact_id   INTEGER NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
    source_db    TEXT NOT NULL,
    source_table TEXT NOT NULL,
    source_pk    TEXT NOT NULL,
    match_key    TEXT NOT NULL,
    match_value  TEXT,
    confidence   REAL NOT NULL DEFAULT 1.0,
    created_at   TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (source_db, source_table, source_pk, contact_id)
);

CREATE TABLE IF NOT EXISTS audit_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    ts         TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    action     TEXT NOT NULL,
    detail     TEXT
);

CREATE TABLE IF NOT EXISTS platforms (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL UNIQUE,
    display_name  TEXT,
    is_builtin    INTEGER NOT NULL DEFAULT 0,
    sort_order    INTEGER NOT NULL DEFAULT 100,
    created_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS custom_tables (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL UNIQUE,
    display_name    TEXT NOT NULL,
    description     TEXT,
    sort_order      INTEGER NOT NULL DEFAULT 100,
    created_at      TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS custom_columns (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    table_id        INTEGER NOT NULL REFERENCES custom_tables(id) ON DELETE CASCADE,
    name            TEXT NOT NULL,
    display_name    TEXT NOT NULL,
    col_type        TEXT NOT NULL DEFAULT 'text'
                    CHECK (col_type IN ('text','integer','real','date','bool')),
    is_required     INTEGER NOT NULL DEFAULT 0,
    default_value   TEXT,
    sort_order      INTEGER NOT NULL DEFAULT 100,
    UNIQUE (table_id, name)
);

CREATE TABLE IF NOT EXISTS data_sources (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    name                  TEXT NOT NULL UNIQUE,
    label                 TEXT NOT NULL,
    code                  TEXT NOT NULL,
    db_path               TEXT NOT NULL,
    table_name            TEXT NOT NULL,
    pk_column             TEXT NOT NULL DEFAULT 'id',
    phone_fields          TEXT,
    name_columns          TEXT,
    national_code_column  TEXT,
    matchers              TEXT,
    create_missing        INTEGER NOT NULL DEFAULT 0,
    social_platform       TEXT,
    enabled               INTEGER NOT NULL DEFAULT 1,
    is_builtin            INTEGER NOT NULL DEFAULT 0,
    sort_order            INTEGER NOT NULL DEFAULT 100,
    created_at            TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at            TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS contact_images (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    contact_id    INTEGER NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
    name          TEXT NOT NULL,
    mime          TEXT,
    size_bytes    INTEGER,
    width         INTEGER,
    height        INTEGER,
    sha256        TEXT,
    raw_data      BLOB NOT NULL,
    encoded_data  TEXT,
    encoding      TEXT NOT NULL DEFAULT 'base64',
    is_primary    INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_contact_images_contact
    ON contact_images(contact_id);
CREATE INDEX IF NOT EXISTS idx_contact_images_primary
    ON contact_images(contact_id, is_primary);

CREATE INDEX IF NOT EXISTS idx_contacts_phone         ON contacts(phone_number);
CREATE INDEX IF NOT EXISTS idx_contacts_name_norm     ON contacts(name_norm, last_name_norm);
CREATE INDEX IF NOT EXISTS idx_contacts_national_code ON contacts(national_code);
CREATE INDEX IF NOT EXISTS idx_socials_contact        ON contact_socials(contact_id);
CREATE INDEX IF NOT EXISTS idx_socials_platform_user  ON contact_socials(platform, username);
CREATE INDEX IF NOT EXISTS idx_links_contact          ON contact_links(contact_id);
CREATE INDEX IF NOT EXISTS idx_links_source           ON contact_links(source_db, source_table);
CREATE INDEX IF NOT EXISTS idx_custom_cols_table      ON custom_columns(table_id);
CREATE INDEX IF NOT EXISTS idx_data_sources_name      ON data_sources(name);
"""


@contextmanager
def connect(path: str = DB_PATH):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA temp_store = MEMORY")
    conn.execute("PRAGMA cache_size = -16000")
    conn.execute("PRAGMA mmap_size = 268435456")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def ensure_schema():
    with connect(DB_PATH) as conn:
        conn.executescript(SCHEMA_SQL)

    _migrate_contacts_status_check()
    _migrate_contact_socials()
    _migrate_contact_socials_verified_status()
    _migrate_contacts_flags()
    _migrate_contacts_notes()
    _migrate_contacts_photo()
    _seed_platforms()
    _rebuild_wide_view()

    try:
        from data_sources import ensure_data_sources
        ensure_data_sources()
    except Exception as e:
        print(f"[db] could not seed data sources: {e}")


# ------------------------------------------------------------
# Migration: add 'notes' column if missing
# ------------------------------------------------------------
def _migrate_contacts_notes():
    with connect(DB_PATH) as conn:
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(contacts)")}
        if "notes" in cols:
            return
        conn.execute("ALTER TABLE contacts ADD COLUMN notes TEXT")
        print("[db] contacts.notes column added.")

#-------------------------------------------------------------
# Migration: add 'path'
# ------------------------------------------------------------
def _migrate_contacts_photo():
    with connect(DB_PATH) as conn:
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(contacts)")}
        if "photo_path" in cols:
            return
        conn.execute("ALTER TABLE contacts ADD COLUMN photo_path TEXT")
        print("[db] contacts.photo_path column added.")

# ------------------------------------------------------------
# Migration: contacts.status CHECK gains 'anonymous'
# ------------------------------------------------------------
def _migrate_contacts_status_check():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT sql FROM sqlite_master "
            "WHERE type='table' AND name='contacts'"
        ).fetchone()
        if not row:
            return
        schema = row["sql"] or ""
        if "'anonymous'" in schema:
            return

        conn.executescript("""
            PRAGMA foreign_keys=OFF;
            PRAGMA legacy_alter_table=ON;

            ALTER TABLE contacts RENAME TO contacts_old;

            CREATE TABLE contacts (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                phone_number    TEXT NOT NULL UNIQUE,
                status          TEXT NOT NULL DEFAULT 'unchecked'
                                CHECK (status IN ('unchecked','checking','verified','invalid','anonymous')),
                name            TEXT,
                last_name       TEXT,
                name_norm       TEXT,
                last_name_norm  TEXT,
                national_code   TEXT,
                notes           TEXT,
                pinned          INTEGER NOT NULL DEFAULT 0,
                special         INTEGER NOT NULL DEFAULT 0,
                created_at      TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at      TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            INSERT INTO contacts
                (id, phone_number, status, name, last_name,
                 name_norm, last_name_norm, national_code,
                 pinned, special, created_at, updated_at)
            SELECT id, phone_number, status, name, last_name,
                   name_norm, last_name_norm, national_code,
                   pinned, special, created_at, updated_at
            FROM contacts_old;

            DROP TABLE contacts_old;

            PRAGMA legacy_alter_table=OFF;
            PRAGMA foreign_keys=ON;

            CREATE INDEX IF NOT EXISTS idx_contacts_phone         ON contacts(phone_number);
            CREATE INDEX IF NOT EXISTS idx_contacts_name_norm     ON contacts(name_norm, last_name_norm);
            CREATE INDEX IF NOT EXISTS idx_contacts_national_code ON contacts(national_code);
            CREATE INDEX IF NOT EXISTS idx_contacts_pinned        ON contacts(pinned);
            CREATE INDEX IF NOT EXISTS idx_contacts_special       ON contacts(special);
        """)
        conn.commit()
        print("[db] contacts.status CHECK migrated to include 'anonymous'.")
    finally:
        conn.close()


# ------------------------------------------------------------
# Migration: contact_socials without CHECK on platform
# ------------------------------------------------------------
def _migrate_contact_socials():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT sql FROM sqlite_master "
            "WHERE type='table' AND name='contact_socials'"
        ).fetchone()
        if not row:
            return
        schema = row["sql"] or ""
        if "CHECK (platform IN" not in schema:
            return

        conn.executescript("""
            PRAGMA foreign_keys=OFF;
            PRAGMA legacy_alter_table=ON;

            ALTER TABLE contact_socials RENAME TO contact_socials_old;

            CREATE TABLE contact_socials (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                contact_id      INTEGER NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
                platform        TEXT NOT NULL,
                exists_status   TEXT NOT NULL DEFAULT 'unknown'
                                CHECK (exists_status IN ('unknown','yes','no')),
                username        TEXT,
                display_name    TEXT,
                user_id         TEXT,
                verified_status TEXT NOT NULL DEFAULT 'unchecked'
                                CHECK (verified_status IN ('unchecked','checking','verified','invalid','anonymous')),
                raw_data        TEXT,
                updated_at      TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (contact_id, platform)
            );

            INSERT INTO contact_socials
                (id, contact_id, platform, exists_status, username,
                 display_name, user_id, verified_status, raw_data, updated_at)
            SELECT id, contact_id, platform, exists_status, username,
                   display_name, user_id, verified_status, raw_data, updated_at
            FROM contact_socials_old;

            DROP TABLE contact_socials_old;

            PRAGMA legacy_alter_table=OFF;
            PRAGMA foreign_keys=ON;

            CREATE INDEX IF NOT EXISTS idx_socials_contact
                ON contact_socials(contact_id);
            CREATE INDEX IF NOT EXISTS idx_socials_platform_user
                ON contact_socials(platform, username);
        """)
        conn.commit()
        print("[db] contact_socials migrated to dynamic-platform schema.")
    finally:
        conn.close()


# ------------------------------------------------------------
# Migration: contact_socials.verified_status gains 'anonymous'
# ------------------------------------------------------------
def _migrate_contact_socials_verified_status():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT sql FROM sqlite_master "
            "WHERE type='table' AND name='contact_socials'"
        ).fetchone()
        if not row:
            return
        schema = row["sql"] or ""
        if "'anonymous'" in schema:
            return

        conn.executescript("""
            PRAGMA foreign_keys=OFF;
            PRAGMA legacy_alter_table=ON;

            ALTER TABLE contact_socials RENAME TO contact_socials_old;

            CREATE TABLE contact_socials (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                contact_id      INTEGER NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
                platform        TEXT NOT NULL,
                exists_status   TEXT NOT NULL DEFAULT 'unknown'
                                CHECK (exists_status IN ('unknown','yes','no')),
                username        TEXT,
                display_name    TEXT,
                user_id         TEXT,
                verified_status TEXT NOT NULL DEFAULT 'unchecked'
                                CHECK (verified_status IN ('unchecked','checking','verified','invalid','anonymous')),
                raw_data        TEXT,
                updated_at      TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (contact_id, platform)
            );

            INSERT INTO contact_socials
                (id, contact_id, platform, exists_status, username,
                 display_name, user_id, verified_status, raw_data, updated_at)
            SELECT id, contact_id, platform, exists_status, username,
                   display_name, user_id, verified_status, raw_data, updated_at
            FROM contact_socials_old;

            DROP TABLE contact_socials_old;

            PRAGMA legacy_alter_table=OFF;
            PRAGMA foreign_keys=ON;

            CREATE INDEX IF NOT EXISTS idx_socials_contact
                ON contact_socials(contact_id);
            CREATE INDEX IF NOT EXISTS idx_socials_platform_user
                ON contact_socials(platform, username);
        """)
        conn.commit()
        print("[db] contact_socials.verified_status now accepts 'anonymous'.")
    finally:
        conn.close()


# ------------------------------------------------------------
# Migration: pinned / special columns
# ------------------------------------------------------------
def _migrate_contacts_flags():
    with connect(DB_PATH) as conn:
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(contacts)")}
        if "pinned" not in cols:
            conn.execute(
                "ALTER TABLE contacts ADD COLUMN pinned INTEGER NOT NULL DEFAULT 0"
            )
        if "special" not in cols:
            conn.execute(
                "ALTER TABLE contacts ADD COLUMN special INTEGER NOT NULL DEFAULT 0"
            )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_contacts_pinned ON contacts(pinned)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_contacts_special ON contacts(special)"
        )


def _seed_platforms():
    with connect(DB_PATH) as conn:
        existing = {r["name"] for r in conn.execute("SELECT name FROM platforms")}
        for name, display, order in BUILTIN_PLATFORMS:
            if name in existing:
                continue
            conn.execute(
                "INSERT INTO platforms(name, display_name, is_builtin, sort_order) "
                "VALUES (?, ?, 1, ?)",
                (name, display, order),
            )


def _rebuild_wide_view():
    with connect(DB_PATH) as conn:
        platforms = [
            dict(r) for r in conn.execute(
                "SELECT name, display_name FROM platforms ORDER BY sort_order, name"
            )
        ]
        pieces = []
        for p in platforms:
            n = p["name"]
            pieces.append(
                f"MAX(CASE WHEN s.platform='{n}' THEN s.exists_status END) AS \"{n}\""
            )
            pieces.append(
                f"MAX(CASE WHEN s.platform='{n}' THEN s.username END) AS \"{n} username\""
            )
            pieces.append(
                f"MAX(CASE WHEN s.platform='{n}' THEN s.display_name END) AS \"{n} display name\""
            )
            pieces.append(
                f"MAX(CASE WHEN s.platform='{n}' THEN s.user_id END) AS \"{n} userid\""
            )
        body = ",\n            ".join(pieces) if pieces else "NULL AS dummy"
        conn.executescript(f"""
            DROP VIEW IF EXISTS v_contacts_wide;
            CREATE VIEW v_contacts_wide AS
            SELECT
                c.id,
                c.phone_number AS "phone number",
                c.status,
                c.name,
                c.last_name,
                c.notes,
                {body}
            FROM contacts c
            LEFT JOIN contact_socials s ON s.contact_id = c.id
            GROUP BY c.id;
        """)


def audit(action: str, detail: str = ""):
    try:
        with connect(DB_PATH) as conn:
            conn.execute(
                "INSERT INTO audit_log(action, detail) VALUES (?, ?)",
                (action, detail),
            )
    except Exception:
        pass


# ------------------------------------------------------------
# Platform registry
# ------------------------------------------------------------
def list_platforms():
    with connect(DB_PATH) as conn:
        return [
            dict(r) for r in conn.execute(
                "SELECT name, display_name, is_builtin, sort_order "
                "FROM platforms ORDER BY sort_order, name"
            )
        ]


def platform_names():
    return [p["name"] for p in list_platforms()]


def _validate_platform_name(name: str):
    name = (name or "").strip().lower()
    if not name:
        raise ValueError("Platform name cannot be empty.")
    if not re.match(r"^[a-z][a-z0-9_]{1,30}$", name):
        raise ValueError(
            "Platform name must start with a letter and contain only "
            "lowercase letters, digits, or underscore (2..31 chars)."
        )
    return name


def add_platform(name: str, display_name: str | None = None) -> str:
    name = _validate_platform_name(name)
    display_name = (display_name or name.capitalize()).strip()
    with connect(DB_PATH) as conn:
        existing = conn.execute(
            "SELECT id FROM platforms WHERE name=?", (name,)
        ).fetchone()
        if existing:
            raise ValueError(f"Platform '{name}' already exists.")
        max_order = conn.execute(
            "SELECT COALESCE(MAX(sort_order), 0) FROM platforms"
        ).fetchone()[0]
        conn.execute(
            "INSERT INTO platforms(name, display_name, is_builtin, sort_order) "
            "VALUES (?, ?, 0, ?)",
            (name, display_name, max_order + 10),
        )
    audit("add_platform", name)
    _rebuild_wide_view()
    return name


def rename_platform(name: str, new_display_name: str | None = None):
    if not new_display_name:
        raise ValueError("Display name cannot be empty.")
    new_display_name = new_display_name.strip()
    with connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT id FROM platforms WHERE name=?", (name,)
        ).fetchone()
        if not row:
            raise ValueError(f"Platform '{name}' not found.")
        conn.execute(
            "UPDATE platforms SET display_name=? WHERE name=?",
            (new_display_name, name),
        )
    audit("rename_platform", f"{name} -> {new_display_name}")
    _rebuild_wide_view()


def remove_platform(name: str):
    with connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT is_builtin FROM platforms WHERE name=?", (name,)
        ).fetchone()
        if not row:
            raise ValueError(f"Platform '{name}' not found.")
        if row["is_builtin"]:
            raise ValueError(
                f"'{name}' is a built-in platform and cannot be removed."
            )
        conn.execute("DELETE FROM platforms WHERE name=?", (name,))
        conn.execute("DELETE FROM contact_socials WHERE platform=?", (name,))
    audit("remove_platform", name)
    _rebuild_wide_view()


# ------------------------------------------------------------
# Custom tables
# ------------------------------------------------------------
_IDENT_RE = re.compile(r"^[a-z][a-z0-9_]{1,40}$")
_RESERVED_COL = {"id", "created_at", "updated_at"}


def _validate_ident(name: str, what: str = "name"):
    name = (name or "").strip().lower()
    if not _IDENT_RE.match(name):
        raise ValueError(
            f"{what.capitalize()} must start with a letter, contain only "
            "lowercase letters, digits, or underscore (2..41 chars)."
        )
    return name


def _sql_type(col_type: str) -> str:
    return {
        "text":    "TEXT",
        "integer": "INTEGER",
        "real":    "REAL",
        "date":    "TEXT",
        "bool":    "INTEGER",
    }.get(col_type, "TEXT")


def _sql_table(name: str) -> str:
    return f"custom_{name}"


def list_custom_tables():
    with connect(DB_PATH) as conn:
        return [
            dict(r) for r in conn.execute(
                "SELECT id, name, display_name, description, sort_order "
                "FROM custom_tables ORDER BY sort_order, name"
            )
        ]


def get_custom_table(name: str):
    name = (name or "").strip().lower()
    with connect(DB_PATH) as conn:
        t = conn.execute(
            "SELECT * FROM custom_tables WHERE name=?", (name,)
        ).fetchone()
        if not t:
            return None
        cols = [
            dict(r) for r in conn.execute(
                "SELECT * FROM custom_columns WHERE table_id=? "
                "ORDER BY sort_order, id",
                (t["id"],)
            )
        ]
        return {"table": dict(t), "columns": cols}


def create_custom_table(name, display_name, columns, description=None,
                        sort_order=100):
    name = _validate_ident(name, "table name")
    display_name = (display_name or name).strip()
    if not display_name:
        raise ValueError("Display name cannot be empty.")
    if not columns:
        raise ValueError("At least one column is required.")

    seen = set()
    clean_cols = []
    for i, col in enumerate(columns):
        cname = _validate_ident(col.get("name", ""), "column name")
        if cname in _RESERVED_COL:
            raise ValueError(f"Column name '{cname}' is reserved.")
        if cname in seen:
            raise ValueError(f"Duplicate column: {cname}")
        seen.add(cname)
        ctype = col.get("col_type", "text")
        if ctype not in CUSTOM_COL_TYPES:
            raise ValueError(f"Invalid type for column '{cname}'.")
        clean_cols.append({
            "name":          cname,
            "display_name":  (col.get("display_name") or
                              cname.replace("_", " ").title()),
            "col_type":      ctype,
            "is_required":   1 if col.get("is_required") else 0,
            "default_value": col.get("default_value"),
            "sort_order":    col.get("sort_order", 10 * (i + 1)),
        })

    sql_name = _sql_table(name)

    with connect(DB_PATH) as conn:
        existing = conn.execute(
            "SELECT id FROM custom_tables WHERE name=?", (name,)
        ).fetchone()
        if existing:
            raise ValueError(f"Table '{name}' already exists.")

        collision = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (sql_name,)
        ).fetchone()
        if collision:
            raise ValueError(f"A table named '{sql_name}' already exists.")

        cur = conn.execute(
            "INSERT INTO custom_tables(name, display_name, description, sort_order) "
            "VALUES (?, ?, ?, ?)",
            (name, display_name, description, sort_order),
        )
        table_id = cur.lastrowid

        for col in clean_cols:
            conn.execute("""
                INSERT INTO custom_columns
                    (table_id, name, display_name, col_type, is_required,
                     default_value, sort_order)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                table_id, col["name"], col["display_name"], col["col_type"],
                col["is_required"], col["default_value"], col["sort_order"],
            ))

        col_defs = []
        for col in clean_cols:
            t = _sql_type(col["col_type"])
            d = " NOT NULL" if col["is_required"] else ""
            col_defs.append(f"c_{col['name']} {t}{d}")
        cols_sql = ",\n    ".join(col_defs) if col_defs else ""

        conn.executescript(f"""
            CREATE TABLE {sql_name} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                {cols_sql},
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
        """)

    audit("create_custom_table", name)
    return table_id


def update_custom_table(name, *, display_name=None, description=None,
                        sort_order=None, columns=None):
    name = (name or "").strip().lower()
    info = get_custom_table(name)
    if not info:
        raise ValueError(f"Table '{name}' not found.")

    sql_name = _sql_table(name)
    clean_cols: list[dict] = []

    if columns is not None:
        seen = set()
        for i, col in enumerate(columns):
            cname = _validate_ident(col.get("name", ""), "column name")
            if cname in _RESERVED_COL:
                raise ValueError(f"Column name '{cname}' is reserved.")
            if cname in seen:
                raise ValueError(f"Duplicate column: {cname}")
            seen.add(cname)
            ctype = col.get("col_type", "text")
            if ctype not in CUSTOM_COL_TYPES:
                raise ValueError(f"Invalid type for column '{cname}'.")
            clean_cols.append({
                "name":          cname,
                "display_name":  (col.get("display_name") or
                                  cname.replace("_", " ").title()),
                "col_type":      ctype,
                "is_required":   1 if col.get("is_required") else 0,
                "default_value": col.get("default_value"),
                "sort_order":    col.get("sort_order", 10 * (i + 1)),
            })
        if not clean_cols:
            raise ValueError("At least one column is required.")

    with connect(DB_PATH) as conn:
        conn.execute("""
            UPDATE custom_tables SET
                display_name = COALESCE(?, display_name),
                description  = COALESCE(?, description),
                sort_order   = COALESCE(?, sort_order),
                updated_at   = CURRENT_TIMESTAMP
            WHERE name = ?
        """, (display_name, description, sort_order, name))

        if columns is not None:
            table_id = info["table"]["id"]
            old_names = {c["name"] for c in info["columns"]}
            new_names = {c["name"] for c in clean_cols}

            conn.execute("DELETE FROM custom_columns WHERE table_id=?", (table_id,))
            for col in clean_cols:
                conn.execute("""
                    INSERT INTO custom_columns
                        (table_id, name, display_name, col_type, is_required,
                         default_value, sort_order)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    table_id, col["name"], col["display_name"], col["col_type"],
                    col["is_required"], col["default_value"], col["sort_order"],
                ))

            conn.execute("PRAGMA foreign_keys=OFF")
            conn.execute(f"ALTER TABLE {sql_name} RENAME TO {sql_name}__old")

            col_defs = []
            for col in clean_cols:
                t = _sql_type(col["col_type"])
                d = " NOT NULL" if col["is_required"] else ""
                col_defs.append(f"c_{col['name']} {t}{d}")
            cols_sql = ",\n    ".join(col_defs)

            conn.executescript(f"""
                CREATE TABLE {sql_name} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    {cols_sql},
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
            """)

            common = sorted(old_names & new_names)
            if common:
                cols_select = ", ".join(f"c_{c}" for c in common)
                conn.execute(
                    f"INSERT INTO {sql_name} (id, {cols_select}, created_at, updated_at) "
                    f"SELECT id, {cols_select}, created_at, updated_at "
                    f"FROM {sql_name}__old"
                )

            conn.execute(f"DROP TABLE {sql_name}__old")
            conn.execute("PRAGMA foreign_keys=ON")

    audit("update_custom_table", name)
    return True


def delete_custom_table(name):
    name = (name or "").strip().lower()
    info = get_custom_table(name)
    if not info:
        raise ValueError(f"Table '{name}' not found.")
    sql_name = _sql_table(name)
    with connect(DB_PATH) as conn:
        conn.execute("DELETE FROM custom_tables WHERE name=?", (name,))
        conn.execute(f"DROP TABLE IF EXISTS {sql_name}")
    audit("delete_custom_table", name)
    return True


# ------------------------------------------------------------
# Custom table data
# ------------------------------------------------------------
def list_custom_rows(name):
    name = (name or "").strip().lower()
    info = get_custom_table(name)
    if not info:
        raise ValueError(f"Table '{name}' not found.")
    sql_name = _sql_table(name)
    cols = info["columns"]
    with connect(DB_PATH) as conn:
        try:
            rows = [dict(r) for r in conn.execute(
                f"SELECT * FROM {sql_name} ORDER BY id"
            )]
        except sqlite3.OperationalError:
            rows = []
    return info["table"], cols, rows


def _row_values(columns, data):
    names, values = [], []
    for col in columns:
        cname = col["name"]
        ctype = col["col_type"]
        v = data.get(cname)

        if v is None or (isinstance(v, str) and v.strip() == ""):
            v = None
        else:
            if ctype == "integer":
                try:
                    v = int(v)
                except (TypeError, ValueError):
                    raise ValueError(f"Column '{cname}' must be an integer.")
            elif ctype == "real":
                try:
                    v = float(v)
                except (TypeError, ValueError):
                    raise ValueError(f"Column '{cname}' must be a number.")
            elif ctype == "bool":
                v = 1 if str(v).strip().lower() in ("1", "true", "yes", "y", "بله") else 0
            elif ctype in ("text", "date"):
                v = str(v)

        if col.get("is_required") and v is None:
            raise ValueError(f"Column '{cname}' is required.")

        names.append(f"c_{cname}")
        values.append(v)
    return names, values


def insert_custom_row(table_name, data: dict):
    table_name = (table_name or "").strip().lower()
    info = get_custom_table(table_name)
    if not info:
        raise ValueError(f"Table '{table_name}' not found.")
    cols = info["columns"]
    sql_name = _sql_table(table_name)
    names, values = _row_values(cols, data)
    placeholders = ", ".join(["?"] * len(names))
    cols_sql = ", ".join(names)
    with connect(DB_PATH) as conn:
        cur = conn.execute(
            f"INSERT INTO {sql_name} ({cols_sql}) VALUES ({placeholders})",
            values,
        )
        new_id = cur.lastrowid
    audit("insert_custom_row", f"{table_name}#{new_id}")
    return new_id


def update_custom_row(table_name, row_id, data: dict):
    table_name = (table_name or "").strip().lower()
    info = get_custom_table(table_name)
    if not info:
        raise ValueError(f"Table '{table_name}' not found.")
    cols = info["columns"]
    sql_name = _sql_table(table_name)
    names, values = _row_values(cols, data)
    sets = ", ".join(f"{n}=?" for n in names)
    values.append(row_id)
    with connect(DB_PATH) as conn:
        conn.execute(
            f"UPDATE {sql_name} SET {sets}, updated_at=CURRENT_TIMESTAMP "
            f"WHERE id=?",
            values,
        )
    audit("update_custom_row", f"{table_name}#{row_id}")


def delete_custom_row(table_name, row_id):
    table_name = (table_name or "").strip().lower()
    info = get_custom_table(table_name)
    if not info:
        raise ValueError(f"Table '{table_name}' not found.")
    sql_name = _sql_table(table_name)
    with connect(DB_PATH) as conn:
        conn.execute(f"DELETE FROM {sql_name} WHERE id=?", (row_id,))
    audit("delete_custom_row", f"{table_name}#{row_id}")


# ------------------------------------------------------------
# Normalization
# ------------------------------------------------------------
def normalize_phone(value):
    if value is None:
        return None
    s = str(value).translate(
        str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
    )
    s = re.sub(r"\D", "", s)
    if not s:
        return None
    if s.startswith("0098"):
        s = s[4:]
    elif s.startswith("98") and len(s) > 10:
        s = s[2:]
    if s.startswith("0"):
        s = s[1:]
    if len(s) == 10 and s.startswith("9"):
        return "0" + s
    return None


def normalize_national_code(value):
    if value is None:
        return None
    s = str(value).translate(
        str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
    )
    s = re.sub(r"\D", "", s)
    return s if len(s) == 10 else None


def normalize_name(value):
    if value is None:
        return None
    s = str(value).strip().lower()
    s = (
        s.replace("ي", "ی")
         .replace("ك", "ک")
         .replace("ۀ", "ه")
         .replace("ة", "ه")
         .replace("\u200c", " ")
    )
    s = re.sub(r"\s+", " ", s)
    return s or None


def db_exists(path: str) -> bool:
    return Path(path).exists()