"""Filename sanitization for uploaded files.

Strips path traversal components, null bytes, and unsafe characters to
prevent directory-traversal attacks and filesystem issues.
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import PurePosixPath

# Characters allowed in sanitized filenames: alphanumeric, hyphen, underscore, dot.
_SAFE_CHARS = re.compile(r"[^\w.\-]", re.ASCII)

MAX_FILENAME_LENGTH = 255


def sanitize_filename(filename: str) -> str:
    """Return a safe, flat filename from an untrusted user-supplied string.

    - Strips directory components (path traversal like ``../../etc/passwd``)
    - Removes null bytes and control characters
    - Normalises Unicode to ASCII-safe form
    - Replaces unsafe characters with underscores
    - Collapses consecutive dots/underscores
    - Falls back to ``"unnamed"`` if the result is empty
    - Truncates to 255 characters
    """
    # Remove null bytes first — they can bypass downstream checks.
    filename = filename.replace("\x00", "")

    # Normalise Unicode to NFKD and strip non-ASCII to avoid homoglyph attacks.
    filename = unicodedata.normalize("NFKD", filename).encode("ascii", "ignore").decode("ascii")

    # Extract only the final path component — defeats ../ traversal.
    filename = PurePosixPath(filename).name

    # Also handle Windows-style backslash separators.
    if "\\" in filename:
        filename = filename.rsplit("\\", 1)[-1]

    # Strip leading dots to prevent hidden files (e.g. .htaccess, .env).
    filename = filename.lstrip(".")

    # Replace unsafe characters with underscores.
    filename = _SAFE_CHARS.sub("_", filename)

    # Collapse runs of underscores and dots.
    filename = re.sub(r"[_.]{2,}", "_", filename)

    # Strip leading/trailing underscores and dots.
    filename = filename.strip("_.")

    # Truncate to filesystem limit.
    if len(filename) > MAX_FILENAME_LENGTH:
        filename = filename[:MAX_FILENAME_LENGTH]

    return filename or "unnamed"
