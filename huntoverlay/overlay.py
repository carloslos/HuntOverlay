# Main Overlay window and the run() entry point.
#
# Core behavior
#   Loads data.json and poiData.json from %LOCALAPPDATA%\HuntOverlay
#   Applies a screen rectangle per map based on detected aspect ratio
#   Draws POIs in that rectangle using normalized coordinates derived from a 4096x4096 grid
#
# Hotkeys (all configurable via GUI). Default:
#   toggle_master        ` (backtick)
#   toggle_overlay       Tab
#   hide_overlay         H
#   map_1..map_4         1 2 3 4
#   detect_map           O
import sys, os, traceback

from PySide6 import QtCore, QtGui, QtWidgets

from .constants import (
    MAPS,
    CONFIG_VERSION,
    DEFAULT_HIDDEN_POSSIBLE_XP,
    VK_TAB,
    VK_CONTROL,
    VK_MENU,
)
from .win32 import key, topmost, click_through, foreground_process_name
from .paths import ICON, DATA_PATH, STYLE_PATH, CONFIG_PATH, udir, load_json, save_json
from .helpers import (
    q2rgb,
    rgb2q,
    screenWH,
    detect_aspect_label,
    vk_to_label,
    rotate90cw_norm,
    detect_data_format,
    get_map_block,
    get_category_list,
    find_style_by_category,
    qcolor_from_any,
    overlay_radius_from_spec,
)
from .config import (
    default_keybinds,
    default_rect_ratio_16_9,
    default_rect_ratio_by_aspect,
    build_default_config,
    load_or_replace_config,
)
from .widgets import KeyCaptureDialog
from .panel import Panel
from .mapdetect import MapMatcher, MATCH_THRESHOLD


