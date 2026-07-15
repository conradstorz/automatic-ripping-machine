"""Label-storage tests for the Job model source sites.

job.label is untrusted disc metadata but is kept RAW at the source: it feeds
metadata lookup (OMDb/TMDB/MusicBrainz), the dupe-check DB query, and UI
display, all of which want the original string. Sanitization happens only at
the filesystem-path sinks (rip_data, logger), never here. These tests pin that
the udev ID_FS_LABEL and lsdvd sources store the label verbatim.
"""
import sys
import subprocess
import unittest
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, '/opt/arm')
from arm.models.job import Job, _parse_lsdvd_title   # noqa: E402


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


class TestParseLsdvdTitle(unittest.TestCase):

    def test_extracts_disc_title(self):
        self.assertEqual(_parse_lsdvd_title("Disc Title: Cool Film\nTitle: 01\n"), "Cool Film")

    def test_no_title_line_returns_empty(self):
        self.assertEqual(_parse_lsdvd_title("some other lsdvd output\n"), "")

    def test_title_containing_colon_preserved(self):
        self.assertEqual(_parse_lsdvd_title("Disc Title: Vol: 2\n"), "Vol: 2")


class TestLsdvdLabel(unittest.TestCase):

    def _run_lsdvd_branch(self, stdout_bytes, returncode=0):
        job = make_bare_job()
        job.disctype = "dvd"
        completed = SimpleNamespace(stdout=stdout_bytes, returncode=returncode)
        with mock.patch("arm.models.job.subprocess.run",
                        return_value=completed) as mock_run:
            Job._apply_lsdvd_label(job)
        return job, mock_run

    def test_lsdvd_label_is_stored_raw(self):
        job, _ = self._run_lsdvd_branch(b"Disc Title: Cool Film\n")
        self.assertEqual(job.label, "Cool Film")

    def test_lsdvd_label_with_path_chars_kept_raw(self):
        job, _ = self._run_lsdvd_branch(b"Disc Title: Disc 1/2\n")
        self.assertEqual(job.label, "Disc 1/2")

    def test_lsdvd_runs_list_form_without_shell_with_timeout(self):
        # No shell: the device path is an argv element; and a timeout guards
        # against a hanging lsdvd blocking disc-insert processing.
        _, mock_run = self._run_lsdvd_branch(b"Disc Title: X\n")
        args, kwargs = mock_run.call_args
        self.assertIsInstance(args[0], list)
        self.assertEqual(args[0][0], "lsdvd")
        self.assertNotIn("shell", kwargs)
        self.assertIn("timeout", kwargs)

    def test_lsdvd_nonzero_exit_still_parses_title(self):
        # lsdvd can print a usable Disc Title yet exit nonzero (e.g. a CSS
        # warning); the old grep|cut pipeline masked the exit code, so we must
        # still capture the title rather than dropping it. fake_run mimics real
        # subprocess.run: check=True raises on the nonzero exit, so the code
        # must run with check=False to keep the title.
        def fake_run(cmd, **kwargs):
            if kwargs.get("check"):
                raise subprocess.CalledProcessError(1, cmd)
            return SimpleNamespace(stdout=b"Disc Title: Cool Film\n", returncode=1)

        job = make_bare_job()
        job.disctype = "dvd"
        with mock.patch("arm.models.job.subprocess.run", side_effect=fake_run):
            Job._apply_lsdvd_label(job)
        self.assertEqual(job.label, "Cool Film")

    def _assert_tolerates(self, error):
        job = make_bare_job()
        job.disctype = "dvd"
        with mock.patch("arm.models.job.subprocess.run", side_effect=error):
            Job._apply_lsdvd_label(job)   # must not raise
        self.assertIn(job.label, (None, ""))

    def test_lsdvd_missing_binary_is_tolerated(self):
        self._assert_tolerates(FileNotFoundError("lsdvd"))

    def test_lsdvd_permission_error_is_tolerated(self):
        self._assert_tolerates(PermissionError("lsdvd"))

    def test_lsdvd_timeout_is_tolerated(self):
        self._assert_tolerates(subprocess.TimeoutExpired(["lsdvd"], 60))


if __name__ == '__main__':
    unittest.main()
