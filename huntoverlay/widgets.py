# Reusable UI widgets and dialogs.
from PySide6 import QtCore, QtGui, QtWidgets

from .constants import VK_ESC, VK_SHIFT, VK_CONTROL, VK_MENU
from .win32 import key
from .paths import ICON


class KeyCaptureDialog(QtWidgets.QDialog):
    """
    Small capture dialog that polls GetAsyncKeyState and records one non modifier key press.
    Ctrl Alt Shift are captured and returned too.
    Esc cancels.
    """
    def __init__(self, action_name: str, p=None):
        super().__init__(p)
        self.setWindowTitle(f"Set keybind: {action_name}")
        self.setModal(True)
        self.setWindowFlags(self.windowFlags() | QtCore.Qt.Tool)
        self.result_bind = None

        v = QtWidgets.QVBoxLayout(self)
        lbl = QtWidgets.QLabel("Press a key now\nCtrl Alt Shift are captured too\nEsc cancels")
        lbl.setAlignment(QtCore.Qt.AlignCenter)
        v.addWidget(lbl)

        self._timer = QtCore.QTimer(self)
        self._timer.timeout.connect(self._poll)
        self._timer.start(10)

        self._prev_down = set()

    def _poll(self):
        if key(VK_ESC):
            self.reject()
            return

        mods = {"ctrl": key(VK_CONTROL), "alt": key(VK_MENU), "shift": key(VK_SHIFT)}

        down = set()
        for vk in range(1, 256):
            if key(vk):
                down.add(vk)

        new_down = [vk for vk in down if vk not in self._prev_down]
        self._prev_down = down

        for vk in new_down:
            if vk in (VK_CONTROL, VK_MENU, VK_SHIFT):
                continue
            self.result_bind = {"vk": int(vk), "ctrl": bool(mods["ctrl"]), "alt": bool(mods["alt"]), "shift": bool(mods["shift"])}
            self.accept()
            return


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
            "QPushButton:hover { background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(255,255,255,50), stop:1 transparent); }"
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
