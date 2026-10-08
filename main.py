# -*- coding: utf-8 -*-
"""第五人格 · 弹琴辅助 V1

  主窗口：粘贴简谱 -> 解析预览 -> 选模式 -> 开始
  覆盖层：贴在游戏琴键上，高亮该按哪个键

热键（全局，游戏在前台也有效）：
  F5  显示 / 隐藏 覆盖层（不想被挡的时候按一下，不用关软件）
  F6  改键模式
  F7  进入/退出 标定模式（拖动对齐覆盖层）
  F8  开始 / 停止
  F9  重来
  Esc 停止（在辅助窗口里）
"""

import queue
import sys
import tkinter as tk
from tkinter import ttk, simpledialog, messagebox

from pynput import keyboard

import keys as K
import library as Lib
import score as S
from engine import SequenceEngine, TimeEngine, Seq
from overlay import PianoOverlay

# ---------------- 按键名映射（用 vk，不受大小写/输入法影响） ----------------
VK_TO_KEY = {}
for _c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
    VK_TO_KEY[ord(_c)] = _c
for _d in "0123456789":
    VK_TO_KEY[ord(_d)] = _d
VK_TO_KEY.update({0xBC: ",", 0xBE: ".", 0xBA: ";", 0xBF: "/",
                  0xDB: "[", 0xBD: "-"})

EVENTS = queue.Queue()


def vk_to_key(vk):
    return VK_TO_KEY.get(vk)


# ---------------- 键盘监听（独立线程 -> 事件丢进队列） ----------------
def on_press(key):
    if key == keyboard.Key.f5:
        EVENTS.put(("hotkey", "f5"))
    elif key == keyboard.Key.f6:
        EVENTS.put(("hotkey", "f6"))
    elif key == keyboard.Key.f7:
        EVENTS.put(("hotkey", "f7"))
    elif key == keyboard.Key.f8:
        EVENTS.put(("hotkey", "f8"))
    elif key == keyboard.Key.f9:
        EVENTS.put(("hotkey", "f9"))
    else:
        vk = getattr(key, "vk", None)
        k = vk_to_key(vk) if vk is not None else None
        if k:
            EVENTS.put(("press", k))


def on_release(key):
    vk = getattr(key, "vk", None)
    k = vk_to_key(vk) if vk is not None else None
    if k:
        EVENTS.put(("release", k))


# ---------------- 主程序 ----------------
DEMO_SHEET = """5
6
1'
2'
|
1'
2'
1'
3
|
2'
1'
1'
2'
|
3'
5'
3'
2'
|
1'
6
5
3
|
3
5
6'
3'
|
2'
2'
1'
3'
|
2'
1'
6
1'
|
3'
2'
1'
6
|
5
3
2
1'
"""


