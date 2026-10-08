# -*- coding: utf-8 -*-
"""简谱解析：文本 -> 音符序列

输入格式（豆包按提示词输出的就是这个）：
    5            <- 每行一个"时刻"
    6
    1'
    5 1'         <- 行内空格分隔 = 同时按（和弦）
    |            <- 单独一行 = 小节线
    # 这是注释   <- 行首 # = 注释

记法：
    1-7          音高（大调音阶）
    '  /  ,      上点=高一个八度 / 下点=低一个八度（可叠加）
    #  /  b      升 / 降（跟在数字后面）

注意：Note.key 是【动态属性】，实时查 keys.MIDI_TO_KEY，
      所以改键位后不用重新解析，覆盖层和引擎立刻用新键位。
"""

import re
from dataclasses import dataclass

import keys as K

BASE = 60                                   # 简谱 1（无点）= C4
SCALE = {1: 0, 2: 2, 3: 4, 4: 5, 5: 7, 6: 9, 7: 11}

_TOKEN = re.compile(r"^([1-7])([#b]?)([',]*)$")


@dataclass
class Note:
    text: str                               # 原始记号，如 "1'"
    midi_raw: int                           # 原始音高
    midi: int                               # 适配后（可能折叠/就近归位过）
    folded: bool = False                    # 是否被八度折叠过
    snapped: bool = False                   # 是否被就近归到白键（基础版没有黑键）

    @property
    def key(self):
        """实时查当前键位表"""
        return K.MIDI_TO_KEY.get(self.midi)

    @property
    def range_ok(self):
        return not self.folded


@dataclass
class Step:
    """一个时刻：行内多个音 = 和弦，同时按"""
    notes: list
    bar: bool = False                       # 紧跟在小节线之后

    @property
    def keys(self):
        return {n.key for n in self.notes if n.key}


def token_to_midi(tok):
    """'1'' -> 72 ；识别不了返回 None"""
    m = _TOKEN.fullmatch(tok)
    if not m:
        return None
    digit, acc, octs = int(m.group(1)), m.group(2), m.group(3)
    midi = BASE + SCALE[digit]
    for ch in octs:
        midi += 12 if ch == "'" else -12
    if acc == "#":
        midi += 1
    elif acc == "b":
        midi -= 1
    return midi


def parse(text, fold=True):
    """解析简谱文本。

    fold=True  : 超出 36 键范围的音自动按八度折回（推荐）
    fold=False : 超范围的音丢掉，并在 issues 里报告

    返回 (steps, issues)
    """
    steps, issues = [], []
    pending_bar = False
    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#"):            # 注释
            continue
        if line.startswith("|"):            # 小节线
            pending_bar = True
            continue

        notes = []
        for tok in line.split():
            midi = token_to_midi(tok)
            if midi is None:
                issues.append(f"第{lineno}行: 认不出 '{tok}'")
                continue
            raw = midi
            folded = False
            if not (K.LOW <= midi <= K.HIGH):
                if fold:
                    midi = K.shift_into_range(midi)
                    folded = True
                else:
                    issues.append(
                        f"第{lineno}行: '{tok}' ({K.note_name(midi)}) 超出音域，已丢弃")
                    continue

            # 当前版本弹不了的音（基础版 21 键没有黑键）→ 就近归到白键
            snapped = False
            if not K.is_playable(midi):
                near = K.nearest_playable(midi)
                if near is None:
                    issues.append(f"第{lineno}行: '{tok}' 当前版本弹不了，已丢弃")
                    continue
                midi = near
                snapped = True

            notes.append(Note(text=tok, midi_raw=raw, midi=midi,
                              folded=folded, snapped=snapped))

        if notes:
            steps.append(Step(notes=notes, bar=pending_bar))
            pending_bar = False

    return steps, issues


def stats(steps):
    total = sum(len(s.notes) for s in steps)
    folded = sum(1 for s in steps for n in s.notes if n.folded)
    snapped = sum(1 for s in steps for n in s.notes if n.snapped)
    if total == 0:
        return "空谱面"
    mids = [n.midi_raw for s in steps for n in s.notes]
    txt = (f"{len(steps)} 个音 | 音域 {K.note_name(min(mids))}~{K.note_name(max(mids))}")
    if folded:
        txt += f" | 折叠 {folded}"
    if snapped:
        txt += f" | 黑键归位 {snapped}"
    return txt


def render(steps, per_line=8):
    """渲染成 简谱/键位 对照表，方便肉眼核对"""
    rows, buf_jp, buf_key = [], [], []
    for s in steps:
        buf_jp.append(" ".join(n.text for n in s.notes))
        buf_key.append(" ".join(n.key or "?" for n in s.notes))
        if len(buf_jp) == per_line:
            rows.append((" ".join(buf_jp), " ".join(buf_key)))
            buf_jp, buf_key = [], []
    if buf_jp:
        rows.append((" ".join(buf_jp), " ".join(buf_key)))

    lines, idx = [], 1
    for jp, ky in rows:
        lines.append(f"{idx:>4}  简谱: {jp}")
        lines.append(f"      键位: {ky}")
        lines.append("")
        idx += per_line
    return "\n".join(lines)
