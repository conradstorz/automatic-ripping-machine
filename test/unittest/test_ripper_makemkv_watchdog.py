"""Tests for the makemkvcon inactivity watchdog and process-tree kill.

Guards the fix for the production hang where `makemkvcon info` wedged at 100%
CPU emitting zero output and blocked the ripper for 17-41 hours.

Key subtlety (regression C1): during a *rip* MakeMKV writes its progress
heartbeat to the `--progress` file, not stdout, so the watchdog must treat a
fresh progress file as a sign of life -- otherwise a healthy long rip whose
stdout is quiet would be falsely killed. `_heartbeat_idle` implements that
"freshest of {stdout, progress file}" rule.

Runs in-container (imports arm.ripper.makemkv).
"""
import os
import stat
import subprocess
import sys
import tempfile
import time
import unittest

sys.path.insert(0, '/opt/arm')
import psutil                          # noqa: E402
import arm.ripper.makemkv as makemkv   # noqa: E402
from arm.ripper.makemkv import (       # noqa: E402
    kill_process_tree,
    run,
    OutputType,
    MakeMkvRuntimeError,
    _heartbeat_idle,
)


def _fakes(proc_marker):
    """pids of live processes whose cmdline contains proc_marker."""
    found = set()
    for p in psutil.process_iter():
        try:
            if proc_marker in " ".join(p.cmdline()):
                found.add(p.pid)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return found


class TestHeartbeatIdle(unittest.TestCase):

    def test_stdout_recent_is_low_idle(self):
        now = 1000.0
        self.assertAlmostEqual(_heartbeat_idle(now - 2, None, now), 2, delta=0.01)

    def test_stdout_stale_no_progress_file(self):
        now = 1000.0
        self.assertAlmostEqual(_heartbeat_idle(now - 120, None, now), 120, delta=0.01)

    def test_fresh_progress_file_beats_stale_stdout(self):
        with tempfile.NamedTemporaryFile() as tmp:
            now = time.time()
            os.utime(tmp.name, (now, now))          # progress file just updated
            # stdout silent for 120s, but the file is fresh -> low idle
            self.assertLess(_heartbeat_idle(now - 120, tmp.name, now), 1)

    def test_stale_progress_file_and_stale_stdout(self):
        with tempfile.NamedTemporaryFile() as tmp:
            now = time.time()
            os.utime(tmp.name, (now - 120, now - 120))   # file also stale
            self.assertGreater(_heartbeat_idle(now - 120, tmp.name, now), 100)

    def test_missing_progress_file_falls_back_to_stdout(self):
        now = 1000.0
        idle = _heartbeat_idle(now - 30, "/nonexistent/progress.log", now)
        self.assertAlmostEqual(idle, 30, delta=0.01)


class TestKillProcessTree(unittest.TestCase):

    def test_kills_parent_and_children(self):
        proc = subprocess.Popen(["bash", "-c", "sleep 60 & sleep 60"])
        try:
            parent = psutil.Process(proc.pid)
            deadline = time.monotonic() + 3
            while not parent.children() and time.monotonic() < deadline:
                time.sleep(0.05)
            children = parent.children(recursive=True)
            self.assertTrue(children, "expected a child sleep process")
            kill_process_tree(proc.pid)
            gone, alive = psutil.wait_procs([parent] + children, timeout=6)
            self.assertEqual(alive, [], "no process in the tree should survive")
        finally:
            try:
                proc.kill()
            except Exception:
                pass
            proc.wait()

    def test_nonexistent_pid_is_noop(self):
        kill_process_tree(2_000_000_000)


class _FakeMakemkvconBase(unittest.TestCase):
    """Point shutil.which('makemkvcon') at a fake script for the duration."""
    script = "#!/bin/bash\nsleep 300\n"

    def setUp(self):
        self._orig_which = makemkv.shutil.which
        self._tmp = tempfile.mkdtemp()
        self._fake = os.path.join(self._tmp, "makemkvcon")
        with open(self._fake, "w") as fake:
            fake.write(self.script)
        os.chmod(self._fake, os.stat(self._fake).st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
        makemkv.shutil.which = lambda name: self._fake if name == "makemkvcon" else self._orig_which(name)

    def tearDown(self):
        makemkv.shutil.which = self._orig_which


class TestRunKillsHungInfoScan(_FakeMakemkvconBase):
    """A silent (hung) makemkvcon info scan is aborted and reaped."""
    script = "#!/bin/bash\nsleep 300\n"

    def test_hung_child_raises_and_leaves_no_survivor(self):
        before = _fakes(self._fake)
        start = time.monotonic()
        with self.assertRaises(MakeMkvRuntimeError):
            list(run(["info", "--cache=1", "disc:0"], OutputType.TINFO, inactivity=1))
        self.assertLess(time.monotonic() - start, 10)
        time.sleep(0.5)
        self.assertEqual(_fakes(self._fake) - before, set(), "run() must reap the hung child")


class TestRunDisabled(_FakeMakemkvconBase):
    """inactivity <= 0 disables the watchdog (no false kill)."""
    script = "#!/bin/bash\nsleep 2\nexit 0\n"

    def test_disabled_does_not_trip_on_silence(self):
        # With the watchdog on (1s) this silent process would be killed; disabled
        # (0), run() must wait for its clean exit and not raise.
        result = list(run(["info", "--cache=1", "disc:0"], OutputType.TINFO, inactivity=0))
        self.assertEqual(result, [])


class TestRunHealthyRipNotKilled(_FakeMakemkvconBase):
    """C1 regression: a rip silent on stdout but updating its --progress file
    must NOT be killed. The fake touches the file passed via --progress."""
    script = (
        "#!/bin/bash\n"
        "P=\"\"\n"
        "for a in \"$@\"; do case \"$a\" in --progress=*) P=\"${a#--progress=}\";; esac; done\n"
        "for i in $(seq 1 15); do [ -n \"$P\" ] && : > \"$P\"; sleep 0.2; done\n"
        "exit 0\n"
    )

    def test_fresh_progress_file_prevents_false_kill(self):
        progress = os.path.join(self._tmp, "progress.log")
        open(progress, "w").close()   # pre-create so getmtime always works
        start = time.monotonic()
        # inactivity=1: without the progress-file heartbeat, stdout silence would
        # trip the kill at ~1s. The fake keeps the file fresh for ~3s.
        result = list(run(["mkv", f"--progress={progress}", "dev:/dev/sr0", "all"],
                          OutputType.MSG, inactivity=1, progress_file=progress))
        self.assertEqual(result, [])
        self.assertGreater(time.monotonic() - start, 1.5,
                           "should have run past the 1s window without being killed")


if __name__ == '__main__':
    unittest.main()
