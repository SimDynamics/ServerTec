"""Strict, small, user-scoped portable Android preference documents.

Only keys from actual LearnGraphicsProgramming settings repositories are allowed.
No files, tokens, caches, local audio paths, entitlement flags or opaque metadata.
"""
from __future__ import annotations

import json
import math
import re


PORTABLE_NAMESPACES = frozenset({
    "appearance_settings",
    "code_wrap_settings",
    "keyboard_shortcut_settings",
    "learning_flow_settings",
    "lesson_text_size_settings",
    "ui_language_settings",
    "lesson_narration_settings",
})
_COURSE = r"[A-Za-z0-9_-]{1,96}"
_ROUTES = ("programming", "math_physics")
_RGB_KEYS = {f"{prefix}{component}" for prefix in ("accent_", "default_global_accent_")
             for component in ("red", "green", "blue")}
_RGB_PREFIXES = ("route_accent_red_", "route_accent_green_", "route_accent_blue_",
                 "default_route_accent_red_", "default_route_accent_green_",
                 "default_route_accent_blue_")
_FLOW_SUFFIXES = ("enabled", "between_lessons", "between_units",
                  "between_courses", "swipe_finish")
_FLOW_GLOBAL = {"global_between_lessons", "global_between_units",
                "global_between_courses", "global_swipe_finish"}
_NARRATION_FLAGS = {"enabled", "kokoro_advance_generation", "controls_visible"}


def _course_suffix(key: str, prefix: str) -> bool:
    return key.startswith(prefix) and re.fullmatch(_COURSE, key[len(prefix):]) is not None


def _kind_for_key(namespace: str, key: str) -> str | None:
    if namespace == "appearance_settings":
        if key in _RGB_KEYS or any(key == prefix + route
                                   for prefix in _RGB_PREFIXES for route in _ROUTES):
            return "rgb"
        if any(key == "route_allow_global_accent_overwrite_" + route for route in _ROUTES):
            return "bool"
    elif namespace == "code_wrap_settings":
        if key == "global_wrap" or any(_course_suffix(key, prefix) for prefix in
                                      ("course_wrap_", "course_allow_global_overwrite_")):
            return "bool"
    elif namespace == "keyboard_shortcut_settings":
        if key == "cpp_shortcuts":
            return "shortcuts"
    elif namespace == "learning_flow_settings":
        if key in _FLOW_GLOBAL or any(
            re.fullmatch(r"course_override_" + _COURSE + "_" + suffix, key)
            for suffix in _FLOW_SUFFIXES
        ):
            return "bool"
    elif namespace == "lesson_text_size_settings":
        if key == "global_scale" or _course_suffix(key, "course_scale_"):
            return "scale"
        if _course_suffix(key, "course_use_global_"):
            return "bool"
    elif namespace == "ui_language_settings":
        if key == "selection":
            return "ui_language"
    elif namespace == "lesson_narration_settings":
        if key in _NARRATION_FLAGS:
            return "bool"
        if key == "engine":
            return "engine"
        if key == "rate":
            return "rate"
        if key in {"language", "last_english_language"}:
            return "language"
        if key == "kokoro_voice" or re.fullmatch(
            r"kokoro_voice:(?:es|fr|en(?:-US|-GB)?)", key):
            return "voice"
        # Android TTS voice IDs and audio-generation pause lists are device-specific.
    return None


def _valid_value(kind: str, value: object) -> bool:
    if kind == "bool":
        return type(value) is bool
    if kind == "rgb":
        return type(value) is int and 0 <= value <= 255
    if kind == "scale":
        return type(value) is int and 75 <= value <= 150
    if kind == "rate":
        return type(value) in (int, float) and math.isfinite(value) and 0.5 <= value <= 2.0
    if kind == "ui_language":
        return type(value) is str and value in ("", "es", "en", "fr")
    if kind == "engine":
        return type(value) is str and value in ("AUTO", "KOKORO", "ANDROID")
    if kind == "language":
        return type(value) is str and re.fullmatch(r"[a-z]{2}(?:-[A-Z]{2})?", value) is not None
    if kind == "voice":
        return type(value) is str and re.fullmatch(r"[A-Za-z0-9_-]{1,64}", value) is not None
    if kind == "shortcuts":
        if type(value) is not str or len(value.encode("utf-8")) > 4096:
            return False
        try:
            decoded = json.loads(value)
        except (ValueError, TypeError):
            return False
        return (type(decoded) is list and len(decoded) <= 80
                and all(type(item) is str and len(item) <= 32 for item in decoded))
    return False


def validate_portable_settings(namespace: str, values: dict[str, object]) -> str:
    if namespace not in PORTABLE_NAMESPACES or type(values) is not dict or len(values) > 128:
        raise ValueError("invalid_portable_settings")
    for key, value in values.items():
        if type(key) is not str or re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", key) is None:
            raise ValueError("invalid_portable_setting")
        kind = _kind_for_key(namespace, key)
        if kind is None or not _valid_value(kind, value):
            raise ValueError("invalid_portable_setting")
    canonical = json.dumps(values, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if len(canonical.encode("utf-8")) > 12288:
        raise ValueError("portable_settings_too_large")
    return canonical
