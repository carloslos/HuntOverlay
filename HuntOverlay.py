# HuntOverlay.py
# Hunt Map Overlay By sKhaled
#
# What this app does
# 1) On first run, it seeds these files into %LOCALAPPDATA%\HuntOverlay
#    data.json
#    poiData.json
#    config.json (overlay settings, rect profiles, enabled types, colors, hidden POIs, global size scale)
#
# 2) It always loads data.json and poiData.json from %LOCALAPPDATA%\HuntOverlay
#    If you edit those there, the overlay uses your edits.
#
# 3) It draws POIs in a screen rectangle using normalized coordinates derived from the 4096x4096 map grid.
#
# 4) It provides a control panel window with:
#    Per type enable checkbox
#    Per type color picker
#    Map selection
#    Global POI size scaling controls
#    Hotkey instructions
#
# 5) Hotkeys
#    ` (backtick) toggles master on/off
#    Tab toggles overlay visible
#    H hides overlay
#    1,2,3,4 switches map if enabled in GUI
#    Ctrl + Alt + Shift + Delete hides the hovered POI for that currently hovered category only
#
# Notes about hide behavior
# If you hide a POI while hovering "possible_xp", it only hides it from possible_xp,
# not from its source category (armories, towers, big_towers).
# Hidden POIs are stored per category in config.json.

import sys, os, json, ctypes, traceback, shutil
from PySide6 import QtCore, QtGui, QtWidgets

MAPS = ["Stillwater Bayou", "DeSalle", "Lawson Delta", "Mammon's Gulch"]

VK_TAB = 0x09
VK_H = 0x48
VK_BT = 0xC0
VK1, VK2, VK3, VK4 = 0x31, 0x32, 0x33, 0x34

VK_DELETE = 0x2E
VK_SHIFT = 0x10
VK_CONTROL = 0x11
VK_MENU = 0x12  # Alt

user32 = ctypes.windll.user32
GetKey = user32.GetAsyncKeyState

def key(vk: int) -> bool:
    return (GetKey(vk) & 0x8000) != 0

def topmost(hwnd: int) -> None:
    try:
        user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x1 | 0x2 | 0x10 | 0x40)
    except:
        pass

def click_through(hwnd: int) -> None:
    try:
        style = user32.GetWindowLongW(hwnd, -20)
        user32.SetWindowLongW(hwnd, -20, style | 0x80000 | 0x80 | 0x8000000 | 0x20)
    except:
        pass

def bd() -> str:
    # Base directory: PyInstaller temp folder when frozen, else script folder
    return getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))

def udir() -> str:
    # Target folder for all runtime files
    p = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "HuntOverlay")
    os.makedirs(p, exist_ok=True)
    return p

def ensure_user_file(filename: str) -> str:
    """
    Ensure a file exists in %LOCALAPPDATA%\HuntOverlay by copying from:
    1) bundled resources (PyInstaller _MEIPASS)
    2) script folder (when running as .py)
    Returns the user file path.
    """
    dst = os.path.join(udir(), filename)
    if os.path.isfile(dst):
        return dst

    src1 = os.path.join(bd(), filename)
    src2 = os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)

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

def q2rgb(c: QtGui.QColor):
    return [c.red(), c.green(), c.blue()]

def rgb2q(v, fallback=QtGui.QColor(255, 180, 80)) -> QtGui.QColor:
    try:
        r, g, b = v
        return QtGui.QColor(int(r), int(g), int(b))
    except:
        return QtGui.QColor(fallback)

