"""Tests for ejecting failed/abandoned discs still sitting in the tray.

Two paths keep a failed disc from getting stuck in a closed tray:

1. Job.eject(force=...) - a forced eject overrides the AUTO_EJECT config so a
   *failed* rip always pops its disc out, while a successful rip still obeys
   AUTO_EJECT (a deliberate keep-the-disc-in choice).
2. clean_old_jobs() - when the zombie sweep marks an abandoned rip as failed,
   it also force-ejects that drive so the orphaned disc does not sit forever.
"""
import sys
import unittest
from unittest import mock

sys.path.insert(0, '/opt/arm')
import arm.models.job as job_module   # noqa: E402
from arm.models.job import Job, JobState   # noqa: E402
from arm.models.system_drives import SystemDrives   # noqa: E402
import arm.ripper.utils as utils   # noqa: E402


def make_bare_job():
    """A Job instance without __init__ (mapped columns assignable)."""
    job = Job._sa_class_manager.new_instance()
    job.ejected = False
    return job


def make_bare_drive():
    """A SystemDrives instance without __init__."""
    return SystemDrives._sa_class_manager.new_instance()


def attach_drive(job):
    """Give the job a drive via the SQLAlchemy backref and stub its hardware
    calls so nothing touches a real device."""
    drive = make_bare_drive()
    drive.job_current = job   # backref sets job.drive = drive
    drive.eject = mock.Mock(name="drive.eject")
    drive.release_current_job = mock.Mock(name="drive.release_current_job")
    return drive


class TestJobEjectForce(unittest.TestCase):

    def _eject(self, auto_eject, force, ejected=False, with_drive=True):
        job = make_bare_job()
        job.ejected = ejected
        drive = attach_drive(job) if with_drive else None
        with mock.patch.object(job_module.cfg, 'arm_config', {'AUTO_EJECT': auto_eject}):
            job.eject(force=force)
        return job, drive

    def test_auto_eject_off_not_forced_skips_eject(self):
        job, drive = self._eject(auto_eject=False, force=False)
        drive.eject.assert_not_called()
        drive.release_current_job.assert_called_once()
        self.assertFalse(job.ejected)

    def test_forced_overrides_auto_eject_off(self):
        job, drive = self._eject(auto_eject=False, force=True)
        drive.eject.assert_called_once()
        self.assertTrue(job.ejected)

    def test_auto_eject_on_ejects_without_force(self):
        job, drive = self._eject(auto_eject=True, force=False)
        drive.eject.assert_called_once()
        self.assertTrue(job.ejected)

    def test_already_ejected_is_noop(self):
        job, drive = self._eject(auto_eject=True, force=True, ejected=True)
        drive.eject.assert_not_called()

    def test_no_drive_forced_does_not_raise(self):
        # Abandoned jobs whose drive was reassigned have drive is None.
        job, _ = self._eject(auto_eject=False, force=True, with_drive=False)
        self.assertFalse(job.ejected)

    def test_force_defaults_to_false(self):
        # Preserve the existing signature default: a plain eject() on a
        # success with AUTO_EJECT off must not eject.
        job = make_bare_job()
        drive = attach_drive(job)
        with mock.patch.object(job_module.cfg, 'arm_config', {'AUTO_EJECT': False}):
            job.eject()
        drive.eject.assert_not_called()


class TestCleanOldJobsEjects(unittest.TestCase):

    def _run_clean_with(self, job, pid_exists):
        """Run clean_old_jobs() with the DB query returning `job` and psutil
        reporting whether its pid is alive."""
        db_mock = mock.MagicMock()
        db_mock.session.query.return_value.filter.return_value.all.return_value = [job]
        with mock.patch.object(utils, 'db', db_mock), \
                mock.patch.object(utils, 'psutil') as psutil_mock, \
                mock.patch.object(utils, 'database_updater'):
            psutil_mock.pid_exists.return_value = pid_exists
            utils.clean_old_jobs()

    def test_abandoned_job_is_force_ejected(self):
        job = make_bare_job()
        job.pid = 4242
        job.eject = mock.Mock(name="job.eject")
        self._run_clean_with(job, pid_exists=False)
        self.assertEqual(job.status, JobState.FAILURE.value)
        job.eject.assert_called_once_with(force=True)

    def test_running_job_is_not_ejected(self):
        job = make_bare_job()
        job.pid = 4242
        job.pid_hash = None
        job.eject = mock.Mock(name="job.eject")
        # pid alive: hash() of the fake process won't match None, but either
        # way a live job must never be ejected.
        with mock.patch.object(utils, 'db', mock.MagicMock()) as db_mock, \
                mock.patch.object(utils, 'psutil') as psutil_mock, \
                mock.patch.object(utils, 'database_updater'):
            db_mock.session.query.return_value.filter.return_value.all.return_value = [job]
            psutil_mock.pid_exists.return_value = True
            proc = mock.Mock()
            psutil_mock.Process.return_value = proc
            utils.clean_old_jobs()
        job.eject.assert_not_called()


if __name__ == '__main__':
    unittest.main()
