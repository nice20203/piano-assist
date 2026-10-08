# -*- coding: utf-8 -*-
"""第五人格钢琴：音高 <-> 键位映射（两个版本，可切换）

版本：
  full36   完整版 · 36 键（3 行 × 12，含黑键）
  basic21  基础版 · 21 键（3 行 × 7，只有白键；游戏里关闭黑键时用）

改键、切换版本都会存到 keymap.json，每个版本各存一份。
"""

import json
import os

LOW, HIGH = 48, 83                      # MIDI 音域 C3 ~ B5

# ---------------- 键位预设 ----------------
# 预设从 presets/*.json 加载，一个文件 = 一套键位方案。
# 想适配别的游戏，只要往 presets/ 里丢一个 JSON，不用改代码。
# 下面这份是 presets/ 目录缺失时的兜底。

PRESET_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "presets")

_BUILTIN = {
    "identity-v-36": (
        "第五人格 · 完整版 36 键（含黑键）",
        {48: ",", 49: "L", 50: ".", 51: ";", 52: "/", 53: "I",
         54: "9", 55: "O", 56: "0", 57: "P", 58: "-", 59: "[",
         60: "Z", 61: "S", 62: "X", 63: "D", 64: "C", 65: "V",
         66: "G", 67: "B", 68: "H", 69: "N", 70: "J", 71: "M",
         72: "Q", 73: "2", 74: "W", 75: "3", 76: "E", 77: "R",
         78: "5", 79: "T", 80: "6", 81: "Y", 82: "7", 83: "U"}, 12),
    "identity-v-21": (
        "第五人格 · 基础版 21 键（只有白键）",
        {48: "Z", 50: "X", 52: "C", 53: "V", 55: "B", 57: "N", 59: "M",
         60: "A", 62: "S", 64: "D", 65: "F", 67: "G", 69: "H", 71: "J",
         72: "Q", 74: "W", 76: "E", 77: "R", 79: "T", 81: "Y", 83: "U"}, 7),
}

# 旧版内置 id -> 新预设 id（兼容老配置文件）
_ALIAS = {"full36": "identity-v-36", "basic21": "identity-v-21"}


def load_presets():
    """扫描 presets/*.json -> {id: (显示名, {音高: 键位}, 每行键数)}"""
    out, default_id = {}, None
    if os.path.isdir(PRESET_DIR):
        for fn in sorted(os.listdir(PRESET_DIR)):
            if not fn.lower().endswith(".json"):
                continue
            try:
                with open(os.path.join(PRESET_DIR, fn), encoding="utf-8") as f:
                    d = json.load(f)
            except Exception:
                continue
            pid = d.get("id") or os.path.splitext(fn)[0]
            mp = {}
            for k, v in (d.get("map") or {}).items():
                try:
                    midi = int(k)
                except (TypeError, ValueError):
                    continue
                if isinstance(v, str) and v:
                    mp[midi] = v
            if mp:
                try:
                    cols = int(d.get("cols", 12))
                except (TypeError, ValueError):
                    cols = 12
                out[pid] = (d.get("name", pid), mp, cols)
                if d.get("default"):
                    default_id = pid
    if default_id and default_id in out:
        out = {default_id: out[default_id],
               **{k: v for k, v in out.items() if k != default_id}}
    return out or {k: (v[0], dict(v[1]), v[2]) for k, v in _BUILTIN.items()}


VERSIONS = load_presets()

BLACK_SEMITONES = {61, 63, 66, 68, 70, 73, 75, 78, 80, 82}

KEYMAP_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "keymap.json")

_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

# ---- 当前状态（由 rebuild() 维护）----
version = next(iter(VERSIONS))
MIDI_TO_KEY = dict(VERSIONS[version][1])
KEY_TO_MIDI = {}
ROWS = []
COLS = 12
BLACK_KEY_SET = set()


def rebuild():
    """按当前版本重建派生表"""
    global KEY_TO_MIDI, ROWS, COLS, BLACK_KEY_SET
    KEY_TO_MIDI = {v: k for k, v in MIDI_TO_KEY.items()}
    cols = VERSIONS[version][2]
    COLS = cols
    ROWS = []
    for base in (48, 60, 72):
        row, m = [], base
        while len(row) < cols and m <= HIGH:
            if m in MIDI_TO_KEY:
                row.append(MIDI_TO_KEY[m])
            m += 1
        ROWS.append(row)
    BLACK_KEY_SET = {MIDI_TO_KEY[m] for m in BLACK_SEMITONES if m in MIDI_TO_KEY}


