# -*- coding: utf-8 -*-
"""每晚入口：新闻联播（19:00）结束后收集信息、生成当日汇总并自动弹出展示。

由任务计划 MorningBoard-Generate 于每天 20:00 调用（错过自动补跑）。
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from app import generate  # noqa: E402


def main():
    payload, is_new = generate.generate_today(force=True)
    print(
        "generated: {0} news={1} funds={2} new={3}".format(
            payload.get("date"),
            len((payload.get("news") or {}).get("items", [])),
            len((payload.get("funds") or {}).get("watchlist", [])),
            is_new,
        )
    )
    # 收集完成 -> 自动弹出展示窗口（pythonw 无控制台；已有窗口时单实例锁自动忽略）
    if getattr(sys, "frozen", False):
        # 打包模式：同目录的 MorningBoard.exe 就是展示窗口
        exe = os.path.join(os.path.dirname(sys.executable), "MorningBoard.exe")
        if os.path.exists(exe):
            subprocess.Popen([exe])
        return 0
    py = sys.executable
    base = os.path.dirname(py)
    pyw = os.path.join(base, "pythonw.exe")
    if not os.path.exists(pyw):
        pyw = py
    subprocess.Popen([pyw, os.path.join(ROOT, "morning_show.py")])
    return 0


if __name__ == "__main__":
    sys.exit(main())
