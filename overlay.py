# -*- coding: utf-8 -*-
"""可标定覆盖层：透明 / 鼠标穿透 / 置顶，自动跟随游戏窗口

踩过的坑（都是实测出来的，别改回去）：
  ★ 不要在窗口显示前调用 winfo_id()/GetAncestor —— 会导致 Tk 的抠色失效，
    窗口变成「全透明但还挡鼠标」。
  ★ 不要设 -alpha —— 它会覆盖 -transparentcolor 的抠色，同样全透明。
  ★ 标定时要走【绝对坐标】，不能用「游戏窗口 + 相对偏移」，
    否则游戏窗口找不到时拖动会被拽回默认位置。
"""

import ctypes
import json
import os
import tkinter as tk
from ctypes import wintypes

import keys as K
from paths import data_file

# ---------------- Win32 ----------------
user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW = 0x00000080
GA_ROOT = 2
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

HWND_TOPMOST = -1
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010
SWP_NOOWNERZORDER = 0x0200

TRANSPARENT_COLOR = "#010203"
DEFAULT_EXE = "dwrg.exe"

# 配色
C_WHITE = "#EDEDED"
C_BLACK = "#1C1C1C"
C_NEXT = "#FFD166"
C_NOW = "#00E5A0"
C_WRONG = "#FF5C5C"
C_BORDER = "#00A3FF"
TXT_DARK = "#1A1A1A"
TXT_LIGHT = "#F2F2F2"


def _is_light(hex_color):
    r = int(hex_color[1:3], 16)
    g = int(hex_color[3:5], 16)
    b = int(hex_color[5:7], 16)
    return (r * 299 + g * 587 + b * 114) / 1000 > 140


# ---------------- 窗口查找 ----------------
def _pid_of(hwnd):
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def _exe_of(pid):
    h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return None
    try:
        buf = ctypes.create_unicode_buffer(1024)
        size = wintypes.DWORD(1024)
        if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            return os.path.basename(buf.value)
    finally:
        kernel32.CloseHandle(h)
    return None


def find_game_window(exe_name=DEFAULT_EXE):
    found = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def cb(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True
        name = _exe_of(_pid_of(hwnd))
        if name and name.lower() == exe_name.lower():
            found.append(hwnd)
        return True

    user32.EnumWindows(cb, 0)
    return found[0] if found else 0


def window_rect(hwnd):
    r = wintypes.RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(r)):
        return None
    return r.left, r.top, r.right - r.left, r.bottom - r.top


def game_rect(exe_name=DEFAULT_EXE):
    """返回游戏窗口矩形；窗口不存在 / 最小化 / 坐标异常时返回 None"""
    hwnd = find_game_window(exe_name)
    if not hwnd or user32.IsIconic(hwnd):
        return None
    r = window_rect(hwnd)
    if not r or r[0] < -10000 or r[1] < -10000:
        return None
    return r


def set_click_through(hwnd, on):
    """鼠标穿透。样式没变化就不写，避免反复 SetWindowLong 冲掉分层属性。"""
    if not hwnd:
        return
    style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    want = style | WS_EX_LAYERED | WS_EX_TOOLWINDOW
    if on:
        want |= WS_EX_TRANSPARENT
    else:
        want &= ~WS_EX_TRANSPARENT
    if want != style:
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, want)


def force_topmost(hwnd):
    """周期性重新置顶：光靠 Tk 的 -topmost 抢不过游戏"""
    if not hwnd:
        return
    try:
        user32.SetWindowPos(wintypes.HWND(hwnd), wintypes.HWND(HWND_TOPMOST),
                            0, 0, 0, 0,
                            SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE
                            | SWP_NOOWNERZORDER)
    except Exception:
        pass


