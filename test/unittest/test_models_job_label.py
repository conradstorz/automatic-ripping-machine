"""Label-sanitization regression tests for the Job model source sites.

sanitize_label can reduce a non-empty raw label (e.g. "///" or "...") to an
empty string. The udev ID_FS_LABEL and lsdvd source sites must not let that
empty result clobber the label into an empty path component; a good label must
still be applied (and sanitized).
"""
import sys
import unittest
from unittest import mock

sys.path.insert(0, '/opt/arm')
from arm.models.job import Job   # noqa: E402


def make_bare_job():
    """A Job instance without running __init__ (which needs udev/config).

    Uses SQLAlchemy's class manager so the instance is instrumented (mapped
    columns are assignable) but __init__ is skipped.
    """
    job = Job._sa_class_manager.new_instance()
    job.devpath = "/dev/sr0"
    job.label = None
    job.disctype = "unknown"
    return job


class TestParseUdevLabel(unittest.TestCase):

    def _run_parse_udev(self, udev_items):
        job = make_bare_job()
        with mock.patch("arm.models.job.pyudev") as mock_pyudev:
            mock_pyudev.Devices.from_device_file.return_value = dict(udev_items)
            job.parse_udev()
        return job

    def test_good_label_is_applied(self):
        job = self._run_parse_udev([("ID_FS_LABEL", "My Movie")])
        self.assertEqual(job.label, "My Movie")

    def test_garbage_label_does_not_become_empty_string(self):
        # "///" sanitizes to "" — it must NOT overwrite the label with an empty
        # path component; the prior value (None) is preserved instead.
        job = self._run_parse_udev([("ID_FS_LABEL", "///")])
        self.assertNotEqual(job.label, "")

    def test_iso9660_still_sets_data_disctype(self):
        job = self._run_parse_udev([("ID_FS_LABEL", "iso9660")])
        self.assertEqual(job.disctype, "data")


class TestLsdvdLabel(unittest.TestCase):

    def _run_lsdvd_branch(self, raw_lsdvd_output):
        job = make_bare_job()
        job.disctype = "dvd"
        # Reproduce the lsdvd fallback branch from Job.__init__ without the rest
        # of construction: sanitize the (mocked) lsdvd output into the label.
        with mock.patch("arm.models.job.subprocess.check_output",
                        return_value=raw_lsdvd_output):
            Job._apply_lsdvd_label(job)
        return job

    def test_good_lsdvd_label_is_applied(self):
        job = self._run_lsdvd_branch(b"Cool Film")
        self.assertEqual(job.label, "Cool Film")

    def test_garbage_lsdvd_label_does_not_become_empty_string(self):
        job = self._run_lsdvd_branch(b"...")
        self.assertNotEqual(job.label, "")


if __name__ == '__main__':
    unittest.main()
