"""Error-handling regression tests for utils.rip_data.

The switch to list-form ``dd`` (no shell) narrowed the set of exceptions that
reach ``rip_data``'s handler, which only caught ``CalledProcessError``. These
tests pin the intended contract: any expected rip failure must mark the job
FAILURE and return False, never propagate and crash the ripper mid-job.
"""
import sys
import subprocess
import unittest
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, '/opt/arm')
from arm.ripper import utils   # noqa: E402
from arm.models.job import JobState   # noqa: E402


def make_job():
    return SimpleNamespace(
        label="mydisc",
        devpath="/dev/sr0",
        video_type="unknown",
        logfile="job.log",
        config=SimpleNamespace(RAW_PATH="/raw", COMPLETED_PATH="/done", LOGPATH="/logs"),
    )


class TestRipDataErrorHandling(unittest.TestCase):

    def setUp(self):
        # Stub collaborators so rip_data touches no real filesystem or DB.
        for name, ret in (
            ("make_dir", True),
            ("convert_job_type", "unknown"),
            ("move_files_main", None),
            ("database_updater", None),
        ):
            setattr(self, name, mock.patch.object(utils, name, return_value=ret).start())
        self.rmtree = mock.patch.object(utils.shutil, "rmtree").start()
        # A mutable config dict tests can override per-case.
        mock.patch.object(utils.cfg, "arm_config", {"DATA_RIP_PARAMETERS": "bs=1M"}).start()
        self.addCleanup(mock.patch.stopall)

    def assert_marked_failure(self, result):
        self.assertFalse(result)
        self.database_updater.assert_called_once()
        self.assertEqual(self.database_updater.call_args[0][0]["status"], JobState.FAILURE.value)

    @mock.patch("builtins.open", new_callable=mock.mock_open)
    @mock.patch.object(utils.subprocess, "check_output", side_effect=FileNotFoundError("dd"))
    def test_missing_dd_binary_marks_failure_not_crash(self, mock_check, mock_open_):
        # dd not on PATH -> FileNotFoundError (not CalledProcessError).
        self.assert_marked_failure(utils.rip_data(make_job()))

    def test_malformed_rip_parameters_marks_failure_not_crash(self):
        # Unbalanced quote in admin config -> shlex.split raises ValueError.
        utils.cfg.arm_config["DATA_RIP_PARAMETERS"] = 'bs=1M count="5'
        self.assert_marked_failure(utils.rip_data(make_job()))

    @mock.patch("builtins.open", side_effect=OSError("logpath unwritable"))
    def test_logfile_open_failure_marks_failure_not_crash(self, mock_open_):
        # Opening the job logfile fails -> OSError, not CalledProcessError.
        self.assert_marked_failure(utils.rip_data(make_job()))

    @mock.patch.object(utils.os.path, "exists", return_value=True)
    @mock.patch.object(utils.os, "unlink", side_effect=FileNotFoundError("gone"))
    @mock.patch("builtins.open", new_callable=mock.mock_open)
    @mock.patch.object(utils.subprocess, "check_output",
                       side_effect=subprocess.CalledProcessError(1, "dd"))
    def test_cleanup_unlink_failure_still_marks_failure(self, mock_check, mock_open_, mock_unlink, mock_exists):
        # dd failed before creating the .part file; the cleanup unlink itself
        # raises, but the job must still be marked FAILURE.
        self.assert_marked_failure(utils.rip_data(make_job()))

    @mock.patch.object(utils.os.path, "isfile", return_value=True)
    @mock.patch("builtins.open", new_callable=mock.mock_open)
    @mock.patch.object(utils.subprocess, "check_output", return_value=b"")
    def test_label_not_mutated_by_sanitizing(self, mock_check, mock_open_, mock_isfile):
        # rip_data must sanitize only for path building, not overwrite
        # job.label, so the dupe-check query and display keep the raw value.
        job = make_job()
        job.label = "BACKUP."          # sanitizes to "BACKUP"
        utils.rip_data(job)
        self.assertEqual(job.label, "BACKUP.")

    @mock.patch.object(utils.os.path, "isfile", return_value=False)
    @mock.patch("builtins.open", new_callable=mock.mock_open)
    @mock.patch.object(utils.subprocess, "check_output", return_value=b"")
    def test_silent_move_failure_marks_failure_and_keeps_source(self, mock_check, mock_open_, mock_isfile):
        # dd succeeds but the move silently fails (move_files_main swallows its
        # own errors). rip_data must NOT report success or delete the source.
        result = utils.rip_data(make_job())
        self.assertFalse(result)
        self.database_updater.assert_called_once()
        self.assertEqual(self.database_updater.call_args[0][0]["status"], JobState.FAILURE.value)
        self.rmtree.assert_not_called()


