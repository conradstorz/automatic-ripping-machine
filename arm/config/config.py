#!/usr/bin/python3
"""yaml config loader"""
import json
import logging
import os
import yaml

import arm.config.config_utils as config_utils


def write_arm_yaml(arm_config, arm_config_path, install_path):
    """
    Rewrite the user's arm.yaml with grouped comments, atomically.

    The full file content is built FIRST, written to a temp file, then
    os.replace()'d into place. A failure while reading comments.json or building
    the content therefore leaves the user's existing arm.yaml untouched, instead
    of truncating it to an empty file that would stop both the ripper and the UI
    from booting.
    """
    tmp_path = arm_config_path + ".tmp"
    try:
        with open(os.path.join(install_path, "arm/ui/comments.json"), "r") as comments_file:
            comments = json.load(comments_file)

        arm_cfg = comments["ARM_CFG_GROUPS"]["BEGIN"] + "\n\n"
        for key, value in dict(arm_config).items():
            # Add any grouping comments
            arm_cfg += config_utils.arm_yaml_check_groups(comments, key)
            # Check for comments for this key in comments.json, add them if they exist
            try:
                if comment := comments[str(key)]:
                    arm_cfg += f"\n{comment}\n"
            except KeyError:
                arm_cfg += "\n"
            # test if key value is an int
            value = str(value)  # just change the type to keep things as expected
            try:
                post_value = int(value)
                arm_cfg += f"{key}: {post_value}\n"
            except ValueError:
                # Test if value is Boolean
                arm_cfg += config_utils.arm_yaml_test_bool(key, value)

        # Content built successfully - now write atomically.
        with open(tmp_path, "w") as settings_file:
            settings_file.write(arm_cfg)
        os.replace(tmp_path, arm_config_path)
    except (OSError, KeyError, ValueError, json.JSONDecodeError) as error:
        logging.warning(f"Could not rewrite {arm_config_path}; leaving it unchanged. Error: {error}")
        try:
            if os.path.isfile(tmp_path):
                os.remove(tmp_path)
        except OSError:
            pass


arm_config: dict[str, str]
arm_config_path: str = os.environ.get("ARM_CONFIG_FILE", "/etc/arm/config/arm.yaml")

abcde_config: dict[str, str]
abcde_config_path: str

apprise_config: dict[str, str]
apprise_config_path: str


def _load_config(fp):
    with open(fp, "r") as yaml_file:
        config = yaml.safe_load(yaml_file)
    return config


def _load_abcde(fp):
    with open(fp, "r") as abcde_read_file:
        config = abcde_read_file.read()
    return config


# arm config, open and read yaml contents
# handle arm.yaml migration here
# Load user config
cur_cfg = _load_config(arm_config_path)
# Load template config
arm_config = _load_config(os.path.join(cur_cfg["INSTALLPATH"], "setup/arm.yaml"))

# Update the template config with the user's values
arm_config.update(cur_cfg)

# Rewrite the user's arm.yaml with grouped comments (atomic; leaves the file
# untouched if anything goes wrong so a bad comments.json can't empty it).
write_arm_yaml(arm_config, arm_config_path, cur_cfg["INSTALLPATH"])

# abcde config file, open and read contents
abcde_config_path = arm_config["ABCDE_CONFIG_FILE"]
abcde_config = _load_abcde(abcde_config_path)

# apprise config, open and read yaml contents
apprise_config_path = arm_config["APPRISE"] or "/etc/arm/config/apprise.yaml"
try:
    apprise_config = _load_config(apprise_config_path)
except OSError:
    apprise_config = {}
