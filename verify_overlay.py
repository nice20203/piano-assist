# -*- coding: utf-8 -*-
"""验证：覆盖层现在到底看不看得见"""
import os, subprocess, sys, tkinter as tk
sys.stdout.reconfigure(encoding="utf-8")

import overlay as O

HERE = os.path.dirname(os.path.abspath(__file__))
SHOT = os.path.join(HERE, "_verify.png")

root = tk.Tk()
root.geometry("260x90+40+40")

ov = O.PianoOverlay(parent=root)
ov.set_highlight(now=set(O.K.ROWS[1]))      # 中音行 12 键高亮成 #00E5A0

info = {}


def grab():
    info.update(sx=ov.root.winfo_screenwidth(), sy=ov.root.winfo_screenheight(),
                ox=ov.root.winfo_x(), oy=ov.root.winfo_y(), w=ov.w, h=ov.h)
    subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                    "-File", os.path.join(HERE, "shot.ps1"), SHOT],
                   capture_output=True)


root.after(1500, grab)
root.after(3200, root.destroy)
root.mainloop()

from PIL import Image
im = Image.open(SHOT).convert("RGB")
IW, IH = im.size
scale = IW / info["sx"]
print(f"Tk 逻辑屏幕 {info['sx']}x{info['sy']}   截图 {IW}x{IH}   缩放比 {scale:.3f}")
print(f"覆盖层逻辑位置 ({info['ox']},{info['oy']}) {info['w']}x{info['h']}")
bx0 = int(info["ox"] * scale); by0 = int(info["oy"] * scale)
bx1 = int((info["ox"] + info["w"]) * scale); by1 = int((info["oy"] + info["h"]) * scale)
print(f"换算到截图坐标: ({bx0},{by0}) ~ ({bx1},{by1})")

px = im.load()


def count_in_box(target, tol):
    n = 0
    for y in range(max(0, by0), min(IH, by1), 2):
        for x in range(max(0, bx0), min(IW, bx1), 2):
            if all(abs(a - b) <= tol for a, b in zip(px[x, y], target)):
                n += 1
    return n


white = count_in_box((0xED, 0xED, 0xED), 12)      # 白键
green = count_in_box((0x00, 0xE5, 0xA0), 12)      # 高亮键
blue = count_in_box((0x00, 0xA3, 0xFF), 30)       # 蓝色外框

print()
print(f"窗口区域内 白键 #EDEDED 采样点数 : {white}")
print(f"窗口区域内 高亮 #00E5A0 采样点数 : {green}")
print(f"外框区域   蓝框 #00A3FF 采样点数 : {blue}")

from collections import Counter
cnt = Counter()
for y in range(max(0, by0), min(IH, by1)):
    for x in range(max(0, bx0), min(IW, bx1)):
        cnt[px[x, y]] += 1
print("\n窗口区域内出现最多的 8 种颜色：")
for c, n in cnt.most_common(8):
    print(f"    {c}  {n} 次")
print()
if white + green > 50:
    print("=> 覆盖层【正常显示】✓ 修好了")
else:
    print("=> 覆盖层【仍然看不见】✗")
