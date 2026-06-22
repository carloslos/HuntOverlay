# Runtime paths and JSON file helpers.
#
# All runtime files live in:
#   %LOCALAPPDATA%\HuntOverlay
#
# Seeded files on first run
#   data.json     POI coordinate dataset
#   poiData.json  style definitions for POI types
#   config.json   user settings, per map rect ratios, keybinds, hidden POIs
import sys, os, json, shutil


def bd() -> str:
    # Base directory used to locate bundled/seed resources.
    # PyInstaller builds expose _MEIPASS; normal .py runs use the repo root,
    # which is the parent of this package directory.
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return meipass
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def udir() -> str:
    # All runtime files live here.
    p = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "HuntOverlay")
    os.makedirs(p, exist_ok=True)
    return p


def ensure_user_file(filename: str) -> str:
    """
    Ensure a file exists in %LOCALAPPDATA%\\HuntOverlay by copying from:
      1) bundled resources (PyInstaller _MEIPASS) or repo root
      2) the package's parent folder (when running as .py)
    Returns the user file path.
    """
    dst = os.path.join(udir(), filename)
    if os.path.isfile(dst):
        return dst

    src1 = os.path.join(bd(), filename)
    src2 = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), filename)

    src = src1 if os.path.isfile(src1) else (src2 if os.path.isfile(src2) else "")
    if src:
        try:
            shutil.copyfile(src, dst)
        except:
            pass

    return dst


ICON = os.path.join(bd(), "myicon.ico") if os.path.isfile(os.path.join(bd(), "myicon.ico")) else ""
DATA_PATH = ensure_user_file("data.json")
STYLE_PATH = ensure_user_file("poiData.json")
CONFIG_PATH = os.path.join(udir(), "config.json")


def load_json(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: str, obj) -> None:
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(json.dumps(obj, indent=2))
    except:
        pass
