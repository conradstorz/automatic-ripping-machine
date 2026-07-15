"""Label-storage tests for the Job model source sites.

job.label is untrusted disc metadata but is kept RAW at the source: it feeds
metadata lookup (OMDb/TMDB/MusicBrainz), the dupe-check DB query, and UI
display, all of which want the original string. Sanitization happens only at
the filesystem-path sinks (rip_data, logger), never here. These tests pin that
the udev ID_FS_LABEL and lsdvd sources store the label verbatim.
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

    def test_label_is_stored_raw(self):
        job = self._run_parse_udev([("ID_FS_LABEL", "My Movie")])
        self.assertEqual(job.label, "My Movie")

    def test_label_with_path_chars_kept_raw(self):
        # Path-unsafe characters are NOT stripped at the source; that happens
        # only at the path sinks. Metadata/dupe-check want the original string.
        job = self._run_parse_udev([("ID_FS_LABEL", "Movie: 2/2")])
        self.assertEqual(job.label, "Movie: 2/2")

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

    def test_lsdvd_label_is_stored_raw(self):
        job = self._run_lsdvd_branch(b"Cool Film")
        self.assertEqual(job.label, "Cool Film")

    def test_lsdvd_label_with_path_chars_kept_raw(self):
        job = self._run_lsdvd_branch(b"Disc 1/2")
        self.assertEqual(job.label, "Disc 1/2")


if __name__ == '__main__':
    unittest.main()
