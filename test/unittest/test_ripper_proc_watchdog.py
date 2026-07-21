"""Tests for the shared external-process watchdog (proc_watchdog).

Generalizes the makemkvcon inactivity watchdog to any external tool: kill a
process that shows no sign of life (no stdout line AND no progress-file update)
for `inactivity` seconds, so a wedged HandBrake/ffmpeg/abcde/dd can't hang a rip
forever, while a healthy long job that keeps writing progress is never killed.

Runs in-container.
"""
import os
import stat
import subprocess
import sys
import tempfile
import time
import unittest

sys.path.insert(0, '/opt/arm')
import psutil   # noqa: E402
from arm.ripper.proc_watchdog import (   # noqa: E402
    run_watched,
    kill_process_tree,
    heartbeat_idle,
    ProcessInactivityError,
)


def _fakes(marker):
    found = set()
    for p in psutil.process_iter():
        try:
            if marker in " ".join(p.cmdline()):
                found.add(p.pid)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return found


class TestHeartbeatIdle(unittest.TestCase):

    def test_stdout_recent(self):
        self.assertAlmostEqual(heartbeat_idle(1000 - 3, None, 1000), 3, delta=0.01)

    def test_fresh_progress_file_beats_stale_stdout(self):
        with tempfile.NamedTemporaryFile() as tmp:
            now = time.time()
            os.utime(tmp.name, (now, now))
            self.assertLess(heartbeat_idle(now - 100, tmp.name, now), 1)

    def test_missing_progress_file_falls_back_to_stdout(self):
        self.assertAlmostEqual(heartbeat_idle(1000 - 20, "/nope/x", 1000), 20, delta=0.01)


class TestKillProcessTree(unittest.TestCase):

    def test_kills_parent_and_children(self):
        proc = subprocess.Popen(["bash", "-c", "sleep 60 & sleep 60"])
        try:
            parent = psutil.Process(proc.pid)
            deadline = time.monotonic() + 3
            while not parent.children() and time.monotonic() < deadline:
                time.sleep(0.05)
            children = parent.children(recursive=True)
            self.assertTrue(children)
            kill_process_tree(proc.pid)
            _, alive = psutil.wait_procs([parent] + children, timeout=6)
            self.assertEqual(alive, [])
        finally:
            try:
                proc.kill()
            except Exception:
                pass
            proc.wait()

    def test_nonexistent_pid_is_noop(self):
        kill_process_tree(2_000_000_000)


class TestRunWatched(unittest.TestCase):

    def _script(self, body):
        d = tempfile.mkdtemp()
        path = os.path.join(d, "fake")
        with open(path, "w") as f:
            f.write("#!/bin/bash\n" + body)
        os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
        return path

    def test_chatty_process_yields_lines_and_returns_output(self):
        script = self._script("echo alpha\necho beta\n")
        lines = []
        out = run_watched([script], inactivity=5, on_line=lines.append)
        self.assertEqual(lines, ["alpha", "beta"])
        self.assertIn("alpha", out)
        self.assertIn("beta", out)

    def test_hung_process_is_killed_and_raises(self):
        script = self._script("sleep 300\n")
        marker = script
        before = _fakes(marker)
        start = time.monotonic()
        with self.assertRaises(ProcessInactivityError):
            run_watched([script], inactivity=1)
        self.assertLess(time.monotonic() - start, 10)
        time.sleep(0.5)
        self.assertEqual(_fakes(marker) - before, set(), "watchdog must reap the hung child")

    def test_fresh_progress_file_prevents_false_kill(self):
        d = tempfile.mkdtemp()
        progress = os.path.join(d, "progress.log")
        open(progress, "w").close()
        # Silent on stdout but touches the progress file every 0.2s for ~3s.
        script = self._script(
            f'for i in $(seq 1 15); do : > "{progress}"; sleep 0.2; done\nexit 0\n')
        start = time.monotonic()
        out = run_watched([script], inactivity=1, progress_file=progress)
        self.assertEqual(out, "")
        self.assertGreater(time.monotonic() - start, 1.5)

    def test_nonzero_exit_raises_calledprocesserror(self):
        script = self._script("echo boom\nexit 3\n")
        with self.assertRaises(subprocess.CalledProcessError) as ctx:
            run_watched([script], inactivity=5)
        self.assertEqual(ctx.exception.returncode, 3)
        self.assertIn("boom", ctx.exception.output)

    def test_disabled_watchdog_does_not_kill_silent_process(self):
        script = self._script("sleep 2\nexit 0\n")
        out = run_watched([script], inactivity=0)   # disabled
        self.assertEqual(out, "")


if __name__ == '__main__':
    unittest.main()
