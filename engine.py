# -*- coding: utf-8 -*-
"""双模式推进引擎

【顺序模式】SequenceEngine —— 等你
      wrong_mode="block"    : 按错卡住不放（学得最牢）
      wrong_mode="continue" : 按错闪红，仍往下走（流畅通顺）

【时间模式】TimeEngine —— 不等你，统一节拍，可调速
"""

from dataclasses import dataclass


# ============================ 顺序模式 ============================

class Seq:
    CORRECT = "correct"       # 按对了一个音（和弦还没齐）
    STEP_DONE = "step_done"   # 这个时刻弹完，进入下一个
    WRONG = "wrong"           # 按错了
    SONG_DONE = "song_done"   # 整首完成
    IGNORED = "ignored"       # 长按重复触发，忽略


@dataclass
class SeqResult:
    status: str
    index: int                # 当前时刻序号（0 基）
    expect: set               # 现在该按哪些键
    wrong_key: str = None
    mistakes: int = 0


class SequenceEngine:
    def __init__(self, steps, wrong_mode="block"):
        if wrong_mode not in ("block", "continue"):
            raise ValueError("wrong_mode 只能是 block 或 continue")
        self.steps = steps
        self.wrong_mode = wrong_mode
        self.index = 0
        self.held = set()      # 当前按住的键（用于过滤长按重复）
        self.hit = set()       # 本时刻已按对的键
        self.mistakes = 0

    # ---- 查询 ----
    @property
    def done(self):
        return self.index >= len(self.steps)

    @property
    def expect(self):
        """当前该按的键集合（和弦就是多个）"""
        if self.done:
            return set()
        return set(self.steps[self.index].keys)

    @property
    def total(self):
        return len(self.steps)

    # ---- 交互 ----
    def press(self, key):
        if key in self.held:
            return self._r(Seq.IGNORED)             # 忽略长按重复
        self.held.add(key)

        if self.done:
            return self._r(Seq.SONG_DONE)

        if key in self.expect:
            self.hit.add(key)
            if self.expect <= self.hit:             # 和弦整个按齐了
                return self._advance(Seq.STEP_DONE)
            return self._r(Seq.CORRECT)

        # 按错了
        self.mistakes += 1
        if self.wrong_mode == "continue":
            return self._advance(Seq.WRONG, wrong_key=key)
        return self._r(Seq.WRONG, wrong_key=key)

    def release(self, key):
        self.held.discard(key)

    def reset(self):
        self.index = 0
        self.held.clear()
        self.hit = set()
        self.mistakes = 0

    # ---- 内部 ----
    def _advance(self, status, wrong_key=None):
        self.index += 1
        self.hit = set()
        if self.done:
            return self._r(Seq.SONG_DONE, wrong_key=wrong_key)
        return self._r(status, wrong_key=wrong_key)

    def _r(self, status, wrong_key=None):
        return SeqResult(status=status, index=self.index, expect=self.expect,
                         wrong_key=wrong_key, mistakes=self.mistakes)


# ============================ 时间模式 ============================

@dataclass
class TimeResult:
    index: int                # 当前该亮的时刻
    expect: set               # 该按的键
    fresh: bool               # 是否是刚跳到这个时刻（用来触发"闪一下"）
    progress: float           # 0.0 ~ 1.0
    finished: bool


class TimeEngine:
    """统一节拍：所有时刻等间隔，不等你按键"""

    def __init__(self, steps, beat_ms=500, speed=1.0):
        self.steps = steps
        self.beat_ms = beat_ms
        self.speed = speed          # >1 更快，<1 更慢
        self.t0 = None
        self._last = -1

    def start(self, now):
        self.t0 = now
        self._last = -1

    def stop(self):
        self.t0 = None

    @property
    def running(self):
        return self.t0 is not None

    def set_speed(self, speed):
        """调速：按当前进度重新对齐时间基准，避免跳帧"""
        self.speed = max(0.1, min(4.0, speed))

    def tick(self, now):
        if self.t0 is None or not self.steps:
            return None
        elapsed_ms = (now - self.t0) * 1000.0 * self.speed
        idx = int(elapsed_ms // self.beat_ms)

        if idx >= len(self.steps):
            return TimeResult(index=len(self.steps) - 1, expect=set(),
                              fresh=False, progress=1.0, finished=True)

        fresh = idx != self._last
        self._last = idx
        return TimeResult(index=idx, expect=set(self.steps[idx].keys),
                          fresh=fresh, progress=idx / len(self.steps),
                          finished=False)
