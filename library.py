# -*- coding: utf-8 -*-
"""曲库：琴谱的保存 / 载入 / 删除

每个谱存成 曲库/<曲名>.txt，纯文本，直接可读可改。
"""

import os
import re

LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "曲库")

# 整行都是"音符记号"的样子（数字、升降号、八度点、空格、小节线）
_NOTEISH = re.compile(r"^[\d#b',\s|]+$")
# 文件名不能用的字符
_BAD = re.compile(r'[\\/:*?"<>|\r\n\t]')


def ensure_dir():
    os.makedirs(LIB_DIR, exist_ok=True)


def safe_name(name):
    """清掉文件名非法字符"""
    name = _BAD.sub("_", (name or "").strip())
    name = name.strip(" .")
    return name[:60] or "未命名"


def detect_title(text):
    """从谱面文本里自动猜曲名。

    认这几种：
      1. 行首 # 的注释行     ->  # 起风了
      2. 开头不像音符的行     ->  起风了
    猜不到返回 None
    """
    for raw in text.splitlines()[:12]:
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#"):
            t = line.lstrip("#").strip()
            if t:
                return safe_name(t)
        elif not _NOTEISH.match(line):
            # 含汉字/字母等，显然不是音符 -> 当标题
            return safe_name(line)
    return None


def list_songs():
    ensure_dir()
    try:
        return sorted(f[:-4] for f in os.listdir(LIB_DIR)
                      if f.lower().endswith(".txt"))
    except Exception:
        return []


def path_of(name):
    return os.path.join(LIB_DIR, safe_name(name) + ".txt")


def save_song(name, text):
    ensure_dir()
    try:
        with open(path_of(name), "w", encoding="utf-8") as f:
            f.write(text if text.endswith("\n") else text + "\n")
        return True
    except Exception:
        return False


def load_song(name):
    try:
        with open(path_of(name), encoding="utf-8") as f:
            return f.read()
    except Exception:
        return None


def delete_song(name):
    try:
        os.remove(path_of(name))
        return True
    except Exception:
        return False


def next_song(current, songs=None):
    """曲库里的下一首（循环）"""
    songs = songs if songs is not None else list_songs()
    if not songs:
        return None
    if current in songs:
        i = songs.index(current)
        return songs[(i + 1) % len(songs)] if len(songs) > 1 else None
    return songs[0]
