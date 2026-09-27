"""
Universal image loader for Tkinter and DB blob helpers.
"""

import importlib
from pathlib import Path
from typing import Any

import tkinter as tk


HAS_PIL = False
Image: Any = None
ImageTk: Any = None

try:
    Image = importlib.import_module("PIL.Image")
    ImageTk = importlib.import_module("PIL.ImageTk")
    HAS_PIL = True
except Exception:
    HAS_PIL = False


SUPPORTED_EXTS = (
    ".png", ".jpg", ".jpeg", ".gif", ".bmp",
    ".webp", ".tif", ".tiff", ".ico", ".ppm", ".pgm",
)


def is_image_file(path) -> bool:
    if not path:
        return False
    return Path(path).suffix.lower() in SUPPORTED_EXTS


# ------------------------------------------------------------
# Load from bytes (DB stored images)
# ------------------------------------------------------------
def load_photo_for_tk_from_bytes(data: bytes, max_size=(320, 320)):
    """
    Return a Tk PhotoImage for the given raw image bytes.
    Uses PIL if available, else tk.PhotoImage (PNG/GIF only).
    """
    if not data:
        return None
    max_w, max_h = max_size

    if HAS_PIL and Image is not None and ImageTk is not None:
        try:
            from io import BytesIO
            img = Image.open(BytesIO(data))
            try:
                img.seek(0)
            except Exception:
                pass
            if img.mode not in ("RGB", "RGBA"):
                img = img.convert("RGBA")
            img.thumbnail((max_w, max_h))
            return ImageTk.PhotoImage(img)
        except Exception:
            pass

    try:
        tkimg = tk.PhotoImage(data=data)
        w, h = tkimg.width(), tkimg.height()
        if w > max_w or h > max_h:
            factor = max((w - 1) // max_w, (h - 1) // max_h) + 1
            tkimg = tkimg.subsample(factor, factor)
        return tkimg
    except Exception:
        return None


# ------------------------------------------------------------
# Load from a file on disk
# ------------------------------------------------------------
def load_photo_for_tk(path, max_size=(320, 320)):
    if not path:
        return None
    p = Path(path)
    if not p.is_absolute():
        p = Path.cwd() / p
    if not p.exists():
        return None
    try:
        return load_photo_for_tk_from_bytes(p.read_bytes(), max_size)
    except Exception:
        return None