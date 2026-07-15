"""Tests for the log-filename label sink in arm.ripper.logger.

The job label is untrusted disc metadata and is kept raw everywhere except
where it becomes a filesystem path. setup_job_log builds a .log filename from
it, so it must sanitize the label here (the point of use), not rely on the
source. _safe_log_label isolates that choice for testing.
"""
import sys
import unittest
from types import SimpleNamespace

sys.path.insert(0, '/opt/arm')
from arm.ripper.logger import _safe_log_label   # noqa: E402


def make_job(label, disctype="dvd", audio_cd_label="Artist - Album"):
    return SimpleNamespace(
        label=label,
        disctype=disctype,
        identify_audio_cd=lambda: audio_cd_label,
    )


class TestSafeLogLabel(unittest.TestCase):

    def test_normal_label_unchanged(self):
        self.assertEqual(_safe_log_label(make_job("The Matrix (1999)")), "The Matrix (1999)")

    def test_path_separators_stripped(self):
        result = _safe_log_label(make_job("a/b\\c"))
        self.assertNotIn("/", result)
        self.assertNotIn("\\", result)

    def test_traversal_neutralized(self):
        result = _safe_log_label(make_job("../../etc/passwd"))
        self.assertNotIn("/", result)
        self.assertFalse(result.startswith("."))

    def test_garbage_label_falls_back_to_no_label(self):
        # A label made only of stripped characters sanitizes to "" -> must not
        # produce a "_stage.log" file with an empty prefix.
        self.assertEqual(_safe_log_label(make_job("///")), "no_label")

    def test_empty_label_non_music(self):
        self.assertEqual(_safe_log_label(make_job("", disctype="data")), "no_label")

    def test_empty_label_music_uses_audio_cd(self):
        job = make_job(None, disctype="music", audio_cd_label="Portishead - Dummy")
        self.assertEqual(_safe_log_label(job), "Portishead - Dummy")

    def test_empty_label_music_is_sanitized(self):
        # An untrusted MusicBrainz title with a separator (e.g. "AC/DC") must
        # not produce a path-breaking log filename.
        job = make_job(None, disctype="music", audio_cd_label="AC/DC")
        self.assertNotIn("/", _safe_log_label(job))


if __name__ == '__main__':
    unittest.main()
