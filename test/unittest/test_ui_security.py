import os
import sys
import unittest
import tempfile

sys.path.insert(0, '/opt/arm')
from arm.ui.security import load_or_create_secret_key, generate_debug_pin   # noqa: E402


class TestUiSecurity(unittest.TestCase):

    def test_generates_key_when_absent(self):
        """A missing key file is created and its contents are returned."""
        with tempfile.TemporaryDirectory() as d:
            key = load_or_create_secret_key(d)
            self.assertTrue(key)
            key_path = os.path.join(d, "secret_key")
            self.assertTrue(os.path.isfile(key_path))
            with open(key_path) as f:
                self.assertEqual(f.read().strip(), key)

    def test_reuses_existing_key(self):
        """A second call returns the identical persisted key."""
        with tempfile.TemporaryDirectory() as d:
            first = load_or_create_secret_key(d)
            second = load_or_create_secret_key(d)
            self.assertEqual(first, second)

    def test_empty_file_is_regenerated(self):
        """An empty/whitespace key file is treated as absent and regenerated."""
        with tempfile.TemporaryDirectory() as d:
            key_path = os.path.join(d, "secret_key")
            with open(key_path, "w") as f:
                f.write("   \n")
            key = load_or_create_secret_key(d)
            self.assertTrue(key)
            with open(key_path) as f:
                self.assertEqual(f.read().strip(), key)

    def test_unwritable_dir_falls_back(self):
        """A dir that cannot be written yields a key without raising or persisting."""
        with tempfile.NamedTemporaryFile() as parent_file:
            # Parent is a regular file -> opening a child path raises OSError.
            bogus_dir = os.path.join(parent_file.name, "sub")
            key = load_or_create_secret_key(bogus_dir)
            self.assertTrue(key)
            self.assertFalse(os.path.exists(os.path.join(bogus_dir, "secret_key")))

    def test_debug_pin_is_random_nonempty(self):
        """generate_debug_pin returns a non-empty string that isn't the old constant."""
        pin = generate_debug_pin()
        self.assertTrue(pin)
        self.assertNotEqual(pin, "12345")


if __name__ == '__main__':
    unittest.main()
