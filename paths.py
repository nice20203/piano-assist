# -*- coding: utf-8 -*-
"""路径解析：同一份代码，既能源码运行，也能打包成 exe 运行

- 源码运行：一切都在脚本所在目录
- 打包 exe：内置资源在临时解包目录（只读），
  用户数据（键位/标定/曲库）写到 exe 旁边，这样才是「绿色免安装」
"""

import os
import sys


def app_dir():
    """用户数据目录：exe 旁边 / 脚本旁边"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def resource_dir():
    """内置只读资源目录（打包后被解到临时目录）"""
    if getattr(sys, "frozen", False):
        return getattr(sys, "_MEIPASS", app_dir())
    return os.path.dirname(os.path.abspath(__file__))


def preset_dir():
    """键位预设目录：优先用 exe 旁边的（用户可以自己加方案），否则用内置的"""
    beside = os.path.join(app_dir(), "presets")
    if os.path.isdir(beside):
        return beside
    return os.path.join(resource_dir(), "presets")


def data_file(name):
    return os.path.join(app_dir(), name)
