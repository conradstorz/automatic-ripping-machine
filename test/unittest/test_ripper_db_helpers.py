"""Tests for database_updater / database_adder failure handling.

Both retry a commit while the SQLite DB is locked. The bug: neither returned
failure when the DB stayed locked for ALL retries -- control fell through to
`return True`, so a write that never landed was reported as success (silent job-
state loss under UI+ripper contention). database_updater also lacked a `break`
on success. Fixed to break on success and return False (after rollback) on
lock-exhaustion, and to rollback before raising a non-locked error.

Runs in-container (imports arm.ripper.utils).
"""
import sys
import unittest
from unittest import mock

sys.path.insert(0, '/opt/arm')
import arm.ripper.utils as utils   # noqa: E402


class _LockedError(Exception):
    """Stand-in for a SQLite 'database is locked' OperationalError."""
    def __str__(self):
        return "(sqlite3.OperationalError) database is locked"


class TestDatabaseUpdater(unittest.TestCase):

    def test_success_commits_once_and_returns_true(self):
        job = mock.Mock()
        with mock.patch.object(utils.db.session, 'commit') as commit, \
             mock.patch.object(utils.db.session, 'rollback') as rollback:
            result = utils.database_updater({'status': 'success'}, job, wait_time=5)
        self.assertTrue(result)
        commit.assert_called_once()          # break on success, no re-commits
        rollback.assert_not_called()

    def test_locked_forever_returns_false_and_rolls_back(self):
        job = mock.Mock()
        with mock.patch.object(utils.db.session, 'commit', side_effect=_LockedError()), \
             mock.patch.object(utils.db.session, 'rollback') as rollback, \
             mock.patch.object(utils.time, 'sleep'):
            result = utils.database_updater({'status': 'x'}, job, wait_time=3)
        self.assertFalse(result, "a never-committed write must not report success")
        rollback.assert_called()

    def test_non_locked_error_rolls_back_then_raises(self):
        job = mock.Mock()
        with mock.patch.object(utils.db.session, 'commit', side_effect=ValueError("boom")), \
             mock.patch.object(utils.db.session, 'rollback') as rollback:
            with self.assertRaises(RuntimeError):
                utils.database_updater({'status': 'x'}, job, wait_time=3)
        rollback.assert_called()


class TestDatabaseAdder(unittest.TestCase):

    def test_success_returns_true(self):
        with mock.patch.object(utils.db.session, 'add'), \
             mock.patch.object(utils.db.session, 'commit') as commit, \
             mock.patch.object(utils.db.session, 'rollback'):
            result = utils.database_adder(mock.Mock())
        self.assertTrue(result)
        commit.assert_called_once()

    def test_locked_forever_returns_false(self):
        with mock.patch.object(utils.db.session, 'add'), \
             mock.patch.object(utils.db.session, 'commit', side_effect=_LockedError()), \
             mock.patch.object(utils.db.session, 'rollback') as rollback, \
             mock.patch.object(utils.time, 'sleep'):
            result = utils.database_adder(mock.Mock())
        self.assertFalse(result, "a never-committed add must not report success")
        rollback.assert_called()


if __name__ == '__main__':
    unittest.main()