def load_json(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_json(path: str, obj) -> None:
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(json.dumps(obj, indent=2))
    except:
        pass

def screenWH():
    g = QtGui.QGuiApplication.primaryScreen().geometry()
    return g.width(), g.height()

def default_rect_ratio():
    # Your recorded rectangle for 2560x1440
    return {
        "rx": 790 / 2560,
        "ry": 210 / 1440,
        "rw": 983 / 2560,
        "rh": 984 / 1440
    }

def rotate90cw_norm(x, y):
    """
    Converts 4096 map coordinates into normalized u,v (0..1) after 90° clockwise rotation.
    Final v is already in top-left origin terms for painting (since we use rect.top + v*height).
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
    Supports two formats:
    1) indexed_r: list of dicts with "i" map index and "r" categories
    2) named: list of dicts with "n" map name and direct category arrays
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
    # Your poiData.json uses a dict of style specs; each spec has categories=...
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
    Convert the poiData.json 'radius' into a reasonable screen radius.
    This keeps your existing mapping but makes it consistent.
    """
    try:
        r = float(spec_radius)
    except:
        r = 12.0
    px = int(round(r * 0.25))
    if px < 3: px = 3
    if px > 10: px = 10
    return px

class SVPad(QtWidgets.QWidget):
    changed = QtCore.Signal(int, int)

    def __init__(self, p=None):
        super().__init__(p)
        self.setMinimumSize(180, 140)
        self.h = 255
        self.s = 255
        self.v = 255
        self.cross = QtCore.QPointF(0, 0)

    def setHue(self, h: int):
        self.h = max(0, min(359, int(h)))
        self.update()

    def setSV(self, sv: int, vv: int):
        self.s = max(0, min(255, int(sv)))
        self.v = max(0, min(255, int(vv)))
        self.cross = QtCore.QPointF(self.s / 255 * self.width(), (1 - self.v / 255) * self.height())
        self.update()

    def mousePressEvent(self, e):
        self._hit(e)

    def mouseMoveEvent(self, e):
        self._hit(e)

    def _hit(self, e):
        x = max(0, min(self.width(), e.position().x()))
        y = max(0, min(self.height(), e.position().y()))
        S = int(round(x / max(1, self.width()) * 255))
        V = int(round((1 - y / max(1, self.height())) * 255))
        if S != self.s or V != self.v:
            self.setSV(S, V)
            self.changed.emit(self.s, self.v)

    def paintEvent(self, _):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        hc = QtGui.QColor()
        hc.setHsv(self.h, 255, 255)
        g = QtGui.QLinearGradient(0, 0, self.width(), 0)
        g.setColorAt(0, QtGui.QColor(255, 255, 255))
        g.setColorAt(1, hc)
        p.fillRect(self.rect(), g)
        g2 = QtGui.QLinearGradient(0, 0, 0, self.height())
        g2.setColorAt(0, QtGui.QColor(0, 0, 0, 0))
        g2.setColorAt(1, QtGui.QColor(0, 0, 0, 255))
        p.fillRect(self.rect(), g2)
        p.setPen(QtGui.QPen(QtGui.QColor(240, 240, 240), 1))
        p.drawEllipse(self.cross, 5, 5)
        p.setPen(QtGui.QPen(QtGui.QColor(20, 20, 20), 1))
        p.drawEllipse(self.cross, 3, 3)

class AdvColorDlg(QtWidgets.QDialog):
    def __init__(self, start: QtGui.QColor, p=None):
        super().__init__(p)
        self.setWindowTitle("Pick Color")
        self.setModal(True)
        self.setWindowFlags(self.windowFlags() | QtCore.Qt.Tool)
        self.setStyleSheet(
            "QWidget{background:#1e1f22;color:#e6e6e6;}"
            "QSlider::groove:horizontal{height:6px;background:#2b2d30;}"
            "QSlider::handle:horizontal{width:12px;background:#90a0ff;margin:-6px 0;border-radius:3px;}"
            "QSpinBox,QLineEdit{background:#2b2d30;color:#e6e6e6;border:1px solid #3a3c40;}"
            "QPushButton{background:#2b2d30;border:1px solid #3a3c40;padding:4px 10px;}"
            "QPushButton:hover{background:#34363a;}"
        )
        self.pad = SVPad(self)
        self.h = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.h.setRange(0, 359)
        self.r = QtWidgets.QSpinBox()
        self.g = QtWidgets.QSpinBox()
        self.b = QtWidgets.QSpinBox()
        for sp in (self.r, self.g, self.b):
            sp.setRange(0, 255)
        self.hex = QtWidgets.QLineEdit()
        self.hex.setMaxLength(7)
        self.hex.setPlaceholderText("#RRGGBB")
        self.prev = QtWidgets.QLabel()
        self.prev.setFixedSize(48, 48)
        self.prev.setFrameShape(QtWidgets.QFrame.Panel)
        self.prev.setFrameShadow(QtWidgets.QFrame.Sunken)

        presets = [
            "#ffffff", "#000000", "#ff0000", "#00ff00", "#0000ff", "#ffff00", "#ff00ff", "#00ffff",
            "#ffa500", "#ffc107", "#795548", "#9e9e9e", "#607d8b", "#8bc34a", "#3f51b5", "#e91e63"
        ]
        grid = QtWidgets.QGridLayout()
        for i, hx in enumerate(presets):
            b = QtWidgets.QPushButton()
            b.setFixedSize(20, 20)
            b.setStyleSheet(f"border:1px solid #3a3c40;background:{hx};")
            b.clicked.connect(lambda _, h=hx: self._set_hex(h))
            grid.addWidget(b, i // 8, i % 8)

        def row(lbl, spin):
            h = QtWidgets.QHBoxLayout()
            h.addWidget(QtWidgets.QLabel(lbl))
            h.addWidget(spin)
            return h

        v = QtWidgets.QVBoxLayout(self)
        v.addWidget(self.pad)
        v.addWidget(QtWidgets.QLabel("Hue"))
        v.addWidget(self.h)
        rgb = QtWidgets.QHBoxLayout()
        rgb.addLayout(row("R", self.r))
        rgb.addLayout(row("G", self.g))
        rgb.addLayout(row("B", self.b))
        v.addLayout(rgb)
        hh = QtWidgets.QHBoxLayout()
        hh.addWidget(QtWidgets.QLabel("Hex"))
        hh.addWidget(self.hex)
        hh.addStretch(1)
        hh.addWidget(self.prev)
        v.addLayout(hh)
        v.addWidget(QtWidgets.QLabel("Presets"))
        v.addLayout(grid)
        bt = QtWidgets.QHBoxLayout()
        ok = QtWidgets.QPushButton("OK")
        ca = QtWidgets.QPushButton("Cancel")
        bt.addStretch(1)
        bt.addWidget(ok)
        bt.addWidget(ca)
        v.addLayout(bt)

        self.h.valueChanged.connect(self._h_changed)
        self.pad.changed.connect(self._sv_changed)
        self.r.valueChanged.connect(self._rgb_changed)
        self.g.valueChanged.connect(self._rgb_changed)
        self.b.valueChanged.connect(self._rgb_changed)
        self.hex.editingFinished.connect(self._hex_changed)
        ok.clicked.connect(self.accept)
        ca.clicked.connect(self.reject)

        self._lock = False
        self._from_color(start)

    def _preview(self, c: QtGui.QColor):
        self.prev.setStyleSheet(f"background: rgb({c.red()},{c.green()},{c.blue()}); border:1px solid #3a3c40;")

    def _set_hex(self, hx: str):
        c = QtGui.QColor(hx if hx.startswith("#") else "#" + hx)
        if c.isValid():
            self._from_color(c)

    def _hex_changed(self):
        self._set_hex(self.hex.text().strip())

    def _h_changed(self, h: int):
        if self._lock:
            return
        self._lock = True
        self.pad.setHue(h)
        self._sync_rgb_hex(self.selectedColor())
        self._lock = False

    def _sv_changed(self, S: int, V: int):
        if self._lock:
            return
        self._lock = True
        c = QtGui.QColor()
        c.setHsv(self.h.value(), S, V)
        self._sync_rgb_hex(c)
        self._lock = False

    def _rgb_changed(self, _=None):
        if self._lock:
            return
        self._lock = True
        c = QtGui.QColor(self.r.value(), self.g.value(), self.b.value())
        h, S, V, _a = c.getHsv()
        h = max(0, h)
        self.h.setValue(h)
        self.pad.setHue(h)
        self.pad.setSV(S, V)
        self._sync_hex_only(c)
        self._lock = False

    def _sync_rgb_hex(self, c: QtGui.QColor):
        self._preview(c)
        self.hex.setText("#{0:02x}{1:02x}{2:02x}".format(c.red(), c.green(), c.blue()))
        self.r.setValue(c.red())
        self.g.setValue(c.green())
        self.b.setValue(c.blue())

    def _sync_hex_only(self, c: QtGui.QColor):
        self._preview(c)
        self.hex.setText("#{0:02x}{1:02x}{2:02x}".format(c.red(), c.green(), c.blue()))

    def _from_color(self, c: QtGui.QColor):
        h, S, V, _a = c.getHsv()
        h = max(0, h)
        self._lock = True
        self.h.setValue(h)
        self.pad.setHue(h)
        self.pad.setSV(S, V)
        self._sync_rgb_hex(c)
        self._lock = False

    def selectedColor(self) -> QtGui.QColor:
        c = QtGui.QColor()
        c.setHsv(self.h.value(), self.pad.s, self.pad.v)
        return c

class DotChip(QtWidgets.QPushButton):
    changed = QtCore.Signal(QtGui.QColor)

    def __init__(self, fill: QtGui.QColor, border=QtGui.QColor(85, 85, 85), p=None):
        super().__init__(p)
        self.fill = QtGui.QColor(fill)
        self.border = QtGui.QColor(border)
        self.setFixedSize(20, 20)
        self.setCursor(QtCore.Qt.PointingHandCursor)
        self.clicked.connect(self.pick)
        self._paint()

    def _paint(self):
        f = self.fill
        b = self.border
        self.setStyleSheet(
            "QPushButton{"
            f"border:2px solid rgb({b.red()},{b.green()},{b.blue()});"
            "border-radius:10px;"
            f"background: rgb({f.red()},{f.green()},{f.blue()});"
            "}"
            "QPushButton:hover{filter:brightness(1.05);}"
        )

    def setFill(self, c: QtGui.QColor):
        self.fill = QtGui.QColor(c)
        self._paint()
        self.changed.emit(self.fill)

    def pick(self):
        d = AdvColorDlg(self.fill, self)
        if ICON:
            d.setWindowIcon(QtGui.QIcon(ICON))
        if d.exec() == QtWidgets.QDialog.Accepted:
            self.setFill(d.selectedColor())

class Panel(QtWidgets.QWidget):
    mapSel = QtCore.Signal(str)
    tnums = QtCore.Signal(bool)
    reset = QtCore.Signal()
    typeToggled = QtCore.Signal(str, bool)
    typeColor = QtCore.Signal(str, QtGui.QColor)
    scaleChanged = QtCore.Signal(float)

    def __init__(self, type_order, type_specs, start_scale: float, p=None):
        super().__init__(p, QtCore.Qt.Window | QtCore.Qt.WindowStaysOnTopHint)
        self.setWindowTitle("Hunt Map Overlay By sKhaled")
        self.setFixedWidth(360)
        self.setStyleSheet(
            "QWidget{background:#1e1f22;color:#e6e6e6;}"
            "QComboBox,QLineEdit,QSpinBox,QDoubleSpinBox{background:#2b2d30;color:#e6e6e6;border:1px solid #3a3c40;}"
            "QPushButton{background:#2b2d30;border:1px solid #3a3c40;padding:4px 8px;}"
            "QPushButton:hover{background:#34363a;}"
            "QLabel{color:#cfd1d4;}"
            "QCheckBox{spacing:10px;}"
            "QCheckBox::indicator{width:16px;height:16px;}"
        )

        self.type_widgets = {}
        v = QtWidgets.QVBoxLayout(self)

        title = QtWidgets.QLabel("POI Types")
        f = title.font()
        f.setBold(True)
        title.setFont(f)
        v.addWidget(title)

        for tkey in type_order:
            spec = type_specs[tkey]
            chk = QtWidgets.QCheckBox(spec["label"])
            chip = DotChip(spec["default_fill"], spec["border"])
            row = QtWidgets.QHBoxLayout()
            row.addWidget(chk)
            row.addStretch(1)
            row.addWidget(chip)
            v.addLayout(row)
            self.type_widgets[tkey] = (chk, chip)
            chk.toggled.connect(lambda val, k=tkey: self.typeToggled.emit(k, val))
            chip.changed.connect(lambda col, k=tkey: self.typeColor.emit(k, col))

            if tkey == "possible_xp":
                line = QtWidgets.QFrame()
                line.setFrameShape(QtWidgets.QFrame.HLine)
                line.setFrameShadow(QtWidgets.QFrame.Sunken)
                line.setStyleSheet("color:#2b2d30;background:#2b2d30;max-height:1px;")
                v.addWidget(line)

        v.addSpacing(6)

        self.chk_nums = QtWidgets.QCheckBox("Enable 1 to 4 Map Switch")
        v.addWidget(self.chk_nums)
        self.chk_nums.toggled.connect(self.tnums)

        v.addWidget(QtWidgets.QLabel("Map:"))
        self.cmb = QtWidgets.QComboBox()
        self.cmb.addItems(MAPS)
        v.addWidget(self.cmb)
        self.cmb.currentTextChanged.connect(self.mapSel)

        v.addSpacing(6)

        v.addWidget(QtWidgets.QLabel("POI Size Scale (global):"))
        scale_row = QtWidgets.QHBoxLayout()
        self.btn_dec = QtWidgets.QPushButton("Smaller")
        self.btn_inc = QtWidgets.QPushButton("Bigger")
        self.scale_box = QtWidgets.QDoubleSpinBox()
        self.scale_box.setRange(0.10, 5.00)
        self.scale_box.setDecimals(2)
        self.scale_box.setSingleStep(0.05)
        self.scale_box.setValue(float(start_scale))
        self.scale_box.setFixedWidth(90)

        scale_row.addWidget(self.btn_dec)
        scale_row.addWidget(self.btn_inc)
        scale_row.addStretch(1)
        scale_row.addWidget(self.scale_box)
        v.addLayout(scale_row)

        self.btn_dec.clicked.connect(self._dec_scale)
        self.btn_inc.clicked.connect(self._inc_scale)
        self.scale_box.valueChanged.connect(lambda x: self.scaleChanged.emit(float(x)))

        v.addSpacing(6)

        self.btn_def = QtWidgets.QPushButton("Default Colors")
        v.addWidget(self.btn_def)
        self.btn_def.clicked.connect(self.reset)

        v.addSpacing(8)

        v.addWidget(QtWidgets.QLabel("Controls"))
        self.help = QtWidgets.QTextEdit()
        self.help.setReadOnly(True)
        self.help.setFixedHeight(150)
        self.help.setStyleSheet("QTextEdit{background:#202225;border:1px solid #3a3c40;}")
        self.help.setText(
            "Backtick `   Toggle master on or off\n"
            "Tab          Show or hide overlay\n"
            "H            Hide overlay\n"
            "1 2 3 4      Switch map (if enabled)\n"
            "Ctrl Alt Shift Delete   Hide hovered POI for current category only\n"
            "\n"
            "Files are stored at:\n"
            "%LOCALAPPDATA%\\HuntOverlay\n"
        )
        v.addWidget(self.help)

        v.addStretch(1)

    def _dec_scale(self):
        self.scale_box.setValue(max(self.scale_box.minimum(), self.scale_box.value() - 0.05))

    def _inc_scale(self):
        self.scale_box.setValue(min(self.scale_box.maximum(), self.scale_box.value() + 0.05))

    def setTypeState(self, tkey: str, enabled: bool, fill_color: QtGui.QColor):
        chk, chip = self.type_widgets[tkey]
        chk.blockSignals(True)
        chip.blockSignals(True)
        chk.setChecked(bool(enabled))
        chip.setFill(fill_color)
        chip.blockSignals(False)
        chk.blockSignals(False)

    def setMap(self, name: str):
        i = self.cmb.findText(name)
        if i >= 0:
            self.cmb.blockSignals(True)
            self.cmb.setCurrentIndex(i)
            self.cmb.blockSignals(False)

class Overlay(QtWidgets.QWidget):
    def __init__(self):
        super().__init__(None, QtCore.Qt.FramelessWindowHint | QtCore.Qt.WindowStaysOnTopHint | QtCore.Qt.Tool)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)
        self.setAttribute(QtCore.Qt.WA_ShowWithoutActivating, True)
        self.setFocusPolicy(QtCore.Qt.NoFocus)
        self.setMouseTracking(False)
        self.showFullScreen()

        if ICON:
            QtWidgets.QApplication.instance().setWindowIcon(QtGui.QIcon(ICON))
            self.setWindowIcon(QtGui.QIcon(ICON))

        self.data_path = DATA_PATH
        self.style_path = STYLE_PATH

        if not os.path.isfile(self.data_path):
            raise RuntimeError(f"Missing data.json in {udir()}")
        if not os.path.isfile(self.style_path):
            raise RuntimeError(f"Missing poiData.json in {udir()}")

        self.game_data = load_json(self.data_path)
        self.fmt = detect_data_format(self.game_data)
        if self.fmt == "unknown":
            raise RuntimeError("Unrecognized data.json format")

        self.poi_style = load_json(self.style_path)

        self.type_order = [
            "possible_xp",
            "spawns",
            "armories",
            "towers",
            "big_towers",
            "workbenches",
            "wild_targets",
            "beetles",
            "easter_eggs",
            "melee_weapons",
            "cash_registers",
        ]

        self.type_specs = self._build_type_specs()

        self.data = self._load_config()
        st = self.data["settings"]

        self.num_sw = bool(st.get("enable_num_switch", True))
        self.prof = st.get("selected_map", MAPS[0]) if st.get("selected_map") in MAPS else MAPS[0]
        self.visible = bool(st.get("visible_overlay", False))
        self.master = bool(st.get("master_on", True))

        self.global_scale = float(st.get("global_scale", 1.00))
        if self.global_scale < 0.10: self.global_scale = 0.10
        if self.global_scale > 5.00: self.global_scale = 5.00

        # Per type settings: enabled + color
        self.types = st.get("types", {})
        for k in self.type_order:
            if k not in self.types:
                self.types[k] = {"enabled": True, "color": q2rgb(self.type_specs[k]["default_fill"])}
            if "enabled" not in self.types[k]:
                self.types[k]["enabled"] = True
            if "color" not in self.types[k]:
                self.types[k]["color"] = q2rgb(self.type_specs[k]["default_fill"])

        # Hidden POIs stored as sets of stable ids per category
        self.hidden = st.get("hidden", {})
        if not isinstance(self.hidden, dict):
            self.hidden = {}
        for k in self.type_order:
            if k not in self.hidden or not isinstance(self.hidden.get(k), list):
                self.hidden[k] = []
        self.hidden_sets = {k: set(self.hidden.get(k, [])) for k in self.type_order}

        self.rect = None
        self._apply_rect()

        self.panel = Panel(self.type_order, self.type_specs, self.global_scale)
        if ICON:
            self.panel.setWindowIcon(QtGui.QIcon(ICON))

        self.panel.tnums.connect(self._set_num_switch)
        self.panel.mapSel.connect(self.switch)
        self.panel.reset.connect(self._reset_colors)
        self.panel.typeToggled.connect(self._type_toggle)
        self.panel.typeColor.connect(self._type_color)
        self.panel.scaleChanged.connect(self._scale_changed)

        self.panel.chk_nums.setChecked(self.num_sw)
        self.panel.setMap(self.prof)
        for k in self.type_order:
            self.panel.setTypeState(
                k,
                self.types[k]["enabled"],
                rgb2q(self.types[k]["color"], self.type_specs[k]["default_fill"])
            )

        self.panel.move(40, 40)
        self.panel.show()

        click_through(int(self.winId()))
        (self.show if self.visible and self.master else self.hide)()
        topmost(int(self.winId()))

        self.pbt = False
        self.pH = False
        self.pT = False
        self.pHide = False

        self.hover = None
        self.hover_radius = 10

        self.cache = {}
        self._rebuild_all_caches()

        # Tick loop
        self.t = QtCore.QTimer(self)
        self.t.timeout.connect(self._tick_safe)
        self.t.start(16)

    def _build_type_specs(self):
        specs = {}

        possible_fill = QtGui.QColor("#FFD34D")
        possible_border = QtGui.QColor("#FFFFFF")
        specs["possible_xp"] = {
            "label": "Possible XP Location",
            "border": possible_border,
            "default_fill": possible_fill,
            "radius_px": 6,
        }

        def add_from_style(category, fallback_label):
            spec = find_style_by_category(self.poi_style, category) or {}
            label = spec.get("label", fallback_label)
            border = qcolor_from_any(spec.get("borderColor", "#555555"), QtGui.QColor("#555555"))
            fill = qcolor_from_any(spec.get("fillColor", "#B4B4B4"), QtGui.QColor("#B4B4B4"))
            radius_px = overlay_radius_from_spec(spec.get("radius", 12))
            specs[category] = {
                "label": str(label),
                "border": border,
                "default_fill": fill,
                "radius_px": radius_px,
            }

        add_from_style("spawns", "Spawns")
        add_from_style("armories", "Armories")
        add_from_style("towers", "Hunting Towers")
        add_from_style("big_towers", "Watch Towers")
        add_from_style("workbenches", "Workbenches")
        add_from_style("wild_targets", "Wild Targets")
        add_from_style("beetles", "Beetles")
        add_from_style("easter_eggs", "Easter Eggs")
        add_from_style("melee_weapons", "Melee Weapons")
        add_from_style("cash_registers", "Cash Registers")

        return specs

    def _load_config(self):
        """
        Config schema (stored at %LOCALAPPDATA%\\HuntOverlay\\config.json)
        profiles[map].rect_ratio {rx,ry,rw,rh}
        settings:
          enable_num_switch
          selected_map
          visible_overlay
          master_on
          global_scale
          types[type] {enabled, color[r,g,b]}
          hidden[type] [stable_id, ...]
        """
        base = {
            "profiles": {m: {"rect_ratio": default_rect_ratio()} for m in MAPS},
            "settings": {
                "enable_num_switch": True,
                "selected_map": MAPS[0],
                "visible_overlay": False,
                "master_on": True,
                "global_scale": 1.00,
                "types": {},
                "hidden": {}
            }
        }

        d = {}
        if os.path.isfile(CONFIG_PATH):
            try:
                d = load_json(CONFIG_PATH)
            except:
                d = {}

        if isinstance(d, dict):
            if isinstance(d.get("profiles"), dict):
                base["profiles"].update(d["profiles"])
            if isinstance(d.get("settings"), dict):
                base["settings"].update(d["settings"])

        for m in MAPS:
            if m not in base["profiles"]:
                base["profiles"][m] = {"rect_ratio": default_rect_ratio()}
            rr = base["profiles"][m].get("rect_ratio")
            if not isinstance(rr, dict):
                base["profiles"][m]["rect_ratio"] = default_rect_ratio()

        return base

    def _save(self):
        st = self.data["settings"]
        st["enable_num_switch"] = self.num_sw
        st["selected_map"] = self.prof
        st["visible_overlay"] = self.visible
        st["master_on"] = self.master
        st["global_scale"] = float(self.global_scale)
        st["types"] = self.types

        # Persist hidden sets as lists
        st["hidden"] = {k: sorted(list(self.hidden_sets.get(k, set()))) for k in self.type_order}
        save_json(CONFIG_PATH, self.data)

    def _apply_rect(self):
        rr = self.data["profiles"][self.prof].get("rect_ratio")
        if not isinstance(rr, dict):
            self.rect = None
            return
        W, H = screenWH()
        self.rect = QtCore.QRect(
            int(rr["rx"] * W),
            int(rr["ry"] * H),
            max(1, int(rr["rw"] * W)),
            max(1, int(rr["rh"] * H))
        )

    def _set_num_switch(self, v: bool):
        self.num_sw = bool(v)
        self._save()

    def _type_toggle(self, tkey: str, enabled: bool):
        if tkey in self.types:
            self.types[tkey]["enabled"] = bool(enabled)
            self._save()
            self.update()

    def _type_color(self, tkey: str, color: QtGui.QColor):
        if tkey in self.types:
            self.types[tkey]["color"] = q2rgb(QtGui.QColor(color))
            self._save()
            self.update()

    def _scale_changed(self, scale: float):
        self.global_scale = float(scale)
        if self.global_scale < 0.10: self.global_scale = 0.10
        if self.global_scale > 5.00: self.global_scale = 5.00
        self._save()
        self.update()

    def _reset_colors(self):
        for k in self.type_order:
            self.types[k]["enabled"] = True
            self.types[k]["color"] = q2rgb(self.type_specs[k]["default_fill"])
            self.panel.setTypeState(k, True, self.type_specs[k]["default_fill"])
        self._save()
        self.update()

    def switch(self, name: str):
        if name in MAPS and name != self.prof:
            self.prof = name
            self._apply_rect()
            self._save()
            self.update()

    def _rebuild_all_caches(self):
        for m in MAPS:
            self.cache[m] = self._build_points_for_map(m)

    def _build_points_for_map(self, map_name: str):
        block = get_map_block(self.game_data, self.fmt, map_name)
        out = {k: [] for k in self.type_order}
        if not block:
            return out

        def build_for_category(cat: str):
            items = get_category_list(block, self.fmt, cat)
            pts = []
            for it in items:
                if not isinstance(it, dict):
                    continue
                c = it.get("c")
                if not c or len(c) < 2:
                    continue
                try:
                    x, y = float(c[0]), float(c[1])
                except:
                    continue
                u, v = rotate90cw_norm(x, y)
                pts.append({"u": u, "v": v, "x": x, "y": y, "raw": it, "src": cat})
            return pts

        for cat in self.type_order:
            if cat == "possible_xp":
                continue
            out[cat] = build_for_category(cat)

        # possible_xp is a union of three categories, each point keeps src
        union = []
        for src in ("towers", "big_towers", "armories"):
            union.extend(out.get(src, []))
        out["possible_xp"] = union

        return out

    def _hidden_key(self, tkey: str, pt: dict) -> str:
        """
        Returns a stable id for a POI that can be stored in config.
        For possible_xp we include src so hiding only affects possible_xp entries.
        For other categories we use x:y (integers) since data is 4096 grid.
        """
        xi = int(round(float(pt.get("x", 0))))
        yi = int(round(float(pt.get("y", 0))))
        if tkey == "possible_xp":
            src = str(pt.get("src", ""))
            return f"{src}:{xi}:{yi}"
        return f"{xi}:{yi}"

    def _is_hidden(self, tkey: str, pt: dict) -> bool:
        k = self._hidden_key(tkey, pt)
        return k in self.hidden_sets.get(tkey, set())

    def _hide_hovered(self):
        if self.hover is None:
            return
        tkey = self.hover["type"]
        pt = self.hover["pt_ref"]
        hk = self._hidden_key(tkey, pt)
        self.hidden_sets.setdefault(tkey, set()).add(hk)
        self._save()
        self.hover = None
        self.update()

    def _update_hover(self):
        self.hover = None
        if not (self.master and self.visible and self.rect):
            return

        gp = QtGui.QCursor.pos()
        lp = self.mapFromGlobal(gp)
        mx, my = float(lp.x()), float(lp.y())

        pts_by_type = self.cache.get(self.prof, {})
        best = None
        best_d2 = float(self.hover_radius * self.hover_radius)

        for tkey in self.type_order:
            if not self.types.get(tkey, {}).get("enabled", True):
                continue

            for idx, pt in enumerate(pts_by_type.get(tkey, [])):
                if self._is_hidden(tkey, pt):
                    continue

                cx = self.rect.left() + pt["u"] * self.rect.width()
                cy = self.rect.top() + pt["v"] * self.rect.height()
                dx = mx - cx
                dy = my - cy
                d2 = dx * dx + dy * dy
                if d2 <= best_d2:
                    best_d2 = d2
                    best = {
                        "map": self.prof,
                        "type": tkey,
                        "index": idx,
                        "pt_ref": pt
                    }

        self.hover = best

    def _tick_safe(self):
        try:
            self._tick()
        except Exception:
            print("Overlay tick crashed:\n" + traceback.format_exc(), flush=True)

    def _tick(self):
        nb = key(VK_BT)
        if nb and not self.pbt:
            self.master = not self.master
            if not self.master and self.visible:
                self.visible = False
                self.hide()
            self._save()
        self.pbt = nb

        nh = key(VK_H)
        if nh and not self.pH and self.visible:
            self.visible = False
            self.hide()
            self._save()
        self.pH = nh

        if not self.master:
            return

        nt = key(VK_TAB)
        if nt and not self.pT:
            self.visible = not self.visible
            (self.show if self.visible else self.hide)()
            if self.visible:
                topmost(int(self.winId()))
            self._save()
        self.pT = nt

        if self.visible and self.num_sw:
            if key(VK1): self.switch(MAPS[0])
            elif key(VK2): self.switch(MAPS[1])
            elif key(VK3): self.switch(MAPS[2])
            elif key(VK4): self.switch(MAPS[3])

        if self.visible:
            self._update_hover()

        # Ctrl + Alt + Shift + Delete to hide hovered POI
        hide_now = key(VK_DELETE) and key(VK_CONTROL) and key(VK_MENU) and key(VK_SHIFT)
        if hide_now and not self.pHide:
            self._hide_hovered()
        self.pHide = hide_now

        self.update()

    def paintEvent(self, _):
        if not (self.master and self.visible and self.rect):
            return

        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)

        pts_by_type = self.cache.get(self.prof, {})

        for tkey in self.type_order:
            if not self.types.get(tkey, {}).get("enabled", True):
                continue

            fill = rgb2q(self.types[tkey].get("color"), self.type_specs[tkey]["default_fill"])
            border = self.type_specs[tkey]["border"]

            base_rpx = int(self.type_specs[tkey]["radius_px"])
            scaled = int(round(base_rpx * float(self.global_scale)))
            if scaled < 1: scaled = 1
            if scaled > 40: scaled = 40

            p.setPen(QtGui.QPen(border, 2))
            p.setBrush(fill)

            for pt in pts_by_type.get(tkey, []):
                if self._is_hidden(tkey, pt):
                    continue
                p.drawEllipse(
                    QtCore.QPointF(
                        self.rect.left() + pt["u"] * self.rect.width(),
                        self.rect.top() + pt["v"] * self.rect.height()
                    ),
                    scaled, scaled
                )

        # Map label
        m = 20
        txt = self.prof
        f = p.font()
        f.setBold(True)
        p.setFont(f)
        fm = QtGui.QFontMetrics(f)
        tw, th = fm.horizontalAdvance(txt), fm.height()
        r = QtCore.QRectF(self.width() - m - tw - 16, m, tw + 16, th + 10)
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(QtGui.QColor(0, 0, 0, 150))
        p.drawRoundedRect(r, 8, 8)
        p.setPen(QtGui.QPen(QtGui.QColor(230, 230, 230), 1))
        p.drawText(r.adjusted(8, 7, -8, -4), QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter, txt)
        p.end()

if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    QtWidgets.QApplication.setStyle("Fusion")

    pal = app.palette()
    for role, color in [
        (QtGui.QPalette.Window, QtGui.QColor(30, 31, 34)),
        (QtGui.QPalette.WindowText, QtGui.QColor(230, 230, 230)),
        (QtGui.QPalette.Base, QtGui.QColor(43, 45, 48)),
        (QtGui.QPalette.AlternateBase, QtGui.QColor(36, 38, 41)),
        (QtGui.QPalette.Text, QtGui.QColor(230, 230, 230)),
        (QtGui.QPalette.Button, QtGui.QColor(43, 45, 48)),
        (QtGui.QPalette.ButtonText, QtGui.QColor(230, 230, 230)),
        (QtGui.QPalette.Highlight, QtGui.QColor(90, 120, 200)),
        (QtGui.QPalette.HighlightedText, QtGui.QColor(255, 255, 255)),
    ]:
        pal.setColor(role, color)
    app.setPalette(pal)

    if ICON:
        app.setWindowIcon(QtGui.QIcon(ICON))

    try:
        w = Overlay()
    except Exception as e:
        QtWidgets.QMessageBox.critical(None, "HuntOverlay error", str(e))
        sys.exit(1)

    sys.exit(app.exec())
