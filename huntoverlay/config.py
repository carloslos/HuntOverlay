# Default config, rect ratios, keybinds and config load/replace.
#
# Config version gate (Option C)
#   If config.json missing OR version mismatch, it is replaced with a fresh
#   default config. Current config version: CONFIG_VERSION
import os

from .constants import (
    MAPS,
    CONFIG_VERSION,
    DEFAULT_HIDDEN_POSSIBLE_XP,
    VK_TAB,
    VK_H,
    VK_O,
    VK_BT,
    VK1,
    VK2,
    VK3,
    VK4,
)
from .paths import CONFIG_PATH, load_json, save_json


def default_rect_ratio_16_9():
    return {"rx": 0.30859375, "ry": 0.14583333333333334, "rw": 0.383984375, "rh": 0.6833333333333333}


def default_rect_ratio_21_9():
    return {"rx": 0.35625, "ry": 0.14722222222222223, "rw": 0.287109375, "rh": 0.6814814814814815}


def default_rect_ratio_32_9():
    return {"rx": 0.404296875, "ry": 0.14722222222222223, "rw": 0.191015625, "rh": 0.6791666666666667}


def default_rect_ratio_by_aspect():
    return {"16:9": default_rect_ratio_16_9(), "21:9": default_rect_ratio_21_9(), "32:9": default_rect_ratio_32_9()}


def default_keybinds():
    """
    Keybind schema is stored under settings.keybinds
    Each action is a dict:
      vk: int virtual key code
      ctrl alt shift: optional booleans for modifier gated binds
    """
    return {
        "toggle_master": {"vk": VK_BT},
        "toggle_overlay": {"vk": VK_TAB},
        "hide_overlay": {"vk": VK_H},
        "map_1": {"vk": VK1},
        "map_2": {"vk": VK2},
        "map_3": {"vk": VK3},
        "map_4": {"vk": VK4},
        "detect_map": {"vk": VK_O},
    }


def build_default_config():
    profiles = {}
    for m in MAPS:
        profiles[m] = {"rect_ratio_by_aspect": default_rect_ratio_by_aspect()}
    return {
        "version": CONFIG_VERSION,
        "profiles": profiles,
        "settings": {
            "enable_num_switch": True,
            "selected_map": MAPS[0],
            "visible_overlay": False,
            "master_on": True,
            "global_scale": 1.00,
            "minimize_to_tray": False,
            "keybinds": default_keybinds(),
            "types": {},
            "hidden": {"possible_xp": list(DEFAULT_HIDDEN_POSSIBLE_XP)},
        },
    }


def load_or_replace_config():
    """
    Option C
    If config.json missing OR version mismatch, replace with a fresh default config.
    """
    if not os.path.isfile(CONFIG_PATH):
        d = build_default_config()
        save_json(CONFIG_PATH, d)
        return d

    try:
        d = load_json(CONFIG_PATH)
    except:
        d = {}

    if not isinstance(d, dict) or d.get("version") != CONFIG_VERSION:
        d = build_default_config()
        save_json(CONFIG_PATH, d)
        return d

    return d