class Overlay(QtWidgets.QWidget):
    def __init__(self):
        super().__init__(None, QtCore.Qt.FramelessWindowHint | QtCore.Qt.WindowStaysOnTopHint | QtCore.Qt.Tool)

        self.tab_blocked = False

        self.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)
        self.setAttribute(QtCore.Qt.WA_ShowWithoutActivating, True)
        self.setFocusPolicy(QtCore.Qt.NoFocus)
        self.setMouseTracking(False)

        if ICON:
            QtWidgets.QApplication.instance().setWindowIcon(QtGui.QIcon(ICON))
            self.setWindowIcon(QtGui.QIcon(ICON))

        if not os.path.isfile(DATA_PATH):
            raise RuntimeError(f"Missing data.json in {udir()}")
        if not os.path.isfile(STYLE_PATH):
            raise RuntimeError(f"Missing poiData.json in {udir()}")

        self.game_data = load_json(DATA_PATH)
        self.fmt = detect_data_format(self.game_data)
        if self.fmt == "unknown":
            raise RuntimeError("Unrecognized data.json format")

        self.poi_style = load_json(STYLE_PATH)

        # Map name lookup keyed by data.json index, used by the image matcher.
        # Reference images live in maps/<index>.webp.
        index_to_name = {}
        for m in self.game_data:
            if isinstance(m, dict) and "i" in m and "n" in m:
                try:
                    index_to_name[int(m["i"])] = str(m["n"])
                except:
                    pass
        if not index_to_name:
            # Fall back to MAPS order with 1 based image indices.
            index_to_name = {i + 1: MAPS[i] for i in range(len(MAPS))}
        self.map_matcher = MapMatcher(index_to_name)

        # Order of types controls draw order and GUI ordering.
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

        W, H = screenWH()
        self.aspect = detect_aspect_label(W, H)

        self.data = load_or_replace_config()
        self._load_state_from_config(self.data)

        # Build the panel window.
        binds_label_map = {
            "toggle_master": "Toggle master",
            "toggle_overlay": "Toggle overlay",
            "hide_overlay": "Hide overlay",
            "detect_map": "Auto-detect map",
            "map_1": "Map 1  Stillwater",
            "map_2": "Map 2  Lawson",
            "map_3": "Map 3  DeSalle",
            "map_4": "Map 4  Mammon",
        }
        binds_value_map = {a: self._bind_label(a) for a in binds_label_map}
        help_text = self._build_help_text()
        self.panel = Panel(self.type_order, self.type_specs, self.global_scale, help_text, binds_label_map, binds_value_map, self.minimize_to_tray)
        if ICON:
            self.panel.setWindowIcon(QtGui.QIcon(ICON))

        # Wire GUI events.
        self.panel.tnums.connect(self._set_num_switch)
        self.panel.mapSel.connect(self.switch)
        self.panel.resetColors.connect(self._reset_colors)
        self.panel.typeToggled.connect(self._type_toggle)
        self.panel.typeColor.connect(self._type_color)
        self.panel.scaleChanged.connect(self._scale_changed)
        self.panel.requestBindEdit.connect(self._edit_keybind)
        self.panel.resetConfig.connect(self._reset_config_to_defaults)
        self.panel.minimizeToTrayChanged.connect(self._set_minimize_to_tray)

        # Seed GUI with current state.
        self.panel.chk_nums.setChecked(self.num_sw)
        self.panel.setMap(self.prof)
        for k in self.type_order:
            self.panel.setTypeState(k, self.types[k]["enabled"], rgb2q(self.types[k]["color"], self.type_specs[k]["default_fill"]))

        self.panel.move(40, 40)
        self.panel.show()

        # Start minimized to tray if enabled, silently
        if self.minimize_to_tray:
            QtCore.QTimer.singleShot(0, lambda: self._hide_panel_to_tray(silent=True))

        # System tray setup.
        self.tray = None
        self._ensure_tray()

        # Move to main monitor
        self._move_to_primary_screen()

        # Make overlay click through and topmost.
        click_through(int(self.winId()))
        (self.show if self.visible and self.master else self.hide)()
        topmost(int(self.winId()))

        # Edge detection for hotkeys so they do not toggle repeatedly while held.
        self.p_toggle_master = False
        self.p_hide = False
        self.p_toggle_overlay = False
        self.p_detect_map = False

        # Cache computed point lists per map to avoid rebuilding every frame.
        self.cache = {}
        self._rebuild_all_caches()

        # Save once at the end to ensure config contains any missing keys we added.
        self._save()

        # Timer tick drives input polling.
        self.t = QtCore.QTimer(self)
        self.t.timeout.connect(self._tick_safe)
        self.t.start(16)

        # Minimize to tray needs access to the panel state changes.
        self.panel.installEventFilter(self)

    def _move_to_primary_screen(self):
        screen = QtGui.QGuiApplication.primaryScreen()
        geom = screen.geometry()

        self.setGeometry(geom)

    def eventFilter(self, obj, ev):
        if obj is self.panel:
            if ev.type() == QtCore.QEvent.WindowStateChange:
                if self.minimize_to_tray and self.panel.isMinimized():
                    self._hide_panel_to_tray()
                    return True
        return super().eventFilter(obj, ev)

    def _ensure_tray(self):
        """
        Creates tray icon and menu once.
        Tray is only used when minimize_to_tray is enabled, but we keep it available.
        """
        if self.tray is not None:
            return

        self.tray = QtWidgets.QSystemTrayIcon(self)
        if ICON:
            self.tray.setIcon(QtGui.QIcon(ICON))
        else:
            self.tray.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_ComputerIcon))

        menu = QtWidgets.QMenu()
        act_restore = QtGui.QAction("Restore panel", menu)
        act_quit = QtGui.QAction("Quit", menu)
        menu.addAction(act_restore)
        menu.addSeparator()
        menu.addAction(act_quit)

        act_restore.triggered.connect(self._restore_panel_from_tray)
        act_quit.triggered.connect(QtWidgets.QApplication.quit)

        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._tray_activated)
        self.tray.show()

    def _tray_activated(self, reason):
        if reason == QtWidgets.QSystemTrayIcon.Trigger:
            self._restore_panel_from_tray()

    def _hide_panel_to_tray(self, silent=False):
        self._ensure_tray()
        self.panel.hide()
        self.panel.setWindowState(QtCore.Qt.WindowNoState)
        if not silent:
            try:
                self.tray.showMessage("HuntOverlay", "Panel minimized to tray", QtWidgets.QSystemTrayIcon.Information, 1500)
            except:
                pass

    def _restore_panel_from_tray(self):
        self.panel.showNormal()
        self.panel.raise_()
        self.panel.activateWindow()

    def _set_minimize_to_tray(self, v: bool):
        self.minimize_to_tray = bool(v)
        self._save()

    def _build_type_specs(self):
        specs = {}

        # possible_xp is a special union category.
        specs["possible_xp"] = {
            "label": "Possible XP Location",
            "border": QtGui.QColor("#FFFFFF"),
            "default_fill": QtGui.QColor("#FFD34D"),
            "radius_px": 6,
        }

        def add_from_style(category, fallback_label):
            spec = find_style_by_category(self.poi_style, category) or {}
            label = spec.get("label", fallback_label)
            border = qcolor_from_any(spec.get("borderColor", "#555555"), QtGui.QColor("#555555"))
            fill = qcolor_from_any(spec.get("fillColor", "#B4B4B4"), QtGui.QColor("#B4B4B4"))
            radius_px = overlay_radius_from_spec(spec.get("radius", 12))
            specs[category] = {"label": str(label), "border": border, "default_fill": fill, "radius_px": radius_px}

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

    def _normalize_keybinds(self, binds: dict) -> dict:
        """
        Merges config keybinds with defaults and forces correct types.
        Unknown keys are ignored.
        """
        base = default_keybinds()
        merged = {k: dict(v) for k, v in base.items()}

        if isinstance(binds, dict):
            for k, v in binds.items():
                if k not in merged:
                    continue
                if not isinstance(v, dict):
                    continue
                for kk, vv in v.items():
                    merged[k][kk] = vv

        for k, v in merged.items():
            try:
                v["vk"] = int(v.get("vk", base[k]["vk"]))
            except:
                v["vk"] = int(base[k]["vk"])

        return merged

    def _load_state_from_config(self, d: dict):
        """
        Loads stateful runtime fields from the config dict.
        This is used at startup and after a full reset to default config.
        """
        st = d.get("settings", {}) if isinstance(d, dict) else {}
        if not isinstance(st, dict):
            st = {}

        self.num_sw = bool(st.get("enable_num_switch", True))
        sel = st.get("selected_map", MAPS[0])
        self.prof = sel if sel in MAPS else MAPS[0]
        self.visible = bool(st.get("visible_overlay", False))
        self.master = bool(st.get("master_on", True))

        self.global_scale = float(st.get("global_scale", 1.00))
        if self.global_scale < 0.10: self.global_scale = 0.10
        if self.global_scale > 5.00: self.global_scale = 5.00

        self.minimize_to_tray = bool(st.get("minimize_to_tray", False))

        self.binds = self._normalize_keybinds(st.get("keybinds", {}))

        # Per type settings.
        self.types = st.get("types", {})
        if not isinstance(self.types, dict):
            self.types = {}
        for k in self.type_order:
            if k not in self.types or not isinstance(self.types.get(k), dict):
                self.types[k] = {"enabled": True, "color": q2rgb(self.type_specs[k]["default_fill"])}
            if "enabled" not in self.types[k]:
                self.types[k]["enabled"] = True
            if "color" not in self.types[k]:
                self.types[k]["color"] = q2rgb(self.type_specs[k]["default_fill"])

        # Hidden lists.
        self.hidden = st.get("hidden", {})
        if not isinstance(self.hidden, dict):
            self.hidden = {}
        for k in self.type_order:
            if k not in self.hidden or not isinstance(self.hidden.get(k), list):
                self.hidden[k] = []

        # Ensure default hidden possible_xp entries exist.
        px = self.hidden.get("possible_xp", [])
        if not isinstance(px, list):
            px = []
        for s in DEFAULT_HIDDEN_POSSIBLE_XP:
            if s not in px:
                px.append(s)
        self.hidden["possible_xp"] = px

        self.hidden_sets = {k: set(self.hidden.get(k, [])) for k in self.type_order}

        # Apply aspect aware rect.
        self.rect = None
        self._apply_rect()

    def _hunt_in_focus(self) -> bool:
        """
        True when the foreground window belongs to the Hunt game process.
        Only called on a key-press edge, so the cost is negligible.
        """
        return foreground_process_name() == "huntgame"

    def _bind_pressed(self, name: str) -> bool:
        b = self.binds.get(name, {})
        try:
            vk = int(b.get("vk", 0))
        except:
            return False
        if vk == 0:
            return False

        # Suppress Tab when used with Alt, Ctrl, or Shift
        if vk == VK_TAB:
            modifier_down = key(VK_MENU) or key(VK_CONTROL)

            if modifier_down:
                # Tab pressed with a modifier → block until Tab is released
                self.tab_blocked = True
                return False

            if self.tab_blocked:
                # Modifier was held when Tab was first pressed
                # Keep blocking until Tab is released
                if not key(VK_TAB):
                    self.tab_blocked = False
                return False

        return key(vk)

    def _bind_label(self, name: str) -> str:
        b = self.binds.get(name, {})
        try:
            vk = int(b.get("vk", 0))
        except:
            vk = 0

        return vk_to_label(vk)

    def _build_help_text(self) -> str:
        return (
            f"Detected aspect: {self.aspect}\n"
            f"Config version: {self.data.get('version','?')}\n"
            "Files are stored at:\n"
            "%LOCALAPPDATA%\\HuntOverlay\n"
        )

    def _save(self):
        st = self.data.setdefault("settings", {})
        self.data["version"] = CONFIG_VERSION

        st["enable_num_switch"] = self.num_sw
        st["selected_map"] = self.prof
        st["visible_overlay"] = self.visible
        st["master_on"] = self.master
        st["global_scale"] = float(self.global_scale)
        st["minimize_to_tray"] = bool(self.minimize_to_tray)

        st["types"] = self.types
        st["keybinds"] = self.binds

        # Persist hidden sets.
        st["hidden"] = {k: sorted(list(self.hidden_sets.get(k, set()))) for k in self.type_order}

        save_json(CONFIG_PATH, self.data)

    def _apply_rect(self):
        """
        Uses detected aspect label to select the correct ratio for the current map.
        """
        pm = self.data.get("profiles", {}).get(self.prof, {})
        rra = pm.get("rect_ratio_by_aspect", {})
        rr = rra.get(self.aspect, None)
        if not isinstance(rr, dict):
            rr = default_rect_ratio_by_aspect().get(self.aspect, default_rect_ratio_16_9())

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

    def _reset_config_to_defaults(self):
        """
        Overwrites config.json with fresh defaults and reloads state immediately.
        This does not touch data.json or poiData.json.
        """
        fresh = build_default_config()
        save_json(CONFIG_PATH, fresh)

        self.data = load_or_replace_config()
        self._load_state_from_config(self.data)

        # Re apply map selection and rectangle because the selected map may have changed.
        self._apply_rect()

        # Push state back into GUI widgets.
        self.panel.chk_nums.setChecked(self.num_sw)
        self.panel.chk_tray.setChecked(self.minimize_to_tray)
        self.panel.scale_box.setValue(float(self.global_scale))
        self.panel.setMap(self.prof)

        for k in self.type_order:
            self.panel.setTypeState(k, self.types[k]["enabled"], rgb2q(self.types[k]["color"], self.type_specs[k]["default_fill"]))

        # Refresh help text because keybinds and aspect might differ.
        self.panel.setHelpText(self._build_help_text())
        for a in self.panel.kb_rows:
            self.panel.setBindLabel(a, self._bind_label(a))

        # Apply overlay visibility state.
        (self.show if self.visible and self.master else self.hide)()
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

        union = []
        for src in ("towers", "big_towers", "armories"):
            union.extend(out.get(src, []))
        out["possible_xp"] = union

        return out

    def _hidden_key(self, tkey: str, pt: dict) -> str:
        """
        Stable hide id.
        For possible_xp we include src so hiding only affects possible_xp entries.
        For other categories use xi:yi.
        """
        xi = int(round(float(pt.get("x", 0))))
        yi = int(round(float(pt.get("y", 0))))
        if tkey == "possible_xp":
            src = str(pt.get("src", ""))
            return f"{src}:{xi}:{yi}"
        return f"{xi}:{yi}"

    def _is_hidden(self, tkey: str, pt: dict) -> bool:
        return self._hidden_key(tkey, pt) in self.hidden_sets.get(tkey, set())

    def _tick_safe(self):
        try:
            self._tick()
        except Exception:
            print("Overlay tick crashed:\n" + traceback.format_exc(), flush=True)

    def _tick(self):
        nm = self._bind_pressed("toggle_master")
        if nm and not self.p_toggle_master:
            self.master = not self.master
            if not self.master and self.visible:
                self.visible = False
                self.hide()
            self._save()
        self.p_toggle_master = nm

        nh = self._bind_pressed("hide_overlay")
        if nh and not self.p_hide and self.visible and self._hunt_in_focus():
            self.visible = False
            self.hide()
            self._save()
        self.p_hide = nh

        if not self.master:
            return

        nt = self._bind_pressed("toggle_overlay")
        if nt and not self.p_toggle_overlay and self._hunt_in_focus():
            self.visible = not self.visible
            (self.show if self.visible else self.hide)()
            if self.visible:
                topmost(int(self.winId()))
            self._save()
        self.p_toggle_overlay = nt

        # Map switching uses MAPS order. Since MAPS changed, 2 is Lawson and 3 is DeSalle.
        if self.visible and self.num_sw:
            if self._bind_pressed("map_1"): self.switch(MAPS[0])
            elif self._bind_pressed("map_2"): self.switch(MAPS[1])
            elif self._bind_pressed("map_3"): self.switch(MAPS[2])
            elif self._bind_pressed("map_4"): self.switch(MAPS[3])

        # Auto-detect the current map from the screen.
        nd = self._bind_pressed("detect_map")
        if nd and not self.p_detect_map and self._hunt_in_focus():
            self._detect_and_switch_map()
        self.p_detect_map = nd

        self.update()

    def _grab_map_region(self):
        """
        Captures the on screen pixels under the overlay rectangle.
        The overlay is hidden for the grab so its POI dots do not pollute the image.
        Returns a QImage or None.
        """
        if not self.rect:
            return None
        screen = QtGui.QGuiApplication.primaryScreen()
        if screen is None:
            return None

        g = screen.geometry()
        x = g.left() + self.rect.left()
        y = g.top() + self.rect.top()
        w = self.rect.width()
        h = self.rect.height()

        was_visible = self.isVisible()
        if was_visible:
            self.hide()
            QtWidgets.QApplication.processEvents()

        pix = screen.grabWindow(0, x, y, w, h)

        if was_visible:
            self.show()
            click_through(int(self.winId()))
            topmost(int(self.winId()))
            QtWidgets.QApplication.processEvents()

        if pix is None or pix.isNull():
            return None
        return pix.toImage()

    def _detect_and_switch_map(self):
        """
        Grabs the map region, matches it against the reference map images and
        switches to the best match. Reports the result via the tray icon.
        """
        if not self.map_matcher.available():
            self._notify("Auto-detect map", "No reference map images found in maps folder")
            return

        region = self._grab_map_region()
        name, score = self.map_matcher.detect(region)
        if not name:
            self._notify("Auto-detect map", "Could not capture the screen")
            return

        if score >= MATCH_THRESHOLD:
            self.switch(name)
            self._notify("Auto-detect map", f"Switched to {name}  (match {score:.2f})")
        else:
            # Low confidence: still switch to the best guess but flag it.
            self.switch(name)
            self._notify("Auto-detect map", f"Best guess {name}  (low confidence {score:.2f})")

    def _notify(self, title: str, message: str):
        if self.tray is not None:
            try:
                self.tray.showMessage(title, message, QtWidgets.QSystemTrayIcon.Information, 1800)
                return
            except:
                pass
        print(f"{title}: {message}", flush=True)

    def _edit_keybind(self, action: str):
        """
        GUI initiated keybind edit.
        Captures the next key press and stores it for the action.
        """
        d = KeyCaptureDialog(action, self.panel)
        if ICON:
            d.setWindowIcon(QtGui.QIcon(ICON))

        if d.exec() != QtWidgets.QDialog.Accepted:
            return

        b = d.result_bind
        if not isinstance(b, dict) or action not in self.binds:
            return

        self.binds[action]["vk"] = int(b.get("vk", self.binds[action]["vk"]))

        self._save()
        self.panel.setBindLabel(action, self._bind_label(action))

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

        # Map label at top right.
        m = 20
        txt = f"{self.prof}  ({self.aspect})"
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


def run():
    app = QtWidgets.QApplication(sys.argv)
    QtWidgets.QApplication.setStyle("Fusion")

    # Consistent dark palette for the panel.
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