def note_name(midi):
    return f"{_NAMES[midi % 12]}{midi // 12 - 1}"


def key_of(midi):
    return MIDI_TO_KEY.get(midi)


def shift_into_range(midi):
    """按八度折回 48~83"""
    while midi < LOW:
        midi += 12
    while midi > HIGH:
        midi -= 12
    return midi


def is_playable(midi):
    return midi in MIDI_TO_KEY


def nearest_playable(midi):
    """最近的可用音（同距离优先取低音）；基础版里用来把升降号就近归到白键"""
    if midi in MIDI_TO_KEY:
        return midi
    for d in range(1, 13):
        if midi - d in MIDI_TO_KEY:
            return midi - d
        if midi + d in MIDI_TO_KEY:
            return midi + d
    return None


# ---------------- 改键 ----------------
def remap(midi, new_key):
    """把某个音改绑到 new_key；被占用就和它【交换】，保证一键一音。
    返回 (是否交换, 被交换的音)"""
    new_key = (new_key.upper() if len(new_key) == 1 and new_key.isalpha()
               else new_key)
    old_key = MIDI_TO_KEY.get(midi)
    if old_key == new_key:
        return False, None
    other = KEY_TO_MIDI.get(new_key)
    if other is not None and other != midi:
        MIDI_TO_KEY[other] = old_key
        MIDI_TO_KEY[midi] = new_key
        rebuild()
        return True, other
    MIDI_TO_KEY[midi] = new_key
    rebuild()
    return False, None


def reset_map():
    """把【当前版本】恢复出厂"""
    MIDI_TO_KEY.clear()
    MIDI_TO_KEY.update(VERSIONS[version][1])
    rebuild()


# ---------------- 版本切换 ----------------
def _read_raw(path):
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _write_raw(path, d):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def _apply(ver, maps=None):
    global version
    version = ver
    MIDI_TO_KEY.clear()
    saved = (maps or {}).get(ver)
    if saved:
        for k, v in saved.items():
            try:
                midi = int(k)
            except ValueError:
                continue
            if LOW <= midi <= HIGH and isinstance(v, str) and v:
                MIDI_TO_KEY[midi] = v
    else:
        MIDI_TO_KEY.update(VERSIONS[ver][1])
    rebuild()


def load_state(path=None):
    path = path or KEYMAP_PATH
    d = _read_raw(path)
    ver = _ALIAS.get(d.get("version", ""), d.get("version", ""))
    if ver not in VERSIONS:
        ver = next(iter(VERSIONS))
    _apply(ver, d.get("maps", {}))
    return ver


def save_state(path=None):
    path = path or KEYMAP_PATH
    d = _read_raw(path)
    maps = d.get("maps", {})
    maps[version] = {str(k): v for k, v in sorted(MIDI_TO_KEY.items())}
    return _write_raw(path, {"version": version, "maps": maps})


def switch_version(ver, path=None):
    """切版本：先把当前版本的键位存下来，再载入目标版本"""
    ver = _ALIAS.get(ver, ver)
    if ver not in VERSIONS or ver == version:
        return False
    path = path or KEYMAP_PATH
    d = _read_raw(path)
    maps = d.get("maps", {})
    maps[version] = {str(k): v for k, v in sorted(MIDI_TO_KEY.items())}
    _apply(ver, maps)
    _write_raw(path, {"version": version, "maps": maps})
    return True


# ---------------- 界面用 ----------------
def version_name():
    return VERSIONS[version][0]


def dump_rows():
    """三行键位（高音在上），只列当前版本真正有的音"""
    out = []
    for label, idx, base in (("高音", 2, 72), ("中音", 1, 60), ("低音", 0, 48)):
        m, items = base, []
        while len(items) < COLS and m <= HIGH:
            if m in MIDI_TO_KEY:
                items.append(f"{note_name(m)}:{MIDI_TO_KEY[m]}")
            m += 1
        out.append(f"{label}  " + "  ".join(items))
    return "\n".join(out)


rebuild()
