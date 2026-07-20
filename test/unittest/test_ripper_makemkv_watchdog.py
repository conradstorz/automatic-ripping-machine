"""Tests for the makemkvcon inactivity watchdog and process-tree kill.

These guard the fix for the production hang where `makemkvcon info` wedged at
100% CPU emitting zero output and blocked the ripper for 17-41 hours because
run() read the child with a blocking `for line in proc.stdout:` and no timeout.

iter_lines_with_timeout() yields lines but raises MakeMkvInactivityError if the
stream produces nothing for `timeout` seconds. kill_process_tree() terminates a
process and its descendants so a wedged makemkvcon (and any children) is reaped.

Runs in-container (imports arm.ripper.makemkv).
"""
import subprocess
import sys
import time
import unittest

sys.path.insert(0, '/opt/arm')
import os                     # noqa: E402
import stat                   # noqa: E402
import tempfile               # noqa: E402
import psutil                 # noqa: E402
import arm.ripper.makemkv as makemkv   # noqa: E402
import arm.config.config as cfg        # noqa: E402
from arm.ripper.makemkv import (   # noqa: E402
    iter_lines_with_timeout,
    kill_process_tree,
    run,
    OutputType,
    MakeMkvInactivityError,
    MakeMkvRuntimeError,
)


class TestIterLinesWithTimeout(unittest.TestCase):

    def test_silent_stream_raises_inactivity(self):
        """A child that emits nothing trips the inactivity timeout promptly."""
        proc = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            stdout=subprocess.PIPE, text=True)
        try:
            start = time.monotonic()
            with self.assertRaises(MakeMkvInactivityError):
                list(iter_lines_with_timeout(proc.stdout, 1))
            elapsed = time.monotonic() - start
            self.assertLess(elapsed, 5, "should raise near the 1s timeout, not block")
        finally:
            proc.kill()
            proc.wait()

    def test_chatty_stream_yields_all_lines(self):
        """A child that emits lines then exits yields them and finishes clean."""
        proc = subprocess.Popen(
            [sys.executable, "-c", "print('alpha'); print('beta')"],
            stdout=subprocess.PIPE, text=True)
        try:
            lines = [ln.rstrip("\n") for ln in iter_lines_with_timeout(proc.stdout, 5)]
            self.assertEqual(lines, ["alpha", "beta"])
        finally:
            proc.wait()

    def test_slow_but_progressing_stream_not_tripped(self):
        """Lines arriving inside the window keep resetting the timer."""
        proc = subprocess.Popen(
            [sys.executable, "-c",
             "import time,sys\n"
             "for i in range(3):\n"
             "    print(i); sys.stdout.flush(); time.sleep(0.5)"],
            stdout=subprocess.PIPE, text=True)
        try:
            lines = [ln.rstrip("\n") for ln in iter_lines_with_timeout(proc.stdout, 2)]
            self.assertEqual(lines, ["0", "1", "2"])
        finally:
            proc.wait()


class TestKillProcessTree(unittest.TestCase):

    def test_kills_parent_and_children(self):
        """kill_process_tree reaps the parent and any descendant processes."""
        # bash parent that spawns a child sleep, then waits.
        proc = subprocess.Popen(["bash", "-c", "sleep 60 & sleep 60"])
        try:
            parent = psutil.Process(proc.pid)
            # give the child a moment to spawn
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
        """Killing a pid that does not exist must not raise."""
        # A pid unlikely to exist.
        kill_process_tree(2_000_000_000)


class TestRunKillsHungMakemkvcon(unittest.TestCase):
    """End-to-end: run() must abort and reap a silent (hung) makemkvcon."""

    def setUp(self):
        self._orig_which = makemkv.shutil.which
        self._orig_inactivity = cfg.arm_config.get('MAKEMKV_MAX_INACTIVITY_SECS')
        self._tmp = tempfile.mkdtemp()
        # A fake "makemkvcon" that ignores its args and hangs silently, like the
        # wedged v1.18.4 info scan seen in production (zero output).
        self._fake = os.path.join(self._tmp, "makemkvcon")
        with open(self._fake, "w") as fake:
            fake.write("#!/bin/bash\nsleep 300\n")
        os.chmod(self._fake, os.stat(self._fake).st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
        cfg.arm_config['MAKEMKV_MAX_INACTIVITY_SECS'] = 1
        makemkv.shutil.which = lambda name: self._fake if name == "makemkvcon" else self._orig_which(name)

    def tearDown(self):
        makemkv.shutil.which = self._orig_which
        if self._orig_inactivity is None:
            cfg.arm_config.pop('MAKEMKV_MAX_INACTIVITY_SECS', None)
        else:
            cfg.arm_config['MAKEMKV_MAX_INACTIVITY_SECS'] = self._orig_inactivity

    def test_hung_child_raises_and_leaves_no_survivor(self):
        before = {p.pid for p in psutil.process_iter() if _is_fake(p, self._fake)}
        start = time.monotonic()
        with self.assertRaises(MakeMkvRuntimeError):
            list(run(["info", "--cache=1", "disc:0"], OutputType.TINFO))
        self.assertLess(time.monotonic() - start, 10, "should abort near the 1s timeout")
        # No fake makemkvcon spawned by this test may survive.
        time.sleep(0.5)
        after = {p.pid for p in psutil.process_iter() if _is_fake(p, self._fake)}
        self.assertEqual(after - before, set(), "run() must reap the hung child")


def _is_fake(proc, fake_path):
    try:
        return fake_path in " ".join(proc.cmdline())
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return False


if __name__ == '__main__':
    unittest.main()
