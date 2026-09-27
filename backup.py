"""
Backup / restore for the databases and the attachments folder.

Each backup is a zip file under ./backups/ with a timestamped name.
The zip contains:
    - contacts.db (if present)
    - identity.db (if present)
    - telegram.db (if present)
    - attachments/<contact_id>/... (all attachment files)
    - meta.json
"""

import json
import shutil
import sqlite3
import zipfile
from datetime import datetime
from pathlib import Path
from branding import APP_NAME

from db import DB_PATH, IDENTITY_DB, TELEGRAM_DB, audit

BACKUP_DIR      = Path("backups")
RESTORE_DIR     = Path("backups/_restore_temp")
ATTACHMENTS_DIR = Path("attachments")


def _databases():
    return [Path(DB_PATH), Path(IDENTITY_DB), Path(TELEGRAM_DB)]


# ------------------------------------------------------------
# Create
# ------------------------------------------------------------
def create_backup(tag: str = "") -> Path:
    """Create a zip with databases + attachments + metadata."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    tag_part = f"_{tag}" if tag else ""
    target = BACKUP_DIR / f"backup_{stamp}{tag_part}.zip"

    existing_dbs = [p for p in _databases() if p.exists()]
    att_dir = ATTACHMENTS_DIR
    has_attachments = att_dir.exists() and any(att_dir.rglob("*"))

    if not existing_dbs and not has_attachments:
        raise RuntimeError("No databases or attachments to back up.")

    meta = {
        "app": APP_NAME,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "tag": tag,
        "files": [p.name for p in existing_dbs],
        "has_attachments": bool(has_attachments),
    }

    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:
        # databases
        for p in existing_dbs:
            try:
                c = sqlite3.connect(p)
                c.execute("PRAGMA wal_checkpoint(FULL);")
                c.close()
            except Exception:
                pass
            z.write(p, arcname=p.name)

        # attachments (preserve directory structure)
        if has_attachments:
            for f in att_dir.rglob("*"):
                if f.is_file():
                    rel = f.relative_to(att_dir.parent)
                    z.write(f, arcname=str(rel).replace("\\", "/"))

        z.writestr("meta.json",
                   json.dumps(meta, ensure_ascii=False, indent=2))

    audit("backup", str(target))
    return target


# ------------------------------------------------------------
# List
# ------------------------------------------------------------
def list_backups():
    if not BACKUP_DIR.exists():
        return []
    files = list(BACKUP_DIR.glob(f"{APP_NAME.lower()}_backup_*.zip"))
    files += list(BACKUP_DIR.glob("backup_*.zip"))  # legacy
    return sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)


# ------------------------------------------------------------
# Restore
# ------------------------------------------------------------
def restore_backup(zip_path) -> list:
    """
    Restore databases and attachments from the given zip.
    A safety backup of current files is created first.
    Returns the list of restored items.
    """
    zip_path = Path(zip_path)
    if not zip_path.exists():
        raise FileNotFoundError(zip_path)

    # safety backup
    try:
        create_backup(tag="pre_restore")
    except Exception:
        pass

    restored: list[str] = []

    # clear the temporary extraction folder
    if RESTORE_DIR.exists():
        shutil.rmtree(RESTORE_DIR, ignore_errors=True)
    RESTORE_DIR.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(zip_path, "r") as z:
        z.extractall(RESTORE_DIR)

    # ----- databases -----
    for db_name in (Path(DB_PATH).name,
                    Path(IDENTITY_DB).name,
                    Path(TELEGRAM_DB).name):
        src = RESTORE_DIR / db_name
        if src.exists():
            shutil.copy2(src, Path(db_name))
            restored.append(db_name)

    # ----- attachments -----
    att_src = RESTORE_DIR / ATTACHMENTS_DIR
    if att_src.exists() and att_src.is_dir():
        att_dst = ATTACHMENTS_DIR
        if att_dst.exists():
            shutil.rmtree(att_dst, ignore_errors=True)
        shutil.copytree(att_src, att_dst)
        restored.append("attachments/")

    # cleanup
    try:
        shutil.rmtree(RESTORE_DIR)
    except Exception:
        pass

    audit("restore", f"{zip_path} -> {restored}")
    return restored


# ------------------------------------------------------------
# Housekeeping
# ------------------------------------------------------------
def prune_old_backups(keep: int = 20) -> int:
    files = list_backups()
    if len(files) <= keep:
        return 0
    deleted = 0
    for f in files[keep:]:
        try:
            f.unlink()
            deleted += 1
        except Exception:
            pass
    return deleted


def backups_total_size() -> int:
    return sum(f.stat().st_size for f in list_backups())