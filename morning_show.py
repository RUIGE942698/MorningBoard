# -*- coding: utf-8 -*-
"""入口：显示晨报窗口。支持 --smoke（3 秒后自动关闭，用于自测）。

单实例保护：窗口已存在时，再次启动直接退出，避免开机启动 + 手动双击重复开窗。
"""
import ctypes  # noqa: E402

# ---- DPI 感知：必须在任何 GUI 初始化之前调用（否则高分屏缩放会导致界面模糊） ----
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:  # noqa: BLE001
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:  # noqa: BLE001
        pass

import os  # noqa: E402
import socket  # noqa: E402
import sys  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.gui import main  # noqa: E402

_LOCK_PORT = 18765


def _acquire_lock():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", _LOCK_PORT))
        s.listen(1)
        return s
    except OSError:
        return None


if __name__ == "__main__":
    smoke = "--smoke" in sys.argv
    lock = None
    if not smoke:
        lock = _acquire_lock()
        if lock is None:
            sys.exit(0)  # 已有实例在运行
    try:
        main(smoke=smoke)
    finally:
        if lock is not None:
            lock.close()