class TestBuildDdCommand(unittest.TestCase):

    def test_returns_list_with_dd_and_operands(self):
        cmd = utils.build_dd_command("/dev/sr0", "/home/arm/raw/x.part", "bs=1M conv=noerror")
        self.assertIsInstance(cmd, list)
        self.assertEqual(cmd[0], "dd")
        self.assertEqual(cmd[1], "if=/dev/sr0")
        self.assertEqual(cmd[2], "of=/home/arm/raw/x.part")
        self.assertEqual(cmd[3:], ["bs=1M", "conv=noerror"])

    def test_destination_is_single_element_no_shell_splitting(self):
        # A destination containing shell metacharacters must remain ONE argv element.
        dest = '/home/arm/raw/a b"; rm -rf ~.part'
        cmd = utils.build_dd_command("/dev/sr0", dest, "")
        self.assertIn(f"of={dest}", cmd)
        self.assertEqual(len([c for c in cmd if c.startswith("of=")]), 1)

    def test_empty_params(self):
        cmd = utils.build_dd_command("/dev/sr0", "/x.part", "")
        self.assertEqual(cmd, ["dd", "if=/dev/sr0", "of=/x.part"])


class TestFixJobTitle(unittest.TestCase):

    def _job(self, title=None, title_manual=None, year=None):
        return SimpleNamespace(title=title, title_manual=title_manual, year=year)

    def test_title_with_year(self):
        self.assertEqual(utils.fix_job_title(self._job(title="The Matrix", year="1999")),
                         "The Matrix (1999)")

    def test_title_without_year(self):
        self.assertEqual(utils.fix_job_title(self._job(title="The Matrix", year="0000")), "The Matrix")

    def test_manual_title_preferred(self):
        self.assertEqual(utils.fix_job_title(self._job(title="Auto", title_manual="Manual", year="")),
                         "Manual")

    def test_path_separators_stripped(self):
        self.assertNotIn("/", utils.fix_job_title(self._job(title="Face/Off", year="1997")))

    def test_traversal_neutralized(self):
        result = utils.fix_job_title(self._job(title="../../etc", year=None))
        self.assertNotIn("/", result)
        self.assertFalse(result.startswith("."))


class TestSaveDiscPoster(unittest.TestCase):

    @mock.patch.object(utils.os, "system")
    @mock.patch.object(utils.os.path, "isfile", side_effect=lambda p: p.endswith("J00___5L.MP2"))
    @mock.patch.object(utils.subprocess, "run")
    def test_poster_runs_list_form_no_shell(self, mock_run, mock_isfile, mock_system):
        # The (title-derived) output dir must reach ffmpeg as a single argv
        # element, never interpolated into a shell command.
        job = SimpleNamespace(disctype="dvd", devpath="/dev/sr0", mountpoint="/mnt/disc")
        with mock.patch.object(utils.cfg, "arm_config", {"RIP_POSTER": True}):
            utils.save_disc_poster('/out/evil"; rm -rf ~', job)
        # os.system (shell) must no longer be used for the poster/mount calls.
        mock_system.assert_not_called()
        # every subprocess call is argv-list form, no shell=True
        self.assertTrue(mock_run.call_args_list)
        for call in mock_run.call_args_list:
            self.assertIsInstance(call.args[0], list)
            self.assertNotEqual(call.kwargs.get("shell"), True)
        ffmpeg_calls = [c for c in mock_run.call_args_list if c.args[0][0] == "ffmpeg"]
        self.assertTrue(ffmpeg_calls)
        self.assertIn('/out/evil"; rm -rf ~/poster.png', ffmpeg_calls[0].args[0])

    @mock.patch.object(utils.os, "system")
    @mock.patch.object(utils.os.path, "isfile", return_value=False)
    @mock.patch.object(utils.subprocess, "run", side_effect=FileNotFoundError("mount"))
    def test_poster_missing_executable_is_tolerated(self, mock_run, mock_isfile, mock_system):
        # A missing mount/ffmpeg/umount must not abort the whole rip; the poster
        # step is best-effort, as the old os.system version was.
        job = SimpleNamespace(disctype="dvd", devpath="/dev/sr0", mountpoint="/mnt/disc")
        with mock.patch.object(utils.cfg, "arm_config", {"RIP_POSTER": True}):
            utils.save_disc_poster("/out", job)   # must not raise


if __name__ == '__main__':
    unittest.main()
