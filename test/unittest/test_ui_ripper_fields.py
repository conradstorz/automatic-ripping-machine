"""Tests for the Ripper Settings field model.

build_field_model turns the flat arm_config dict into an ordered, grouped set
of typed fields for the redesigned settings page. The critical guarantees are
(1) every config key is rendered exactly once -- so save_settings, which
rebuilds arm.yaml from the POSTed keys, can never drop a setting -- and (2)
booleans serialize to the yaml-literal 'true'/'false' the save path expects.
"""
import sys
import unittest

sys.path.insert(0, '/opt/arm')
from arm.ui.settings.ripper_fields import build_field_model, humanize   # noqa: E402


class TestBuildFieldModel(unittest.TestCase):

    def _find(self, model, key):
        for group in model:
            for field in group["fields"]:
                if field["key"] == key:
                    return field
        raise AssertionError(f"{key} not in model")

    def test_every_key_appears_exactly_once(self):
        cfg = {"ARM_NAME": "x", "PREVENT_99": True, "SOME_NEW_OPTION": "y", "EMBY_API_KEY": "z"}
        model = build_field_model(cfg, {})
        keys = [f["key"] for g in model for f in g["fields"]]
        self.assertCountEqual(keys, list(cfg.keys()))

    def test_curated_key_gets_human_label_and_type(self):
        field = self._find(build_field_model({"PREVENT_99": True}, {}), "PREVENT_99")
        self.assertNotEqual(field["label"], "PREVENT_99")
        self.assertEqual(field["type"], "bool")

    def test_unmapped_key_falls_back_to_advanced_text(self):
        field = self._find(build_field_model({"SOME_NEW_OPTION": "hi"}, {}), "SOME_NEW_OPTION")
        self.assertEqual(field["group_id"], "advanced")
        self.assertEqual(field["type"], "text")
        self.assertEqual(field["label"], "Some New Option")

    def test_unmapped_boolean_infers_toggle(self):
        field = self._find(build_field_model({"SOME_FLAG": False}, {}), "SOME_FLAG")
        self.assertEqual(field["type"], "bool")

    def test_enum_carries_options(self):
        field = self._find(build_field_model({"LOGLEVEL": "INFO"}, {}), "LOGLEVEL")
        self.assertEqual(field["type"], "enum")
        self.assertIn("DEBUG", field["options"])

    def test_bool_value_serializes_to_yaml_literal(self):
        model = build_field_model({"PREVENT_99": True, "SKIP_TRANSCODE": False}, {})
        self.assertEqual(self._find(model, "PREVENT_99")["value"], "true")
        self.assertEqual(self._find(model, "SKIP_TRANSCODE")["value"], "false")

    def test_description_pulled_and_cleaned_from_comments(self):
        model = build_field_model({"ARM_NAME": ""}, {"ARM_NAME": "# A friendly name\n# shown in notifications"})
        desc = self._find(model, "ARM_NAME")["desc"]
        self.assertIn("A friendly name", desc)
        self.assertNotIn("#", desc)

    def test_empty_groups_are_omitted(self):
        model = build_field_model({"ARM_NAME": "x"}, {})
        ids = [g["id"] for g in model]
        self.assertIn("general", ids)
        self.assertNotIn("logging", ids)


class TestHumanize(unittest.TestCase):

    def test_acronyms_preserved(self):
        self.assertEqual(humanize("EMBY_API_KEY"), "Emby API Key")
        self.assertEqual(humanize("FFMPEG_CLI"), "FFmpeg CLI")
        self.assertEqual(humanize("UI_BASE_URL"), "UI Base URL")


if __name__ == '__main__':
    unittest.main()
