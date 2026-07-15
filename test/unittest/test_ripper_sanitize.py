import sys
import unittest

sys.path.insert(0, '/opt/arm')
from arm.ripper.sanitize import sanitize_label   # noqa: E402
from arm.ripper.utils import build_dd_command   # noqa: E402


class TestSanitizeLabel(unittest.TestCase):

    def test_benign_labels_unchanged(self):
        for label in ("Tom & Jerry", "The Matrix (1999)", "Depeche Mode - Violator", "data-disc"):
            self.assertEqual(sanitize_label(label), label)

    def test_path_separators_removed(self):
        self.assertNotIn("/", sanitize_label("a/b/c"))
        self.assertNotIn("\\", sanitize_label("a\\b\\c"))

    def test_traversal_neutralized(self):
        result = sanitize_label("../../etc/passwd")
        self.assertNotIn("/", result)
        self.assertFalse(result.startswith("."))
        self.assertEqual(result, "etcpasswd")

    def test_dotdot_becomes_empty(self):
        self.assertEqual(sanitize_label(".."), "")

    def test_control_chars_removed(self):
        self.assertEqual(sanitize_label("a\x00b\x1fc"), "abc")

    def test_shell_metachars_kept_but_harmless(self):
        # Not stripped (list-form dd makes them harmless literals), but no separators.
        result = sanitize_label('x"; rm -rf ~; echo "')
        self.assertNotIn("/", result)
        self.assertIn('"', result)

    def test_empty_and_none(self):
        self.assertEqual(sanitize_label(""), "")
        self.assertIsNone(sanitize_label(None))


class TestBuildDdCommand(unittest.TestCase):

    def test_returns_list_with_dd_and_operands(self):
        cmd = build_dd_command("/dev/sr0", "/home/arm/raw/x.part", "bs=1M conv=noerror")
        self.assertIsInstance(cmd, list)
        self.assertEqual(cmd[0], "dd")
        self.assertEqual(cmd[1], "if=/dev/sr0")
        self.assertEqual(cmd[2], "of=/home/arm/raw/x.part")
        self.assertEqual(cmd[3:], ["bs=1M", "conv=noerror"])

    def test_destination_is_single_element_no_shell_splitting(self):
        # A destination containing shell metacharacters must remain ONE argv element.
        dest = '/home/arm/raw/a b"; rm -rf ~.part'
        cmd = build_dd_command("/dev/sr0", dest, "")
        self.assertIn(f"of={dest}", cmd)
        self.assertEqual(len([c for c in cmd if c.startswith("of=")]), 1)

    def test_empty_params(self):
        cmd = build_dd_command("/dev/sr0", "/x.part", "")
        self.assertEqual(cmd, ["dd", "if=/dev/sr0", "of=/x.part"])


if __name__ == '__main__':
    unittest.main()
