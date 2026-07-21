"""Tests for arm_subprocess wall-clock timeout on short helper commands."""
import subprocess
import sys
import unittest

sys.path.insert(0, '/opt/arm')
from arm.ripper.ProcessHandler import arm_subprocess, _timeout_secs   # noqa: E402


class TestArmSubprocessTimeout(unittest.TestCase):

    def test_timeout_aborts_and_returns_none(self):
        # sleep outlives the 1s timeout -> killed, handled, returns None.
        self.assertIsNone(arm_subprocess(["sleep", "10"], timeout=1))

    def test_timeout_with_check_reraises(self):
        with self.assertRaises(subprocess.TimeoutExpired):
            arm_subprocess(["sleep", "10"], timeout=1, check=True)

    def test_normal_command_still_returns_output(self):
        out = arm_subprocess(["echo", "hello"], timeout=10)
        self.assertIn("hello", out)


class TestTimeoutSecs(unittest.TestCase):

    def test_explicit_positive(self):
        self.assertEqual(_timeout_secs(30), 30)

    def test_explicit_zero_disables(self):
        self.assertIsNone(_timeout_secs(0))

    def test_none_uses_config_default(self):
        # Config default is 60 unless overridden; must be a positive int or None.
        val = _timeout_secs(None)
        self.assertTrue(val is None or (isinstance(val, int) and val > 0))


if __name__ == '__main__':
    unittest.main()
