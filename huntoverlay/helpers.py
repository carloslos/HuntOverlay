# Color, screen/aspect, keybind label and data format helpers.
from PySide6 import QtGui

from .constants import (
    MAPS,
    VK_TAB,
    VK_BT,
    VK_DELETE,
    VK_SHIFT,
    VK_CONTROL,
    VK_MENU,
    VK_ESC,
)


def q2rgb(c: QtGui.QColor):
    return [c.red(), c.green(), c.blue()]


def rgb2q(v, fallback=QtGui.QColor(255, 180, 80)) -> QtGui.QColor:
    try:
        r, g, b = v
        return QtGui.QColor(int(r), int(g), int(b))
    except:
        return QtGui.QColor(fallback)


def screenWH():
    g = QtGui.QGuiApplication.primaryScreen().geometry()
    return g.width(), g.height()


def detect_aspect_label(w: int, h: int) -> str:
    """
    Aspect bucketing
    32:9 if a >= 3.20
    21:9 if a >= 2.20
    else 16:9
    """
    if h <= 0:
        return "16:9"
    a = float(w) / float(h)
    if a >= 3.20:
        return "32:9"
    if a >= 2.20:
        return "21:9"
    return "16:9"


def vk_to_label(vk: int) -> str:
    if vk == VK_TAB: return "Tab"
    if vk == VK_BT: return "`"
    if vk == VK_DELETE: return "Delete"
    if vk == VK_SHIFT: return "Shift"
    if vk == VK_CONTROL: return "Ctrl"
    if vk == VK_MENU: return "Alt"
    if 0x30 <= vk <= 0x39: return chr(vk)
    if 0x41 <= vk <= 0x5A: return chr(vk)
    if vk == VK_ESC: return "Esc"
    return f"VK_{vk}"


def rotate90cw_norm(x, y):
    """
    Converts 4096 map coordinates into normalized u,v (0..1) after 90° clockwise rotation.
    v is top down for painting.
    """
    xr = float(y)
    yr = 4095.0 - float(x)
    u = xr / 4095.0
    v = yr / 4095.0
    if u < 0: u = 0.0
    if u > 1: u = 1.0
    if v < 0: v = 0.0
    if v > 1: v = 1.0
    return u, v


def detect_data_format(game_data) -> str:
    """
    Supports two formats
    indexed_r: list of dicts with "i" map index and "r" categories
    named: list of dicts with "n" map name and direct category arrays
    """
    if isinstance(game_data, list) and game_data:
        a = game_data[0]
        if isinstance(a, dict) and "i" in a and ("r" in a or "a" in a):
            return "indexed_r"
        if isinstance(a, dict) and "n" in a:
            return "named"
    return "unknown"


def get_map_block(game_data, fmt: str, map_name: str):
    if fmt == "named":
        for m in game_data:
            if isinstance(m, dict) and m.get("n") == map_name:
                return m
        return None

    if fmt == "indexed_r":
        idx = MAPS.index(map_name)
        for m in game_data:
            if isinstance(m, dict) and m.get("i") == idx:
                return m
        return None

    return None


def get_category_list(map_block, fmt: str, category: str):
    if not isinstance(map_block, dict):
        return []
    if fmt == "named":
        v = map_block.get(category, [])
        return v if isinstance(v, list) else []
    if fmt == "indexed_r":
        r = map_block.get("r", {})
        if isinstance(r, dict):
            v = r.get(category, [])
            return v if isinstance(v, list) else []
        return []
    return []


def find_style_by_category(style_json, category: str):
    if not isinstance(style_json, dict):
        return None
    for _, spec in style_json.items():
        if isinstance(spec, dict) and spec.get("categories") == category:
            return spec
    return None


def qcolor_from_any(value, fallback: QtGui.QColor) -> QtGui.QColor:
    try:
        c = QtGui.QColor(str(value))
        return c if c.isValid() else QtGui.QColor(fallback)
    except:
        return QtGui.QColor(fallback)


def overlay_radius_from_spec(spec_radius) -> int:
    """
    Converts poiData.json radius into a stable on screen radius baseline.
    """
    try:
        r = float(spec_radius)
    except:
        r = 12.0
    px = int(round(r * 0.25))
    if px < 3: px = 3
    if px > 10: px = 10
    return px