# ---------------- 覆盖层 ----------------
class PianoOverlay:
    def __init__(self, parent=None, config_path=None):
        self.config_path = config_path or data_file("calib.json")
        self.rel_x, self.rel_y = 0, 0          # 相对游戏窗口
        self.abs_x, self.abs_y = None, None    # 游戏不在时的绝对位置
        self.w, self.h = 720, 240
        self.exe_name = DEFAULT_EXE
        self.calibrating = False
        self.visible = True            # 覆盖层显示开关
        self.remap_mode = False        # 改键模式
        self.remap_midi = None         # 选中的音（等用户按新键）
        self.remap_key = None          # 该音当前绑的键
        self._drag = None
        self._calib_abs = None
        self._highlight = set()
        self._preview = set()
        self._wrong = set()
        self._game_hwnd = 0
        self._last_pos = None
        self.load()

        self.root = tk.Tk() if parent is None else tk.Toplevel(parent)
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.configure(bg=TRANSPARENT_COLOR)
        self.root.attributes("-transparentcolor", TRANSPARENT_COLOR)
        # ★ win_hwnd 延迟到窗口显示后再取（见 _follow）
        self.win_hwnd = 0

        self.canvas = tk.Canvas(self.root, bg=TRANSPARENT_COLOR,
                                highlightthickness=0, bd=0)
        self.canvas.pack(fill="both", expand=True)

        # 只绑在 Toplevel 上：Canvas 是它的子控件，事件会冒泡上来。
        # 两处都绑会让一次移动触发两遍
        self.root.bind("<Button-1>", self._on_press)
        self.root.bind("<B1-Motion>", self._on_drag)
        self.root.bind("<ButtonRelease-1>", self._on_release)

        self._apply_geometry(force=True)
        self.redraw()
        self.root.after(60, self._follow)

    # ---------- 标定存取 ----------
    def load(self):
        if not os.path.exists(self.config_path):
            return
        try:
            with open(self.config_path, encoding="utf-8") as f:
                d = json.load(f)
            self.rel_x = d.get("rel_x", self.rel_x)
            self.rel_y = d.get("rel_y", self.rel_y)
            self.abs_x = d.get("abs_x", self.abs_x)
            self.abs_y = d.get("abs_y", self.abs_y)
            self.w = d.get("w", self.w)
            self.h = d.get("h", self.h)
            self.exe_name = d.get("exe", self.exe_name)
        except Exception:
            pass

    def save(self):
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump({"exe": self.exe_name,
                           "rel_x": self.rel_x, "rel_y": self.rel_y,
                           "abs_x": self.abs_x, "abs_y": self.abs_y,
                           "w": self.w, "h": self.h},
                          f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    # ---------- 对外微调接口（主窗口面板用） ----------
    def nudge(self, dx, dy):
        if self.abs_x is None:
            self.abs_x, self.abs_y = self._target_pos()
        self.abs_x += dx
        self.abs_y += dy
        self.rel_x += dx
        self.rel_y += dy
        self._apply_geometry(force=True)

    def set_pos(self, x, y):
        self.abs_x, self.abs_y = x, y
        r = game_rect(self.exe_name)
        if r:
            self.rel_x, self.rel_y = x - r[0], y - r[1]
        self._last_pos = None
        self._apply_geometry(force=True)
        self.save()

    def set_size(self, w, h):
        self.w, self.h = max(80, int(w)), max(40, int(h))
        self._apply_geometry(force=True)
        self.redraw()
        self.save()

    def current_pos(self):
        # 优先用算出来的位置；窗口还没真正定位时 winfo_x() 是垃圾值
        return self._last_pos or (self.root.winfo_x(), self.root.winfo_y())

    # ---------- 高亮 ----------
    def set_highlight(self, now=None, preview=None, wrong=None):
        self._highlight = set(now or ())
        self._preview = set(preview or ())
        self._wrong = set(wrong or ())
        self.redraw()

    # ---------- 定位 ----------
    def _target_pos(self):
        self._game_hwnd = find_game_window(self.exe_name)
        if self.calibrating and self._calib_abs:
            return self._calib_abs[0], self._calib_abs[1]
        r = game_rect(self.exe_name)
        if r:
            return r[0] + self.rel_x, r[1] + self.rel_y
        if self.abs_x is not None:
            return self.abs_x, self.abs_y
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        return max(0, (sw - self.w) // 2), max(0, sh - self.h - 120)

    def _apply_geometry(self, force=False):
        x, y = self._target_pos()
        # 越界保护：配置文件被写坏、或游戏窗口在别的显示器时，
        # 夹回主屏可见范围，免得覆盖层跑到屏幕外看不见
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        x = max(-self.w + 80, min(x, sw - 80))
        y = max(0, min(y, sh - 40))
        if not force and (x, y) == self._last_pos:
            return
        self._last_pos = (x, y)
        self.root.geometry(f"{self.w}x{self.h}+{x}+{y}")
        self.root.attributes("-transparentcolor", TRANSPARENT_COLOR)

    def _follow(self):
        if self.visible and self.root.winfo_viewable():
            if not self.win_hwnd:
                self.win_hwnd = user32.GetAncestor(self.root.winfo_id(), GA_ROOT)
            set_click_through(self.win_hwnd,
                              not (self.calibrating or self.remap_mode))
            force_topmost(self.win_hwnd)          # ★ 反复抢置顶
            if not self.calibrating:
                self._apply_geometry()
        self.root.after(60, self._follow)

    # ---------- 显示 / 隐藏 ----------
    def set_visible(self, on):
        """显示或隐藏覆盖层（隐藏后完全不占屏幕，也不用关软件）"""
        self.visible = bool(on)
        if self.visible:
            self.root.deiconify()
            if not self.win_hwnd:
                self.win_hwnd = user32.GetAncestor(self.root.winfo_id(), GA_ROOT)
            set_click_through(self.win_hwnd,
                              not (self.calibrating or self.remap_mode))
            self._last_pos = None
            self._apply_geometry(force=True)
        else:
            self.root.withdraw()
        return self.visible

    def toggle_visible(self):
        return self.set_visible(not self.visible)

    # ---------- 改键模式 ----------
    def cell_at(self, x, y):
        """屏幕坐标 -> (显示行, 列, 该位置的 MIDI 音)"""
        rows, cols = 3, K.COLS          # 完整版 12 列 / 基础版 7 列
        gap = 2 if not self.calibrating else 3
        cw = (self.w - gap * (cols + 1)) / cols
        ch = (self.h - gap * (rows + 1)) / rows
        if cw <= 1 or ch <= 1:
            return None
        col = int((x - gap) // (cw + gap))
        row = int((y - gap) // (ch + gap))
        if not (0 <= col < cols and 0 <= row < rows):
            return None
        display_rows = [K.ROWS[2], K.ROWS[1], K.ROWS[0]]
        key = display_rows[row][col]
        return row, col, K.KEY_TO_MIDI.get(key)

    def toggle_remap(self):
        if not self.win_hwnd:
            self.win_hwnd = user32.GetAncestor(self.root.winfo_id(), GA_ROOT)
        self.remap_mode = not self.remap_mode
        if not self.remap_mode:
            self.remap_midi = self.remap_key = None
        self.redraw()
        return self.remap_mode

    def pick_for_remap(self, x, y):
        """点中某个琴键 -> 记下它，等用户按新键"""
        cell = self.cell_at(x, y)
        if not cell:
            return None
        _, _, midi = cell
        self.remap_midi = midi
        self.remap_key = K.MIDI_TO_KEY.get(midi)
        self.redraw()
        return self.remap_midi

    def apply_remap(self, new_key):
        """把选中的音改绑到 new_key，返回 (音名, 旧键, 新键, 被交换的音)"""
        if self.remap_midi is None:
            return None
        midi = self.remap_midi
        old = K.MIDI_TO_KEY.get(midi)
        swapped, other = K.remap(midi, new_key)
        self.remap_midi = self.remap_key = None
        self.redraw()
        return (K.note_name(midi), old, new_key, other)

    # ---------- 绘制 ----------
    def redraw(self):
        c = self.canvas
        c.delete("all")
        if self.w < 40 or self.h < 20:
            return
        rows, cols = 3, K.COLS          # 完整版 12 列 / 基础版 7 列
        gap = 2 if not self.calibrating else 3
        cw = (self.w - gap * (cols + 1)) / cols
        ch = (self.h - gap * (rows + 1)) / rows
        if cw <= 1 or ch <= 1:
            return

        display_rows = [K.ROWS[2], K.ROWS[1], K.ROWS[0]]
        for r, row_keys in enumerate(display_rows):
            for col, key in enumerate(row_keys):
                x0 = gap + col * (cw + gap)
                y0 = gap + r * (ch + gap)
                x1, y1 = x0 + cw, y0 + ch

                if self.remap_mode and key == self.remap_key:
                    fill, outline = "#FF00FF", "#FFFFFF"
                elif key in self._wrong:
                    fill, outline = C_WRONG, "#FFFFFF"
                elif key in self._highlight:
                    fill, outline = C_NOW, "#FFFFFF"
                elif key in self._preview:
                    fill, outline = C_NEXT, "#FFFFFF"
                elif key in K.BLACK_KEY_SET:
                    fill, outline = C_BLACK, "#000000"
                else:
                    fill, outline = C_WHITE, "#9AA0A6"

                wdt = 3 if key in (self._highlight | self._wrong) else 1
                c.create_rectangle(x0, y0, x1, y1, fill=fill,
                                   outline=outline, width=wdt)
                if ch > 16 and cw > 14:
                    c.create_text((x0 + x1) / 2, (y0 + y1) / 2, text=key,
                                  fill=TXT_DARK if _is_light(fill) else TXT_LIGHT,
                                  font=("Consolas", max(8, int(ch * 0.34)), "bold"))

        c.create_rectangle(1, 1, self.w - 1, self.h - 1,
                           outline=C_BORDER, width=2)
        if self.calibrating:
            c.create_rectangle(3, 3, self.w - 3, self.h - 3,
                               outline="#FF00FF", width=3, dash=(6, 4))
            c.create_text(self.w / 2, 16,
                          text="标定中：拖动移动 · 拖右下角缩放 · F7 保存",
                          fill="#FF00FF", font=("Microsoft YaHei", 11, "bold"))
        elif self.remap_mode:
            c.create_rectangle(3, 3, self.w - 3, self.h - 3,
                               outline="#FF00FF", width=3, dash=(6, 4))
            hint = ("改键：先点一个琴键，再按你要绑的新键  (F6 退出)"
                    if self.remap_midi is None else
                    f"已选中 {K.note_name(self.remap_midi)}（当前 {self.remap_key}）"
                    f" —— 现在按新键  (F6 退出)")
            c.create_text(self.w / 2, 16, text=hint,
                          fill="#FF00FF", font=("Microsoft YaHei", 11, "bold"))

    # ---------- 标定 ----------
    def toggle_calibration(self):
        if not self.win_hwnd:
            self.win_hwnd = user32.GetAncestor(self.root.winfo_id(), GA_ROOT)
        self.calibrating = not self.calibrating
        if self.calibrating:
            # 进入标定：锁住当前绝对位置，之后拖多少就是多少
            self._calib_abs = [self.root.winfo_x(), self.root.winfo_y()]
            set_click_through(self.win_hwnd, False)
        else:
            self._commit_calibration()
            set_click_through(self.win_hwnd, True)
        self.redraw()
        return self.calibrating

    def _commit_calibration(self):
        if self._calib_abs:
            ax, ay = self._calib_abs
            self.abs_x, self.abs_y = ax, ay
            r = game_rect(self.exe_name)
            if r:
                self.rel_x, self.rel_y = ax - r[0], ay - r[1]
        self._calib_abs = None
        self._last_pos = None
        self.save()

    def _clamp_pos(self, x, y):
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        return (max(-self.w + 80, min(int(x), sw - 80)),
                max(0, min(int(y), sh - 40)))

    def _on_press(self, e):
        if self.remap_mode:                 # 改键模式：点琴键来选中
            self.pick_for_remap(e.x, e.y)
            return
        if not self.calibrating:
            return
        if not self._calib_abs:
            self._calib_abs = [self.root.winfo_x(), self.root.winfo_y()]
        near_corner = (e.x > self.w - 30 and e.y > self.h - 30)
        # ★ 记下【按下那一刻】的屏幕绝对坐标和窗口位置，
        #   之后每次移动都从这组基准重算，绝不在上一次结果上累加，
        #   否则窗口一动，鼠标相对坐标就变，位移会滚雪球 → 飞走
        self._drag = {
            "mode": "resize" if near_corner else "move",
            "mx": e.x_root, "my": e.y_root,
            "wx": self._calib_abs[0], "wy": self._calib_abs[1],
            "w": self.w, "h": self.h,
        }

    def _on_drag(self, e):
        if not self.calibrating or not self._drag or not self._calib_abs:
            return
        d = self._drag
        dx = e.x_root - d["mx"]
        dy = e.y_root - d["my"]

        if d["mode"] == "move":
            x, y = self._clamp_pos(d["wx"] + dx, d["wy"] + dy)
            self._calib_abs = [x, y]
            self.root.geometry(f"{self.w}x{self.h}+{x}+{y}")
        else:
            self.w = max(120, d["w"] + dx)
            self.h = max(60, d["h"] + dy)
            x, y = self._calib_abs
            self.root.geometry(f"{self.w}x{self.h}+{x}+{y}")
        self.redraw()

    def _on_release(self, _):
        self._drag = None

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    ov = PianoOverlay()
    ov.set_highlight(now={"Z", "X"}, preview={"C"})
    ov.run()
