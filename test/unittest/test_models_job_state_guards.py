"""The finished/idle/ripping properties must not raise on an unset/legacy status.

JobState(self.status) raises ValueError when status is None (a freshly built
Job) or an unrecognized string (a row from an older schema). These properties
are read by the ripper and by drive/eject logic, so they must degrade to False
instead of crashing the caller.

Runs in-container (imports arm.models.job).
"""
import sys
import unittest

sys.path.insert(0, '/opt/arm')
from arm.models.job import Job   # noqa: E402


class TestJobStateGuards(unittest.TestCase):

    def _job(self, status):
        # instrumented instance without __init__ (which needs udev/config)
        job = Job._sa_class_manager.new_instance()
        job.status = status
        return job

    def test_none_status_is_not_finished_idle_or_ripping(self):
        job = self._job(None)
        self.assertFalse(job.finished)
        self.assertFalse(job.idle)
        self.assertFalse(job.ripping)

    def test_unknown_status_is_not_finished_idle_or_ripping(self):
        job = self._job("some_legacy_status")
        self.assertFalse(job.finished)
        self.assertFalse(job.idle)
        self.assertFalse(job.ripping)

    def test_known_status_still_works(self):
        self.assertTrue(self._job("success").finished)
        self.assertTrue(self._job("active").idle)
        self.assertTrue(self._job("ripping").ripping)
        self.assertFalse(self._job("success").ripping)


if __name__ == '__main__':
    unittest.main()
