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
from unittest import mock

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


class TestCheckDbVersionClosesConnection(unittest.TestCase):
    """The sqlite connection opened to verify a freshly-created DB must be
    closed (via contextlib.closing) on every exit path."""

    def _run(self, head, db_ver):
        install_path = cfg.arm_config['INSTALLPATH']
        fake_conn = mock.MagicMock()
        fake_conn.cursor.return_value.fetchone.return_value = (db_ver,)
        # isfile: False on the create check, True after "upgrade" so we proceed.
        isfile_returns = iter([False, True])
        with mock.patch('sqlite3.connect', return_value=fake_conn), \
             mock.patch.object(ui_utils.os.path, 'isfile',
                               side_effect=lambda _p: next(isfile_returns)), \
             mock.patch.object(ui_utils, 'make_dir'), \
             mock.patch.object(ui_utils.shutil, 'copy'), \
             mock.patch('flask_migrate.upgrade'), \
             mock.patch('alembic.script.ScriptDirectory.from_config') as m_script:
            m_script.return_value.get_current_head.return_value = head
            raised = None
            try:
                ui_utils.check_db_version(install_path, "/tmp/fake_arm.db")
            except RuntimeError as exc:
                raised = exc
        return fake_conn, raised

    def test_connection_closed_on_up_to_date_path(self):
        fake_conn, exc = self._run(head="rev1", db_ver="rev1")
        self.assertIsNone(exc)
        fake_conn.close.assert_called_once()

    def test_connection_closed_even_when_it_raises(self):
        # A persistent post-upgrade mismatch raises RuntimeError; the connection
        # must still be closed by closing().
        fake_conn, exc = self._run(head="rev2", db_ver="rev1")
        self.assertIsInstance(exc, RuntimeError)
        fake_conn.close.assert_called_once()


if __name__ == '__main__':
    unittest.main()
