"""
Vault management.

Layout:
    vault/
        vault.json                 (unencrypted header)
        contacts.db.enc
        identity.db.enc
        telegram.db.enc
        attachments.zip.enc

Public API:
    vault_exists() -> bool
    init_vault(passphrase, source_dir, ...) -> None
    unlock(passphrase) -> Path          # working directory
    lock(workdir, passphrase) -> None
    change_passphrase(old, new) -> None
"""

import base64
import shutil
import tempfile
import zipfile
from io import BytesIO
from pathlib import Path

from crypto import (
    HAS_CRYPTO, require_crypto,
    derive_key, generate_salt,
    make_header, read_header, write_header, decode_salt,
    encrypt_file, decrypt_file,
    encrypt_bytes, decrypt_bytes,
    DEFAULT_ITERATIONS,
)

VAULT_DIR       = Path("vault")
HEADER_NAME     = "vault.json"
ATTACHMENTS_ENC = "attachments.zip.enc"
TMP_ZIP         = "_attachments_tmp.zip"

# logical filename  ->  encrypted filename
ENCRYPTED_FILES = {
    "contacts.db": "contacts.db.enc",
    "identity.db": "identity.db.enc",
    "telegram.db": "telegram.db.enc",
}


# ------------------------------------------------------------
# Detection
# ------------------------------------------------------------
def vault_exists(vault_dir: Path = VAULT_DIR) -> bool:
    return (Path(vault_dir) / HEADER_NAME).exists()


# ------------------------------------------------------------
# Init
# ------------------------------------------------------------
def init_vault(passphrase: str,
               source_dir: Path = Path("."),
               vault_dir: Path = VAULT_DIR,
               attachments_dir: Path | None = None,
               iterations: int = DEFAULT_ITERATIONS,
               remove_originals: bool = False) -> None:
    require_crypto()
    source_dir = Path(source_dir)
    vault_dir  = Path(vault_dir)

    if attachments_dir is None:
        attachments_dir = source_dir / "attachments"
    attachments_dir = Path(attachments_dir)

    if vault_exists(vault_dir):
        raise RuntimeError(f"Vault already exists at {vault_dir}.")

    vault_dir.mkdir(parents=True, exist_ok=True)

    salt = generate_salt()
    write_header(vault_dir / HEADER_NAME, make_header(salt, iterations))

    key = derive_key(passphrase, salt, iterations)

    for logical, enc_name in ENCRYPTED_FILES.items():
        src = source_dir / logical
        if src.exists():
            encrypt_file(src, vault_dir / enc_name, key)
            if remove_originals:
                try:
                    src.unlink()
                except Exception:
                    pass

    if attachments_dir.exists():
        tmp_zip = vault_dir / TMP_ZIP
        with zipfile.ZipFile(tmp_zip, "w", zipfile.ZIP_DEFLATED) as z:
            for f in attachments_dir.rglob("*"):
                if f.is_file():
                    rel = f.relative_to(attachments_dir)
                    z.write(f, arcname=str(rel).replace("\\", "/"))
        encrypt_file(tmp_zip, vault_dir / ATTACHMENTS_ENC, key)
        tmp_zip.unlink(missing_ok=True)
        if remove_originals:
            shutil.rmtree(attachments_dir, ignore_errors=True)


# ------------------------------------------------------------
# Unlock
# ------------------------------------------------------------
def unlock(passphrase: str, vault_dir: Path = VAULT_DIR) -> Path:
    require_crypto()
    vault_dir = Path(vault_dir)
    header_path = vault_dir / HEADER_NAME
    if not header_path.exists():
        raise RuntimeError(f"No vault found at {vault_dir}.")

    header = read_header(header_path)
    salt = decode_salt(header)
    iterations = int(header.get("iterations", DEFAULT_ITERATIONS))
    key = derive_key(passphrase, salt, iterations)

    workdir = Path(tempfile.mkdtemp(prefix="contacts_unlocked_"))
    try:
        for logical, enc_name in ENCRYPTED_FILES.items():
            enc = vault_dir / enc_name
            if enc.exists():
                decrypt_file(enc, workdir / logical, key)

        enc_att = vault_dir / ATTACHMENTS_ENC
        if enc_att.exists():
            plaintext_zip = decrypt_bytes(enc_att.read_bytes(), key)
            att_dir = workdir / "attachments"
            att_dir.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(BytesIO(plaintext_zip)) as z:
                z.extractall(att_dir)
    except Exception:
        shutil.rmtree(workdir, ignore_errors=True)
        raise

    return workdir


# ------------------------------------------------------------
# Lock
# ------------------------------------------------------------
def lock(workdir: Path, passphrase: str, vault_dir: Path = VAULT_DIR) -> None:
    require_crypto()
    workdir   = Path(workdir)
    vault_dir = Path(vault_dir)
    header_path = vault_dir / HEADER_NAME
    if not header_path.exists():
        raise RuntimeError(f"No vault found at {vault_dir}.")

    header = read_header(header_path)
    salt = decode_salt(header)
    iterations = int(header.get("iterations", DEFAULT_ITERATIONS))
    key = derive_key(passphrase, salt, iterations)

    vault_dir.mkdir(parents=True, exist_ok=True)

    for logical, enc_name in ENCRYPTED_FILES.items():
        src = workdir / logical
        if src.exists():
            encrypt_file(src, vault_dir / enc_name, key)

    att_dir = workdir / "attachments"
    if att_dir.exists():
        tmp_zip = vault_dir / TMP_ZIP
        with zipfile.ZipFile(tmp_zip, "w", zipfile.ZIP_DEFLATED) as z:
            for f in att_dir.rglob("*"):
                if f.is_file():
                    rel = f.relative_to(att_dir)
                    z.write(f, arcname=str(rel).replace("\\", "/"))
        encrypt_file(tmp_zip, vault_dir / ATTACHMENTS_ENC, key)
        tmp_zip.unlink(missing_ok=True)

    shutil.rmtree(workdir, ignore_errors=True)


# ------------------------------------------------------------
# Change passphrase
# ------------------------------------------------------------
def change_passphrase(old: str, new: str, vault_dir: Path = VAULT_DIR) -> None:
    require_crypto()
    if old == new:
        raise ValueError("New passphrase is the same as the old one.")
    workdir = unlock(old, vault_dir)
    try:
        salt = generate_salt()
        write_header(vault_dir / HEADER_NAME, make_header(salt))
        lock(workdir, new, vault_dir)
    except Exception:
        shutil.rmtree(workdir, ignore_errors=True)
        raise