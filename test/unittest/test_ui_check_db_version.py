"""Regression test for check_db_version when the DB file cannot be created.

check_db_version() tries to create a missing DB via flask_migrate.upgrade. If
that fails to produce the file (permissions / bad path), the function used to
fall through to `c.execute(...)` with the sqlite cursor `c` never assigned,
raising an opaque `UnboundLocalError: local variable 'c'`. This is the real
source of the 500 on /history and /database when the DB is genuinely missing
and uncreatable. The function must instead fail cleanly (log + return).

We reproduce faithfully at the function level: point db_file at a path that
gets a directory but no file (flask_migrate.upgrade runs against the app's
real engine, not this path, so it never creates db_file). Before the fix this
raised UnboundLocalError; after the fix it returns without raising.

Runs in-container like the other arm.ui tests.
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, '/opt/arm')
import arm.ui.utils as ui_utils          # noqa: E402
import arm.config.config as cfg          # noqa: E402


class TestCheckDbVersionUncreatable(unittest.TestCase):

    def test_returns_cleanly_when_file_cannot_be_created(self):
        install_path = cfg.arm_config['INSTALLPATH']
        with tempfile.TemporaryDirectory() as d:
            # dirname is creatable, but nothing will create the db file itself
            bogus = os.path.join(d, 'sub', 'arm.db')
            try:
                result = ui_utils.check_db_version(install_path, bogus)
            except UnboundLocalError as e:  # the original bug
                self.fail(f"check_db_version raised UnboundLocalError: {e}")
            self.assertIsNone(result)
            self.assertFalse(os.path.isfile(bogus))


if __name__ == '__main__':
    unittest.main()
