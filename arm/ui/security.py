"""Security helpers for the ARM web UI.

Dependency-light on purpose (stdlib only) so it can be unit-tested without
constructing the Flask app.
"""
import os
import logging
import secrets

SECRET_KEY_FILENAME = "secret_key"


def load_or_create_secret_key(config_dir: str) -> str:
    """Return a stable Flask secret key, persisted in ``config_dir``.

    Reads ``<config_dir>/secret_key`` if it exists and is non-empty; otherwise
    generates a new key and writes it with owner-only permissions. If the
    directory cannot be read or written, logs a warning and returns the
    freshly generated key for this run (sessions will not survive a restart in
    that degraded case).
    """
    key_path = os.path.join(config_dir, SECRET_KEY_FILENAME)
    try:
        if os.path.isfile(key_path):
            with open(key_path, "r", encoding="utf-8") as key_file:
                existing = key_file.read().strip()
            if existing:
                return existing
    except OSError as error:
        logging.warning(
            "Could not read secret key in %s (%s); regenerating.",
            config_dir, error)

    key = secrets.token_hex(32)
    try:
        # Create with owner-only perms from the start (no world-readable
        # window); O_TRUNC handles an existing empty/partial file.
        fd = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            os.write(fd, key.encode("utf-8"))
        finally:
            os.close(fd)
        os.chmod(key_path, 0o600)
    except OSError as error:
        logging.warning(
            "Could not persist secret key in %s (%s); "
            "using a temporary key for this run.", config_dir, error)
    return key


def generate_debug_pin() -> str:
    """Return a fresh random Werkzeug debugger PIN (not persisted)."""
    return secrets.token_hex(8)
