import sys
import unittest

sys.path.insert(0, '/opt/arm')
from arm.ripper.sanitize import sanitize_label, safe_path_component   # noqa: E402


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


class TestSafePathComponent(unittest.TestCase):

    def test_normal_title_unchanged(self):
        self.assertEqual(safe_path_component("The Matrix (1999)"), "The Matrix (1999)")

    def test_path_separators_stripped(self):
        self.assertNotIn("/", safe_path_component("Face/Off"))

    def test_traversal_neutralized(self):
        result = safe_path_component("../../etc/passwd")
        self.assertNotIn("/", result)
        self.assertFalse(result.startswith("."))

    def test_empty_uses_fallback(self):
        self.assertEqual(safe_path_component(""), "unknown")
        self.assertEqual(safe_path_component(None), "unknown")

    def test_garbage_uses_fallback(self):
        self.assertEqual(safe_path_component("///"), "unknown")

    def test_custom_fallback(self):
        self.assertEqual(safe_path_component("", "movie"), "movie")


if __name__ == '__main__':
    unittest.main()
