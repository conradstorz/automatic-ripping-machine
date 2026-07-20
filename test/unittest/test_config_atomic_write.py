"""Tests for the atomic arm.yaml rewrite.

The old code opened arm.yaml in "w" mode (truncating it) BEFORE reading
comments.json and building the replacement, catching only OSError. A
JSONDecodeError/KeyError there left arm.yaml empty -> neither the ripper nor
the UI could boot. write_arm_yaml() now builds the content first, writes a temp
file, and os.replace()s it, leaving the original untouched on any failure.

Runs in-container (imports arm.config.config, which reads /opt/arm on import).
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, '/opt/arm')
import yaml                             # noqa: E402
import arm.config.config as cfg_module  # noqa: E402


class TestWriteArmYaml(unittest.TestCase):

    def test_preserves_original_when_comments_json_is_broken(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "arm", "ui"))
            with open(os.path.join(d, "arm", "ui", "comments.json"), "w") as broken:
                broken.write("{ this is not valid json ")
            arm_yaml = os.path.join(d, "arm.yaml")
            original = "INSTALLPATH: /opt/arm\nARM_NAME: keepme\n"
            with open(arm_yaml, "w") as f:
                f.write(original)

            # Must not raise, and must NOT truncate the user's config.
            cfg_module.write_arm_yaml({"INSTALLPATH": "/opt/arm", "ARM_NAME": "keepme"},
                                      arm_yaml, d)

            with open(arm_yaml) as f:
                self.assertEqual(f.read(), original)

    def test_rewrites_and_reparses_on_valid_inputs(self):
        # /opt/arm has the real comments.json.
        with tempfile.TemporaryDirectory() as d:
            arm_yaml = os.path.join(d, "arm.yaml")
            with open(arm_yaml, "w") as f:
                f.write("stale\n")

            cfg_module.write_arm_yaml({"ARM_NAME": "x", "MINLENGTH": "600"}, arm_yaml, "/opt/arm")

            with open(arm_yaml) as f:
                content = f.read()
            self.assertIn("ARM_NAME:", content)
            self.assertNotEqual(content, "stale\n")   # was actually rewritten
            parsed = yaml.safe_load(content)          # must be valid YAML
            self.assertEqual(parsed["ARM_NAME"], "x")
            self.assertEqual(parsed["MINLENGTH"], 600)

    def test_no_tmp_file_left_behind(self):
        with tempfile.TemporaryDirectory() as d:
            arm_yaml = os.path.join(d, "arm.yaml")
            with open(arm_yaml, "w") as f:
                f.write("stale\n")
            cfg_module.write_arm_yaml({"ARM_NAME": "x"}, arm_yaml, "/opt/arm")
            self.assertFalse(os.path.exists(arm_yaml + ".tmp"))


if __name__ == '__main__':
    unittest.main()
