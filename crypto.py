"""
AES-256-GCM encryption + PBKDF2-HMAC-SHA256 key derivation.

Provides both low-level byte/file encryption and small helpers
for the vault header (salt + iteration count).
"""

import base64
import importlib
import json
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ------------------------------------------------------------
# Optional cryptography import (safe for Pylance)
# ------------------------------------------------------------
HAS_CRYPTO = False
AESGCM: Any = None
PBKDF2HMAC: Any = None
hashes: Any = None

try:
    _mod_aead = importlib.import_module(
        "cryptography.hazmat.primitives.ciphers.aead")
    _mod_kdf = importlib.import_module(
        "cryptography.hazmat.primitives.kdf.pbkdf2")
    _mod_hashes = importlib.import_module(
        "cryptography.hazmat.primitives.hashes")

    AESGCM = _mod_aead.AESGCM
    PBKDF2HMAC = _mod_kdf.PBKDF2HMAC
    hashes = _mod_hashes
    HAS_CRYPTO = True
except Exception:
    HAS_CRYPTO = False


NONCE_SIZE         = 12
KEY_SIZE           = 32           # 256-bit AES key
SALT_SIZE          = 16
DEFAULT_ITERATIONS = 600_000
VAULT_VERSION      = 1


def require_crypto():
    if not HAS_CRYPTO:
        raise RuntimeError(
            "The 'cryptography' package is required for vault support.\n"
            "Install it with:  pip install cryptography"
        )


# ------------------------------------------------------------
# Key derivation
# ------------------------------------------------------------
def derive_key(passphrase, salt: bytes,
               iterations: int = DEFAULT_ITERATIONS) -> bytes:
    require_crypto()
    if isinstance(passphrase, str):
        passphrase = passphrase.encode("utf-8")
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=KEY_SIZE,
        salt=salt,
        iterations=iterations,
    )
    return kdf.derive(passphrase)


def generate_salt() -> bytes:
    return secrets.token_bytes(SALT_SIZE)


def generate_random_key() -> str:
    """Return a 64-character hex passphrase (256-bit entropy)."""
    return secrets.token_hex(32)


# ------------------------------------------------------------
# Byte-level encryption
# ------------------------------------------------------------
def encrypt_bytes(plaintext: bytes, key: bytes) -> bytes:
    """AES-256-GCM. Returns nonce || ciphertext || tag."""
    require_crypto()
    nonce = secrets.token_bytes(NONCE_SIZE)
    aesgcm = AESGCM(key)
    ct = aesgcm.encrypt(nonce, plaintext, None)
    return nonce + ct


def decrypt_bytes(blob: bytes, key: bytes) -> bytes:
    """Decrypt a blob produced by encrypt_bytes. Raises on wrong key."""
    require_crypto()
    if len(blob) < NONCE_SIZE + 16:
        raise ValueError("Ciphertext too short.")
    nonce = blob[:NONCE_SIZE]
    ct    = blob[NONCE_SIZE:]
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ct, None)


def encrypt_file(src: Path, dst: Path, key: bytes):
    plaintext = Path(src).read_bytes()
    blob = encrypt_bytes(plaintext, key)
    Path(dst).parent.mkdir(parents=True, exist_ok=True)
    Path(dst).write_bytes(blob)


def decrypt_file(src: Path, dst: Path, key: bytes):
    blob = Path(src).read_bytes()
    plaintext = decrypt_bytes(blob, key)
    Path(dst).parent.mkdir(parents=True, exist_ok=True)
    Path(dst).write_bytes(plaintext)


# ------------------------------------------------------------
# Header
# ------------------------------------------------------------
def make_header(salt: bytes,
                iterations: int = DEFAULT_ITERATIONS) -> dict:
    return {
        "app":        "CROW",
        "version":    VAULT_VERSION,
        "salt":       base64.b64encode(salt).decode("ascii"),
        "iterations": iterations,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def read_header(path: Path) -> dict:
    return json.loads(Path(path).read_text("utf-8"))


def write_header(path: Path, header: dict):
    Path(path).write_text(
        json.dumps(header, ensure_ascii=False, indent=2),
        "utf-8",
    )


def decode_salt(header: dict) -> bytes:
    return base64.b64decode(header["salt"])


# ------------------------------------------------------------
# Passphrase prompt (terminal)
# ------------------------------------------------------------
def prompt_passphrase(confirm: bool = False) -> str:
    import getpass
    while True:
        p1 = getpass.getpass("Vault passphrase: ")
        if not p1:
            print("Empty passphrase is not allowed.")
            continue
        if not confirm:
            return p1
        p2 = getpass.getpass("Confirm passphrase: ")
        if p1 != p2:
            print("Passphrases do not match, try again.")
            continue
        return p1