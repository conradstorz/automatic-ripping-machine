"""Tests for the ripper-side watchdog helpers:

- sleep_check_process must not loop forever when the makemkvcon slot never
  frees (D5 cascade: a lingering hung makemkvcon kept the process count up, so
  a later job's sleep_check_process would spin unbounded).
- reap_orphan_makemkv must kill only makemkvcon processes reparented to init
  (ppid 1, i.e. their ARM parent died), never a makemkvcon with a live parent
  (an active rip).

Runs in-container (imports arm.ripper.utils).
"""
import sys
import unittest
from unittest import mock

sys.path.insert(0, '/opt/arm')
import arm.ripper.utils as utils          # noqa: E402
import arm.config.config as cfg           # noqa: E402


class FakeProc:
    def __init__(self, name, pid, ppid):
        self.info = {'name': name, 'pid': pid, 'ppid': ppid}
        self.killed = False

    def kill(self):
        self.killed = True


class TestSleepCheckProcessBounded(unittest.TestCase):

    def test_returns_after_max_wait_when_slot_never_frees(self):
        """When the process count stays over the limit, the loop must give up
        after MAKEMKV_CONCURRENT_WAIT_MAX_SECS instead of spinning forever."""
        orig = cfg.arm_config.get('MAKEMKV_CONCURRENT_WAIT_MAX_SECS')
        cfg.arm_config['MAKEMKV_CONCURRENT_WAIT_MAX_SECS'] = 3
        # Always report 5 makemkvcon processes running (>= max_processes=1).
        procs = [FakeProc('makemkvcon', i, 100) for i in range(5)]
        try:
            with mock.patch.object(utils.psutil, 'process_iter', return_value=procs), \
                 mock.patch.object(utils.time, 'sleep') as fake_sleep:
                # If the loop were unbounded this call would never return.
                result = utils.sleep_check_process('makemkvcon', 1, sleep=(1, 2, 1))
            self.assertTrue(result)
            self.assertTrue(fake_sleep.called, "should have slept at least once before giving up")
        finally:
            if orig is None:
                cfg.arm_config.pop('MAKEMKV_CONCURRENT_WAIT_MAX_SECS', None)
            else:
                cfg.arm_config['MAKEMKV_CONCURRENT_WAIT_MAX_SECS'] = orig

    def test_disabled_when_max_processes_zero(self):
        """Unchanged behavior: a limit of 0 disables the check immediately."""
        self.assertFalse(utils.sleep_check_process('makemkvcon', 0))


class TestReapOrphanMakemkv(unittest.TestCase):

    def test_kills_only_orphaned_makemkvcon(self):
        orphan = FakeProc('makemkvcon', 111, 1)        # reparented to init -> orphan
        active = FakeProc('makemkvcon', 222, 4242)     # live ARM parent -> leave alone
        other = FakeProc('HandBrakeCLI', 333, 1)       # not makemkvcon -> leave alone
        with mock.patch.object(utils.psutil, 'process_iter',
                               return_value=[orphan, active, other]):
            killed = utils.reap_orphan_makemkv()
        self.assertTrue(orphan.killed)
        self.assertFalse(active.killed)
        self.assertFalse(other.killed)
        self.assertEqual(killed, [111])


if __name__ == '__main__':
    unittest.main()
