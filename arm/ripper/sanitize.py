"""Sanitization helpers for untrusted optical-disc metadata.

Stdlib-only (``re``) so it can be imported from both ``arm.models.job`` and
``arm.ripper.utils`` without an import cycle, and unit-tested in isolation.
"""
import re

_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")
_MULTI_DOT = re.compile(r"\.{2,}")


def sanitize_label(raw):
    """Return a filesystem-safe, still-readable version of a disc label.

    Removes only what is dangerous for use as a single path component:
    control/DEL characters, path separators (``/`` and ``\\``), and runs of
    dots (``..`` traversal). Ordinary characters (letters, digits, spaces,
    ``& : ( ) - _`` ...) are preserved so labels keep their original look.
    Returns the input unchanged if it is falsy (``""``/``None``).

    This is the SECURITY sink for untrusted disc metadata: use it wherever a
    label from udev/lsdvd/MusicBrainz becomes a path. It is intentionally
    distinct from ``clean_for_filename`` (``arm.ripper.utils`` /
    ``arm.ui.utils``), which is an *aesthetic* filename cleaner (rewrites
    ``&``->``and``, ``:``->``-``, strips brackets) and is not a safety boundary.
    Keep the "what is unsafe in a path component" rules here, not there.
    """
    if not raw:
        return raw
    text = _CONTROL_CHARS.sub("", str(raw))
    text = text.replace("/", "").replace("\\", "")
    text = _MULTI_DOT.sub(".", text)
    return text.strip().strip(".").strip()
