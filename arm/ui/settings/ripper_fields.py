"""Field metadata for the Ripper Settings page.

The saved arm.yaml is rebuilt from exactly the keys POSTed by the settings
form (see ``ui.utils.build_arm_cfg``), so the redesigned page must render a
field for *every* key in ``arm_config`` or that setting would be dropped on
save. ``build_field_model`` guarantees that: curated keys get a human label,
control type and group; any unmapped key falls back to a text field in the
"Advanced" group with an auto-derived label. Nothing is ever omitted.
"""
from collections import OrderedDict

# Ordered groups shown on the page. "advanced" is the catch-all and comes last.
GROUPS = [
    ("general", "General", "Identity & display"),
    ("ripping", "Identification & ripping", "How discs are read"),
    ("transcode", "Transcoding", "HandBrake, MakeMKV & FFmpeg"),
    ("metadata", "Metadata", "Title lookup & API keys"),
    ("dirs", "Directories", "Where files live"),
    ("web", "Web & security", "UI access"),
    ("perms", "File permissions", "Ownership & mode"),
    ("logging", "Logging", "Diagnostics"),
    ("advanced", "Advanced", "Less-common options"),
]

# Curated metadata: key -> {label, group, type, options?, unit?, tag?}
# type is one of: bool, enum, number, path, text.
FIELDS = {
    # General
    "ARM_NAME": {"label": "Machine name", "group": "general", "type": "text"},
    "ARM_CHILDREN": {"label": "Child servers", "group": "general", "type": "text"},
    "DATE_FORMAT": {"label": "Date format", "group": "general", "type": "text"},

    # Identification & ripping
    "PREVENT_99": {"label": "Prevent Track-99 discs", "group": "ripping", "type": "bool",
                   "tag": {"c": "warn", "t": "can hang MakeMKV"}},
    "ARM_CHECK_UDF": {"label": "Check UDF disc type", "group": "ripping", "type": "bool"},
    "GET_VIDEO_TITLE": {"label": "Auto-detect video title", "group": "ripping", "type": "bool"},
    "VIDEOTYPE": {"label": "Video type", "group": "ripping", "type": "enum",
                  "options": ["auto", "series", "movie"]},
    "RIPMETHOD": {"label": "Blu-ray rip method", "group": "ripping", "type": "enum",
                  "options": ["mkv", "backup", "backup_dvd"]},
    "MINLENGTH": {"label": "Minimum title length", "group": "ripping", "type": "number", "unit": "sec"},
    "MAXLENGTH": {"label": "Maximum title length", "group": "ripping", "type": "number", "unit": "sec"},
    "MANUAL_WAIT": {"label": "Pause for manual ID", "group": "ripping", "type": "bool"},
    "MANUAL_WAIT_TIME": {"label": "Manual ID wait", "group": "ripping", "type": "number", "unit": "sec"},
    "ALLOW_DUPLICATES": {"label": "Allow duplicate rips", "group": "ripping", "type": "bool"},
    "SKIP_TRANSCODE": {"label": "Skip transcoding", "group": "ripping", "type": "bool"},
    "MAINFEATURE": {"label": "Main feature only", "group": "ripping", "type": "bool"},
    "RIP_POSTER": {"label": "Rip DVD poster", "group": "ripping", "type": "bool"},
    "AUTO_EJECT": {"label": "Auto-eject when done", "group": "ripping", "type": "bool"},
    "DATA_RIP_PARAMETERS": {"label": "Data rip parameters (dd)", "group": "ripping", "type": "text"},
    "ABCDE_CONFIG_FILE": {"label": "abcde config file", "group": "ripping", "type": "path"},

    # Transcoding
    "USE_FFMPEG": {"label": "Use FFmpeg instead of HandBrake", "group": "transcode", "type": "bool"},
    "DEST_EXT": {"label": "Output format", "group": "transcode", "type": "enum", "options": ["mkv", "mp4"]},
    "HB_PRESET_DVD": {"label": "HandBrake preset · DVD", "group": "transcode", "type": "text"},
    "HB_PRESET_BD": {"label": "HandBrake preset · Blu-ray", "group": "transcode", "type": "text"},
    "HB_ARGS_DVD": {"label": "HandBrake extra args · DVD", "group": "transcode", "type": "text"},
    "HB_ARGS_BD": {"label": "HandBrake extra args · Blu-ray", "group": "transcode", "type": "text"},
    "MKV_ARGS": {"label": "MakeMKV arguments", "group": "transcode", "type": "text"},
    "MAX_CONCURRENT_TRANSCODES": {"label": "Concurrent transcodes", "group": "transcode", "type": "number"},
    "MAX_CONCURRENT_MAKEMKVINFO": {"label": "Concurrent MakeMKV info calls", "group": "transcode", "type": "number"},
    "DELRAWFILES": {"label": "Delete working files", "group": "transcode", "type": "bool"},
    "MAKEMKV_PERMA_KEY": {"label": "MakeMKV permanent key", "group": "transcode", "type": "text"},

    # Metadata
    "METADATA_PROVIDER": {"label": "Metadata provider", "group": "metadata", "type": "enum",
                          "options": ["omdb", "tmdb"]},
    "GET_AUDIO_TITLE": {"label": "Audio CD lookup", "group": "metadata", "type": "enum",
                        "options": ["none", "musicbrainz", "freecddb"]},
    "OMDB_API_KEY": {"label": "OMDb API key", "group": "metadata", "type": "text"},
    "TMDB_API_KEY": {"label": "TMDb API key", "group": "metadata", "type": "text"},
    "ARM_API_KEY": {"label": "ARM API key", "group": "metadata", "type": "text"},

    # Directories
    "RAW_PATH": {"label": "Raw files", "group": "dirs", "type": "path"},
    "TRANSCODE_PATH": {"label": "Transcode working dir", "group": "dirs", "type": "path"},
    "COMPLETED_PATH": {"label": "Completed files", "group": "dirs", "type": "path"},
    "EXTRAS_SUB": {"label": "Extras subfolder name", "group": "dirs", "type": "text"},
    "INSTALLPATH": {"label": "ARM install path", "group": "dirs", "type": "path"},
    "LOGPATH": {"label": "Log directory", "group": "dirs", "type": "path"},
    "DBFILE": {"label": "Database file", "group": "dirs", "type": "path"},

    # Web & security
    "DISABLE_LOGIN": {"label": "Disable login", "group": "web", "type": "bool",
                      "tag": {"c": "crit", "t": "opens the UI to anyone"}},
    "WEBSERVER_IP": {"label": "Web server address", "group": "web", "type": "text"},
    "WEBSERVER_PORT": {"label": "Web server port", "group": "web", "type": "number"},
    "UI_BASE_URL": {"label": "Public base URL", "group": "web", "type": "text"},

    # File permissions
    "SET_MEDIA_PERMISSIONS": {"label": "Set media permissions", "group": "perms", "type": "bool"},
    "CHMOD_VALUE": {"label": "chmod value", "group": "perms", "type": "text"},
    "SET_MEDIA_OWNER": {"label": "Set media owner", "group": "perms", "type": "bool"},
    "CHOWN_USER": {"label": "Owner user", "group": "perms", "type": "text"},
    "CHOWN_GROUP": {"label": "Owner group", "group": "perms", "type": "text"},
    "UMASK": {"label": "Process umask", "group": "perms", "type": "text"},

    # Logging
    "LOGLEVEL": {"label": "Log level", "group": "logging", "type": "enum",
                 "options": ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]},
    "LOGLIFE": {"label": "Log retention", "group": "logging", "type": "number", "unit": "days"},
}

