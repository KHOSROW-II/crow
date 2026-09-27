"""
Helpers for rendering Persian / Arabic text inside Tkinter widgets.

Tkinter does not shape Arabic script nor apply BiDi ordering natively
on classic widgets, so we must reshape the text (join letters) and
reverse the visual order (RTL) before passing it to the widget.
"""

try:
    import arabic_reshaper
    from bidi.algorithm import get_display
    HAS_BIDI = True
except ImportError:
    HAS_BIDI = False


def fa(text) -> str:
    """Shape and reverse a single-line Persian string for Tk display."""
    if text is None:
        return ""
    s = str(text)
    if not HAS_BIDI or not s.strip():
        return s
    try:
        return get_display(arabic_reshaper.reshape(s))
    except Exception:
        return s


def fa_lines(text) -> str:
    """Shape each line of a (possibly) multi-line Persian string."""
    if text is None:
        return ""
    return "\n".join(fa(line) for line in str(text).split("\n"))


def fa_multi(*values) -> str:
    """Apply fa() to each value and join with spaces."""
    return " ".join(fa(v) for v in values if v)


def is_persian(text) -> bool:
    if text is None:
        return False
    return any("\u0600" <= c <= "\u06ff" for c in str(text))