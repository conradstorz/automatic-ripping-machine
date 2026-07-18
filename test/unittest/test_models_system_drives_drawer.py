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


if __name__ == '__main__':
    unittest.main()