# Word -> display form for label auto-derivation of unmapped keys.
_ACRONYMS = {
    "API": "API", "ID": "ID", "URL": "URL", "IP": "IP", "DVD": "DVD", "BD": "BD",
    "CLI": "CLI", "MKV": "MKV", "FFMPEG": "FFmpeg", "EMBY": "Emby", "TMDB": "TMDb",
    "OMDB": "OMDb", "PB": "Pushbullet", "IFTTT": "IFTTT", "PO": "Pushover",
    "HB": "HandBrake", "ARM": "ARM", "UDF": "UDF", "JSON": "JSON", "UI": "UI",
}


def humanize(key):
    """Derive a readable label from a config key, preserving known acronyms."""
    words = []
    for part in str(key).split("_"):
        if not part:
            continue
        words.append(_ACRONYMS.get(part.upper(), part.capitalize()))
    return " ".join(words)


def _clean_desc(raw):
    """Turn a comments.json entry (leading '#', embedded newlines) into prose."""
    if not raw:
        return ""
    lines = [line.lstrip("#").strip() for line in str(raw).split("\n")]
    return " ".join(line for line in lines if line)


def _format_value(raw, ftype):
    """Format a stored value for its control (booleans -> yaml literals)."""
    if ftype == "bool":
        if isinstance(raw, bool):
            return "true" if raw else "false"
        return str(raw).strip().lower() if str(raw).strip().lower() in ("true", "false") else "false"
    return "" if raw is None else str(raw)


def build_field_model(arm_config, comments):
    """Build the ordered, grouped field model for the Ripper Settings page.

    Every key in ``arm_config`` yields exactly one field. Unmapped keys land in
    the "Advanced" group as text (or a toggle if their value is boolean).
    Empty groups are dropped.
    """
    groups = OrderedDict(
        (gid, {"id": gid, "label": label, "sub": sub, "fields": []})
        for gid, label, sub in GROUPS
    )
    for key, raw in arm_config.items():
        meta = FIELDS.get(key)
        if meta:
            group_id = meta["group"]
            ftype = meta["type"]
            label = meta["label"]
            options = meta.get("options") or []
            unit = meta.get("unit") or ""
            tag = meta.get("tag")
        else:
            group_id = "advanced"
            ftype = "bool" if isinstance(raw, bool) else "text"
            label = humanize(key)
            options = []
            unit = ""
            tag = None
        groups[group_id]["fields"].append({
            "key": key,
            "group_id": group_id,
            "label": label,
            "type": ftype,
            "options": options,
            "unit": unit,
            "tag": tag,
            "value": _format_value(raw, ftype),
            "desc": _clean_desc(comments.get(key, "") if comments else ""),
        })
    return [group for group in groups.values() if group["fields"]]
