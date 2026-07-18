"""Tests for SystemDrives.drawer_status — the human-readable tray label.

The drawer status shown per drive in Settings -> Drives maps the kernel
CDROM_DRIVE_STATUS ioctl result (the CDS enum) to a plain 'Open' / 'Closed' /
'Unavailable' string. These pin that mapping so the UI label stays in sync
with the open/closed icon that reads the same tray value.
"""
import sys
import unittest

sys.path.insert(0, '/opt/arm')
from arm.models.system_drives import SystemDrives, CDS   # noqa: E402
from arm.models.job import Job   # noqa: E402


def make_bare_drive():
    """A SystemDrives instance without __init__ (mapped columns assignable).

    Mirrors make_bare_job() in test_models_job_label.py: uses SQLAlchemy's
    class manager so the instance is instrumented but __init__ (which needs
    udev/config) is skipped.
    """
    drive = SystemDrives._sa_class_manager.new_instance()
    drive.stale = False
    drive._tray = None
    return drive


class TestDrawerStatus(unittest.TestCase):

    def _drive(self, tray_value, stale=False):
        drive = make_bare_drive()
        drive.stale = stale
        drive.tray = tray_value   # setter stores CDS(value).value
        return drive

    def test_tray_open_reports_open(self):
        self.assertEqual(self._drive(CDS.TRAY_OPEN.value).drawer_status, "Open")

    def test_disc_ok_reports_closed(self):
        self.assertEqual(self._drive(CDS.DISC_OK.value).drawer_status, "Closed")

    def test_no_disc_reports_closed(self):
        self.assertEqual(self._drive(CDS.NO_DISC.value).drawer_status, "Closed")

    def test_no_info_reports_closed(self):
        self.assertEqual(self._drive(CDS.NO_INFO.value).drawer_status, "Closed")

    def test_drive_not_ready_reports_closed(self):
        self.assertEqual(self._drive(CDS.DRIVE_NOT_READY.value).drawer_status, "Closed")

    def test_error_tray_reports_unavailable(self):
        # _tray is None -> CDS(None) is CDS.ERROR -> not a readable state
        self.assertEqual(self._drive(None).drawer_status, "Unavailable")

    def test_stale_drive_reports_unavailable(self):
        # even with an otherwise readable tray value, a stale drive is unavailable
        self.assertEqual(self._drive(CDS.DISC_OK.value, stale=True).drawer_status, "Unavailable")


class TestStatusLabel(unittest.TestCase):
    """SystemDrives.status_label -> chip label: Ripping/Idle/Open/Unavailable.

    Mirrors the drive-icon precedence: Unavailable > Open > Ripping > Idle.
    """

    def _drive(self, tray_value, stale=False, ripping=False):
        drive = make_bare_drive()
        drive.stale = stale
        drive.tray = tray_value
        # setting the relationship drives the .processing property
        drive.job_current = Job._sa_class_manager.new_instance() if ripping else None
        return drive

    def test_closed_with_job_is_ripping(self):
        self.assertEqual(self._drive(CDS.DISC_OK.value, ripping=True).status_label, "Ripping")

    def test_closed_no_job_is_idle(self):
        self.assertEqual(self._drive(CDS.DISC_OK.value).status_label, "Idle")

    def test_empty_closed_is_idle(self):
        self.assertEqual(self._drive(CDS.NO_DISC.value).status_label, "Idle")

    def test_open_is_open(self):
        self.assertEqual(self._drive(CDS.TRAY_OPEN.value).status_label, "Open")

    def test_error_is_unavailable(self):
        self.assertEqual(self._drive(None).status_label, "Unavailable")

    def test_stale_is_unavailable(self):
        self.assertEqual(self._drive(CDS.DISC_OK.value, stale=True).status_label, "Unavailable")

    def test_unavailable_beats_ripping(self):
        # a stale drive with a lingering job still reads Unavailable (can't trust it)
        self.assertEqual(
            self._drive(CDS.DISC_OK.value, stale=True, ripping=True).status_label,
            "Unavailable")


if __name__ == '__main__':
    unittest.main()
