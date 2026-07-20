"""Test the UI-side periodic watchdog sweep.

run_watchdog_once() runs in the long-lived UI process and must reap abandoned
jobs (clean_old_jobs) and orphaned makemkvcon processes (reap_orphan_makemkv)
inside a Flask app context, so a stuck job is caught even when no new disc is
inserted.

Runs in-container (imports arm.runui, which builds the Flask app).
"""
import sys
import unittest
from unittest import mock

sys.path.insert(0, '/opt/arm')
import arm.runui as runui                 # noqa: E402
import arm.ripper.utils as ripper_utils   # noqa: E402


class TestRunWatchdogOnce(unittest.TestCase):

    def test_sweep_calls_both_reapers(self):
        with mock.patch.object(ripper_utils, 'clean_old_jobs') as clean, \
             mock.patch.object(ripper_utils, 'reap_orphan_makemkv') as reap:
            runui.run_watchdog_once()
        clean.assert_called_once()
        reap.assert_called_once()


if __name__ == '__main__':
    unittest.main()
