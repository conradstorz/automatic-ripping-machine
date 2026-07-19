#!/usr/bin/env bash

# This script is inspired by the script posted on the forums.
# Given that it hasn't been taken down I'm going to assume they
# don't have a problem with users programmatically scraping the
# beta key.
# Link: https://forum.makemkv.com/forum/viewtopic.php?p=119221#p119221

set -e

EXIT_CODE_PARSE_ERROR=20
EXIT_CODE_INTERNAL_ERROR=30
EXIT_CODE_URL_ERROR=40
EXIT_CODE_INVALID_MAKEMKV_SERIAL=50

MAKEMKV_SERIAL_URL="https://forum.makemkv.com/forum/viewtopic.php?f=5&t=1053"
MAKEMKV_SERIAL="$1"

# Use beta key if serial is not passed
if [ -z "$MAKEMKV_SERIAL" ]; then
    # The forum is briefly unreachable at times and rate-limits bursts of
    # requests (e.g. several drives ripping at once), which would otherwise fail
    # an otherwise-good rip. Bound each attempt with a timeout and retry a few
    # times with linear backoff before giving up.
    MAKEMKV_KEY_MAX_TRIES="${MAKEMKV_KEY_MAX_TRIES:-4}"
    attempt=1
    while true; do
        if MAKEMKV_SERIAL=$(curl -fsSL --connect-timeout 15 --max-time 45 \
                "$MAKEMKV_SERIAL_URL" | grep -oP 'T-[\w\d@]{66}'); then
            break
        fi
        if [ "$attempt" -ge "$MAKEMKV_KEY_MAX_TRIES" ]; then
            echo "The beta key cannot be found at: $MAKEMKV_SERIAL_URL (after $attempt attempts)"
            exit $EXIT_CODE_URL_ERROR
        fi
        backoff=$((attempt * 5))
        echo "Attempt $attempt to fetch the beta key failed; retrying in ${backoff}s..."
        sleep "$backoff"
        attempt=$((attempt + 1))
    done
    echo "MakeMKV beta key for this month: $MAKEMKV_SERIAL"
fi

# Check that the key follows a certain rule but not too strict.
# - "T-xyz" for beta keys
# - "M-xyz" for perma keys
if ! [[ $MAKEMKV_SERIAL =~ ^[A-Z]-.+$ ]]; then
	echo "Value for serial ($MAKEMKV_SERIAL) is invalid. Not adding it"
	exit $EXIT_CODE_INVALID_MAKEMKV_SERIAL
fi

# create .MakeMKV dir if it doesn't already exist
MAKEMKV_DIR="/home/arm/.MakeMKV"
if [ ! -d "$MAKEMKV_DIR" ]; then
    mkdir -p "$MAKEMKV_DIR"
    chown arm:arm "$MAKEMKV_DIR"
fi
SETTINGS_FILE="$MAKEMKV_DIR/settings.conf"

# If the file doesn't exist OR grep doesn't find key string in settings, append
# the key to the file. If the file was found, look for the matching section and
# replace the key. We strictly need a valid entry to replace it. Otherwise the
# script adds a valid entry to the file which may lead to double-defined
# values. This script does not delete invalid entries which is up to the user
# to do.
if [[ ! -f "$SETTINGS_FILE" ]] || ! grep -q 'app_Key = ".*"' "$SETTINGS_FILE"; then
    echo "Either $SETTINGS_FILE doesn't exist, or app_Key is not inside it"
	if (( $(grep -c "^app_Key" "$SETTINGS_FILE") > 0 )); then
		echo "Parse Error of settings file: $SETTINGS_FILE"
		exit $EXIT_CODE_PARSE_ERROR
	fi
	echo "app_Key = \"$MAKEMKV_SERIAL\"" >> "$SETTINGS_FILE"
else
    echo "$SETTINGS_FILE exists, updating value of app_Key"
	sed -i "s|app_Key = \".*\"|app_Key = \"$MAKEMKV_SERIAL\"|" "$SETTINGS_FILE"
fi

# check that the key got written
if (( $(grep -c 'app_Key = ".*"' /home/arm/.MakeMKV/settings.conf) != 1 )); then
	echo "Settings file is corrupt after adding the key: $SETTINGS_FILE"
	exit $EXIT_CODE_INTERNAL_ERROR
fi

chown arm:arm "$SETTINGS_FILE"
