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
    generates a new key, writes it with owner-only permissions, and returns it.
    If the directory cannot be read or written, logs a warning and returns a
    fresh in-memory key so the app still boots (sessions will not survive a
    restart in that degraded case).
    """
    key_path = os.path.join(config_dir, SECRET_KEY_FILENAME)
    try:
        if os.path.isfile(key_path):
            with open(key_path, "r", encoding="utf-8") as key_file:
                existing = key_file.read().strip()
            if existing:
                return existing
        key = secrets.token_hex(32)
        with open(key_path, "w", encoding="utf-8") as key_file:
            key_file.write(key)
        os.chmod(key_path, 0o600)
        return key
    except OSError as error:
        logging.warning(
            "Could not read or persist secret key in %s (%s); "
            "using a temporary key for this run.", config_dir, error)
        return secrets.token_hex(32)


def generate_debug_pin() -> str:
    """Return a fresh random Werkzeug debugger PIN (not persisted)."""
    return secrets.token_hex(8)
