"""Tests for move_files_main failure handling.

Previously a failed shutil.move was only logged; the caller returned normally
and post-processing then deleted the raw files (arm_ripper deletes raw AFTER
the move) -> the ripped title was permanently lost. move_files_main now raises
RipperException on a failed/missing move so the job fails and raw is preserved.

Runs in-container (imports arm.ripper.utils).
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, '/opt/arm')
import arm.ripper.utils as utils   # noqa: E402


class TestMoveFilesMain(unittest.TestCase):

    def test_successful_move(self):
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "src.mkv")
            with open(src, "w") as f:
                f.write("data")
            dst = os.path.join(d, "dst.mkv")
            utils.move_files_main(src, dst, d)
            self.assertTrue(os.path.isfile(dst))
            self.assertFalse(os.path.isfile(src))

    def test_move_failure_raises(self):
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "does_not_exist.mkv")  # nothing to move
            dst = os.path.join(d, "dst.mkv")
            with self.assertRaises(utils.RipperException):
                utils.move_files_main(src, dst, d)

    def test_existing_destination_is_left_untouched(self):
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "src.mkv")
            with open(src, "w") as f:
                f.write("new")
            dst = os.path.join(d, "dst.mkv")
            with open(dst, "w") as f:
                f.write("existing")
            utils.move_files_main(src, dst, d)   # dst exists -> skip, no raise
            with open(dst) as f:
                self.assertEqual(f.read(), "existing")
            self.assertTrue(os.path.isfile(src))  # source untouched


if __name__ == '__main__':
    unittest.main()
