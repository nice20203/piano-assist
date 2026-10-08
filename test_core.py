# -*- coding: utf-8 -*-
"""自测：解析器 + 两种模式引擎（不需要 GUI、不需要游戏）"""
import sys, time
sys.stdout.reconfigure(encoding="utf-8")

from score import parse, stats, render
from engine import SequenceEngine, TimeEngine, Seq

# 豆包识别的那首，按升级版提示词补上小节线（每 4 拍一段）
SHEET = """
5
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

steps, issues = parse(SHEET)

print("=" * 62)
print("【解析结果】")
print(f"  {stats(steps)}")
if issues:
    print("  问题：")
    for i in issues:
        print("    -", i)
else:
    print("  无解析问题 ✓")

print()
print(render(steps))

# ---------------- 顺序模式 ----------------
print("=" * 62)
print("【顺序模式 · block（按错卡住不放）】")

eng = SequenceEngine(steps, wrong_mode="block")

# 模拟：第 5 个音故意按错
for i in range(4):
    for k in sorted(eng.expect):
        eng.press(k)
    for k in sorted(eng.expect):
        eng.release(k)
print(f"  已顺利弹过 {eng.index} 个音")

wrong = "U" if "U" not in eng.expect else "M"
r = eng.press(wrong)
print(f"  故意按错 '{wrong}' -> 状态={r.status}  仍停在第 {r.index + 1} 个音（卡住不放）✓")
print(f"  该按的是: {sorted(r.expect)}")
eng.release(wrong)

# 换 continue 模式试同一个错
eng2 = SequenceEngine(steps, wrong_mode="continue")
for i in range(4):
    for k in sorted(eng2.expect):
        eng2.press(k)
    for k in sorted(eng2.expect):
        eng2.release(k)
r2 = eng2.press("U" if "U" not in eng2.expect else "M")
print(f"  同样按错，continue 模式 -> 状态={r2.status}  已推进到第 {r2.index + 1} 个音（闪红继续）✓")

# ---------------- 完整跑一遍 ----------------
print()
print("【顺序模式 · block 完整跑完】")
eng3 = SequenceEngine(steps, wrong_mode="block")
guard = 0
while not eng3.done and guard < 10000:
    want = sorted(eng3.expect)
    for k in want:
        eng3.press(k)
    for k in want:
        eng3.release(k)
    guard += 1
print(f"  完成: {eng3.done} | 总时刻 {eng3.total} | 失误 {eng3.mistakes}")

# ---------------- 时间模式 ----------------
print()
print("【时间模式 · 统一节拍 500ms，1.5 倍速】")
te = TimeEngine(steps, beat_ms=500, speed=1.5)
now = time.perf_counter()
te.start(now)
for t in range(0, 6):
    r = te.tick(now + t * 0.3)
    if r:
        print(f"  t={t*0.3:.1f}s -> 第 {r.index + 1:>2} 个音  "
              f"{sorted(r.expect)}  进度 {r.progress * 100:4.1f}%"
              f"  {'← 刚到，闪一下' if r.fresh else ''}")
print("=" * 62)