class App:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("第五人格 · 弹琴辅助 V1")
        self.root.geometry("600x880+40+20")
        self.root.attributes("-topmost", True)

        self.steps = []
        self.engine = None
        self.mode = tk.StringVar(value="seq_block")
        self.speed = tk.DoubleVar(value=1.0)
        self.beat_ms = tk.IntVar(value=500)
        self._last_render = None
        self._wrong_flash = 0

        K.load_state()              # 加载版本 + 用户改过的键位
        self._build_ui()
        self.refresh_keymap()

        self.refresh_library()

        self.overlay = PianoOverlay(parent=self.root)
        self.read_overlay()
        self.root.after(500, self.read_overlay)     # 窗口真正定位后再刷新一次

        self.listener = keyboard.Listener(on_press=on_press,
                                          on_release=on_release)
        self.listener.daemon = True
        self.listener.start()

        self.root.after(30, self.pump)

    # ---------- UI ----------
    def _build_ui(self):
        pad = {"padx": 10, "pady": 4}

        tk.Label(self.root, text="① 粘贴简谱（豆包识别的结果直接贴进来）",
                 anchor="w", font=("Microsoft YaHei", 10, "bold")).pack(
            fill="x", **pad)
        self.txt_in = tk.Text(self.root, height=5, font=("Consolas", 11),
                              undo=True)
        self.txt_in.pack(fill="both", expand=True, padx=10)
        self.txt_in.insert("1.0", DEMO_SHEET)

        bar = tk.Frame(self.root)
        bar.pack(fill="x", **pad)
        tk.Button(bar, text="② 解析", command=self.do_parse,
                  width=12).pack(side="left")
        tk.Button(bar, text="清空", command=self.clear_input,
                  width=6).pack(side="left", padx=4)
        self.lbl_stat = tk.Label(bar, text="", anchor="w",
                                 font=("Microsoft YaHei", 9), fg="#0A7")
        self.lbl_stat.pack(side="left", padx=8)

        tk.Label(self.root, text="③ 解析预览（简谱 / 键位）", anchor="w",
                 font=("Microsoft YaHei", 10, "bold")).pack(fill="x", **pad)
        self.txt_out = tk.Text(self.root, height=5, font=("Consolas", 10),
                               bg="#F7F7F7", state="disabled")
        self.txt_out.pack(fill="both", expand=True, padx=10)

        mf = tk.LabelFrame(self.root, text="④ 模式")
        mf.pack(fill="x", **pad)
        for text, val in [("顺序 · 按错卡住不放", "seq_block"),
                          ("顺序 · 按错闪红继续", "seq_continue"),
                          ("时间 · 不等你（可调速）", "time")]:
            tk.Radiobutton(mf, text=text, value=val, variable=self.mode,
                           command=self.on_mode).pack(anchor="w", padx=8)

        sf = tk.Frame(mf)
        sf.pack(fill="x", padx=8, pady=4)
        tk.Label(sf, text="速度").pack(side="left")
        self.sc_speed = tk.Scale(sf, from_=0.5, to=2.0, resolution=0.1,
                                 orient="horizontal", variable=self.speed,
                                 length=200)
        self.sc_speed.pack(side="left", padx=6)
        self.lbl_speed = tk.Label(sf, text="1.0x")
        self.lbl_speed.pack(side="left")
        self.speed.trace_add("write", lambda *_: self.lbl_speed.config(
            text=f"{self.speed.get():.1f}x"))
        tk.Label(sf, text="  每音(ms)").pack(side="left")
        tk.Entry(sf, textvariable=self.beat_ms, width=6).pack(side="left")
        self.sc_speed.configure(state="disabled")

        # ⑤ 覆盖层微调（比手拖准，拖不准就用这个）
        tf = tk.LabelFrame(self.root, text="⑤ 覆盖层微调（对不齐时用，比手拖准）")
        tf.pack(fill="x", **pad)
        r1 = tk.Frame(tf)
        r1.pack(fill="x", padx=8, pady=2)
        self.e_x, self.e_y, self.e_w, self.e_h = (tk.Entry(r1, width=5)
                                                  for _ in range(4))
        for lab, ent in (("X", self.e_x), ("Y", self.e_y),
                         ("宽", self.e_w), ("高", self.e_h)):
            tk.Label(r1, text=lab).pack(side="left")
            ent.pack(side="left", padx=(0, 6))
        r2 = tk.Frame(tf)
        r2.pack(fill="x", padx=8, pady=2)
        tk.Button(r2, text="读取当前", command=self.read_overlay).pack(side="left")
        tk.Button(r2, text="应用", command=self.apply_overlay).pack(side="left", padx=4)
        for lab, dx, dy in (("←", -10, 0), ("→", 10, 0), ("↑", 0, -10), ("↓", 0, 10)):
            tk.Button(r2, text=lab, width=3,
                      command=lambda dx=dx, dy=dy: self.nudge_overlay(dx, dy)
                      ).pack(side="left")

        # ⑥ 键位
        kf = tk.LabelFrame(self.root, text="⑥ 键位（点覆盖层上的琴键即可改绑）")
        kf.pack(fill="x", **pad)
        # 版本切换
        vr = tk.Frame(kf)
        vr.pack(fill="x", padx=8, pady=(4, 0))
        tk.Label(vr, text="版本：", font=("Microsoft YaHei", 9, "bold")).pack(side="left")
        self.ver_var = tk.StringVar(value=K.version)
        for vid, (label, _, _) in K.VERSIONS.items():
            tk.Radiobutton(vr, text=label, value=vid, variable=self.ver_var,
                           command=self.on_version).pack(side="left", padx=4)

        kr = tk.Frame(kf)
        kr.pack(fill="x", padx=8, pady=2)
        tk.Button(kr, text="改键模式 (F6)", command=self.toggle_remap,
                  width=14).pack(side="left")
        tk.Button(kr, text="恢复默认", command=self.reset_keys,
                  width=10).pack(side="left", padx=6)
        tk.Button(kr, text="保存键位", width=10,
                  command=lambda: (K.save_state(), self.lbl_run.config(
                      text="键位已保存到 keymap.json"))
                  ).pack(side="left")
        self.lbl_keys = tk.Label(kf, text="", anchor="w", justify="left",
                                 font=("Consolas", 8), fg="#555")
        self.lbl_keys.pack(fill="x", padx=8, pady=(0, 4))

        # ⑦ 曲库
        lf = tk.LabelFrame(self.root, text="⑦ 曲库（保存 / 载入 / 连弹）")
        lf.pack(fill="x", **pad)
        lr = tk.Frame(lf)
        lr.pack(fill="x", padx=8, pady=3)
        self.cb_song = ttk.Combobox(lr, width=20, state="readonly", values=[])
        self.cb_song.pack(side="left")
        tk.Button(lr, text="载入", width=6,
                  command=self.lib_load).pack(side="left", padx=4)
        tk.Button(lr, text="保存", width=6,
                  command=self.lib_save).pack(side="left")
        tk.Button(lr, text="删除", width=6,
                  command=self.lib_delete).pack(side="left", padx=4)
        self.var_auto = tk.BooleanVar(value=False)
        tk.Checkbutton(lr, text="弹完自动下一首",
                       variable=self.var_auto).pack(side="left", padx=4)

        cf = tk.Frame(self.root)
        cf.pack(fill="x", **pad)
        self.btn_run = tk.Button(cf, text="▶ 开始 (F8)", command=self.toggle_run,
                                 width=11, bg="#D8F5E3")
        self.btn_run.pack(side="left")
        tk.Button(cf, text="⟲ 重来 (F9)", command=self.reset,
                  width=10).pack(side="left", padx=4)
        tk.Button(cf, text="标定 (F7)", command=self.toggle_calib,
                  width=10).pack(side="left")
        tk.Button(cf, text="隐藏/显示 (F5)", command=self.toggle_overlay,
                  width=13).pack(side="left", padx=4)

        self.lbl_run = tk.Label(self.root, text="就绪｜先解析，再按 F7 把覆盖层对齐游戏钢琴",
                                anchor="w", font=("Microsoft YaHei", 9), fg="#666")
        self.lbl_run.pack(fill="x", **pad)

        self.root.bind("<Escape>", lambda e: self.stop())

    # ---------- 解析 ----------
    def do_parse(self):
        text = self.txt_in.get("1.0", "end")
        steps, issues = S.parse(text)
        self.steps = steps
        self.txt_out.configure(state="normal")
        self.txt_out.delete("1.0", "end")
        if not steps:
            self.txt_out.insert("1.0", "解析不出任何音符，检查一下格式")
        else:
            self.txt_out.insert("1.0", S.render(steps))
            if issues:
                self.txt_out.insert("end", "\n【问题】\n" + "\n".join(issues))
        self.txt_out.configure(state="disabled")
        self.lbl_stat.config(text=S.stats(steps) if steps else "空",
                             fg="#0A7" if steps and not issues else "#C60")
        self.reset()

    def clear_input(self):
        self.txt_in.delete("1.0", "end")
        self.txt_out.configure(state="normal")
        self.txt_out.delete("1.0", "end")
        self.txt_out.configure(state="disabled")
        self.steps = []
        self.stop()
        self.lbl_stat.config(text="")
        self.lbl_run.config(text="已清空 —— 把琴谱文本粘到①，再点② 解析")

    # ---------- 模式 ----------
    def on_mode(self):
        running = self.engine is not None
        if running:
            self.stop()
        is_time = self.mode.get() == "time"
        self.sc_speed.configure(state="normal" if is_time else "disabled")
        self.lbl_run.config(text=f"模式已切换：{self.mode.get()}")

    # ---------- 运行控制 ----------
    def toggle_run(self):
        if self.engine:
            self.stop()
        else:
            self.start()

    def start(self):
        if not self.steps:
            self.do_parse()
            if not self.steps:
                return
        m = self.mode.get()
        if m == "time":
            self.engine = TimeEngine(self.steps, beat_ms=self.beat_ms.get(),
                                     speed=self.speed.get())
            import time as _t
            self.engine.start(_t.perf_counter())
        else:
            self.engine = SequenceEngine(
                self.steps, wrong_mode="block" if m == "seq_block" else "continue")
        self.btn_run.config(text="■ 停止 (F8)", bg="#FADBD8")
        self.lbl_run.config(text="演奏中…")
        self._last_render = None
        self._refresh_overlay()

    def stop(self):
        if isinstance(self.engine, TimeEngine):
            self.engine.stop()
        self.engine = None
        self.btn_run.config(text="▶ 开始 (F8)", bg="#D8F5E3")
        self.lbl_run.config(text="已停止")
        self.overlay.set_highlight()

    def reset(self):
        self.stop()
        self.lbl_run.config(text="已重来（按 F8 从头开始）")

    def toggle_calib(self):
        on = self.overlay.toggle_calibration()
        self.lbl_run.config(text="标定模式：拖动覆盖层对齐游戏钢琴，再按 F7 保存"
                            if on else "标定已保存")
        self.read_overlay()

    # ---------- 覆盖层微调 ----------
    def read_overlay(self):
        x, y = self.overlay.current_pos()
        for ent, val in ((self.e_x, x), (self.e_y, y),
                         (self.e_w, self.overlay.w), (self.e_h, self.overlay.h)):
            ent.delete(0, "end")
            ent.insert(0, str(val))

    def apply_overlay(self):
        try:
            self.overlay.set_size(int(self.e_w.get()), int(self.e_h.get()))
            self.overlay.set_pos(int(self.e_x.get()), int(self.e_y.get()))
            self.lbl_run.config(text="覆盖层位置/尺寸已应用并保存")
        except ValueError:
            self.lbl_run.config(text="X/Y/宽/高 必须是数字")

    def nudge_overlay(self, dx, dy):
        self.overlay.nudge(dx, dy)
        self.read_overlay()

    # ---------- 覆盖层刷新 ----------
    def _refresh_overlay(self):
        if isinstance(self.engine, SequenceEngine):
            now = set(self.engine.expect)
            nxt = set()
            if self.engine.index + 1 < len(self.steps):
                nxt = set(self.steps[self.engine.index + 1].keys)
            self.overlay.set_highlight(now=now, preview=nxt)
        # 时间模式由 pump 里的 tick 驱动，这里不用管

    # ---------- 事件泵 ----------
    def pump(self):
        import time as _t
        while not EVENTS.empty():
            kind, val = EVENTS.get()
            if kind == "hotkey":
                if val == "f5":
                    self.toggle_overlay()
                elif val == "f6":
                    self.toggle_remap()
                elif val == "f7":
                    self.toggle_calib()
                elif val == "f8":
                    self.toggle_run()
                elif val == "f9":
                    self.reset()
            elif kind == "press":
                self._on_key(val)
            elif kind == "release":
                if isinstance(self.engine, SequenceEngine):
                    self.engine.release(val)

        # 时间模式：定时推进
        if isinstance(self.engine, TimeEngine) and self.engine.running:
            r = self.engine.tick(_t.perf_counter())
            if r:
                if r.finished:
                    self.overlay.set_highlight()
                    self.stop()
                    self.song_finished()
                else:
                    nxt = set()
                    if r.index + 1 < len(self.steps):
                        nxt = set(self.steps[r.index + 1].keys)
                    self.overlay.set_highlight(now=r.expect, preview=nxt)
                    self.lbl_run.config(
                        text=f"时间模式  {r.index + 1}/{len(self.steps)}  "
                             f"{r.progress * 100:.0f}%")

        self.root.after(30, self.pump)

    def toggle_overlay(self):
        on = self.overlay.toggle_visible()
        self.lbl_run.config(
            text="覆盖层：已隐藏（按 F5 恢复）" if not on
            else "覆盖层：已显示")

    # ---------- 曲库 ----------
    def refresh_library(self, select=None):
        songs = Lib.list_songs()
        self.cb_song["values"] = songs
        if songs:
            if select in songs:
                self.cb_song.set(select)
            elif self.cb_song.get() not in songs:
                self.cb_song.set(songs[0])
        else:
            self.cb_song.set("")

    def lib_save(self):
        text = self.txt_in.get("1.0", "end").strip()
        if not text:
            self.lbl_run.config(text="输入框是空的，没东西可保存")
            return
        guess = Lib.detect_title(text)
        if guess:
            name = simpledialog.askstring(
                "保存到曲库", f"自动识别到曲名（可改）：",
                initialvalue=guess, parent=self.root)
        else:
            name = simpledialog.askstring(
                "保存到曲库", "没识别出曲名，请输入：", parent=self.root)
        if not name:
            return
        name = Lib.safe_name(name)
        if Lib.save_song(name, text):
            self.refresh_library(select=name)
            self.lbl_run.config(text=f"已保存到曲库：{name}")
        else:
            self.lbl_run.config(text="保存失败")

    def lib_load(self):
        name = self.cb_song.get()
        if not name:
            self.lbl_run.config(text="曲库是空的")
            return False
        text = Lib.load_song(name)
        if text is None:
            self.lbl_run.config(text=f"载入失败：{name}")
            return False
        self.txt_in.delete("1.0", "end")
        self.txt_in.insert("1.0", text)
        self.do_parse()
        self.lbl_run.config(text=f"已载入：{name}（{S.stats(self.steps)}）")
        return True

    def lib_delete(self):
        name = self.cb_song.get()
        if not name:
            return
        if messagebox.askyesno("删除", f"确定从曲库删除「{name}」？",
                               parent=self.root):
            Lib.delete_song(name)
            self.refresh_library()
            self.lbl_run.config(text=f"已删除：{name}")

    def song_finished(self):
        """一首弹完之后调用：需要的话自动切下一首"""
        if self.var_auto.get():
            nxt = Lib.next_song(self.cb_song.get())
            if nxt:
                self.cb_song.set(nxt)
                self.lbl_run.config(text=f"✅ 弹完，准备下一首：{nxt}")
                self.root.after(800, self._play_next)
                return
        self.lbl_run.config(text="✅ 弹完了")

    def _play_next(self):
        if self.lib_load():
            self.start()

    # ---------- 改键 ----------
    def toggle_remap(self):
        if self.engine:
            self.stop()
        on = self.overlay.toggle_remap()
        self.lbl_run.config(
            text="改键模式：点覆盖层上的琴键选中，再按新键即可（F6 退出）"
            if on else "已退出改键模式")

    def refresh_keymap(self):
        if hasattr(self, "lbl_keys"):
            self.lbl_keys.config(text=K.dump_rows())

    def on_version(self):
        v = self.ver_var.get()
        if v == K.version:
            return
        if self.engine:
            self.stop()
        if self.overlay.remap_mode:
            self.overlay.toggle_remap()
        K.switch_version(v)
        self.refresh_keymap()
        self.do_parse()
        self.overlay.redraw()
        self.lbl_run.config(text=f"已切换：{K.version_name()}")

    def reset_keys(self):
        K.reset_map()
        K.save_state()
        self.refresh_keymap()
        self.do_parse()
        self.lbl_run.config(text=f"「{K.version_name()}」已恢复出厂键位")

    def _on_key(self, key):
        # 改键模式下：按键不喂给引擎，而是用来重新绑键
        if self.overlay.remap_mode:
            if self.overlay.remap_midi is not None:
                r = self.overlay.apply_remap(key)
                if r:
                    name, old, new, other = r
                    K.save_state()
                    msg = f"改键 ✓  {name}:  {old}  →  {new}"
                    if other is not None:
                        msg += f"   （与 {K.note_name(other)} 交换了键位）"
                    self.refresh_keymap()
                    self.do_parse()          # 先刷新预览（它会重置状态栏）
                    self.lbl_run.config(text=msg)   # 再把提示写回去
            return

        if not isinstance(self.engine, SequenceEngine):
            return
        r = self.engine.press(key)
        if r.status == Seq.WRONG:
            self.overlay.set_highlight(now=r.expect, wrong={key})
            self.lbl_run.config(
                text=f"❌ 按错了 '{key}'  该按 {sorted(r.expect)}"
                     f"  (第 {r.index + 1}/{len(self.steps)} 个音)")
            self.root.after(180, self._refresh_overlay)
            return
        if r.status == Seq.SONG_DONE:
            self.lbl_run.config(text=f"✅ 全曲弹完！失误 {r.mistakes} 次")
            self.overlay.set_highlight()
            self.stop()
            self.song_finished()
            return
        if r.status in (Seq.CORRECT, Seq.STEP_DONE):
            nxt = set()
            if r.index + 1 < len(self.steps):
                nxt = set(self.steps[r.index + 1].keys)
            self.overlay.set_highlight(now=r.expect, preview=nxt)
            self.lbl_run.config(
                text=f"第 {r.index + 1}/{len(self.steps)} 个音"
                     + (f"　失误 {r.mistakes}" if r.mistakes else ""))

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        App().run()
    except Exception:
        import os
        import traceback
        tb = traceback.format_exc()
        print(tb)
        log = os.path.join(os.path.dirname(os.path.abspath(__file__)), "error.log")
        try:
            with open(log, "w", encoding="utf-8") as f:
                f.write(tb)
            print(f"错误已写入: {log}")
        except Exception:
            pass
        try:
            input("出错了，按回车关闭…")
        except Exception:
            pass
