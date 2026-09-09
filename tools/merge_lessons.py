# -*- coding: utf-8 -*-
"""把多 Agent 产出的课程批次文件合并进课程库（knowledge_extra.json）。

用法：python tools/merge_lessons.py
读取 lessons_incoming/*.json（格式：{"分类名": [{t,s,b,links}, ...]}），
按标题去重后追加到对应分类（走 app.lesson_updater.append_lessons）。
"""
import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from app import knowledge, lesson_updater  # noqa: E402

_IN_CANDIDATES = [
    os.environ.get("LESSONS_INCOMING", ""),
    os.path.join(os.path.expanduser("~"), "WorkBuddy", "2026-08-29-19-18-15", "lessons_incoming"),
    os.path.join(os.path.dirname(ROOT), "WorkBuddy", "2026-08-29-19-18-15", "lessons_incoming"),
    os.path.join(ROOT, "lessons_incoming"),
]
IN_DIR = next((p for p in _IN_CANDIDATES if p and os.path.isdir(p)), _IN_CANDIDATES[-1])


def main():
    files = sorted(glob.glob(os.path.join(IN_DIR, "*.json")))
    if not files:
        print("没有待合并的批次文件：", IN_DIR)
        return
    total_new = 0
    for fp in files:
        try:
            with open(fp, encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:  # noqa: BLE001
            print("跳过（解析失败）", os.path.basename(fp), e)
            continue
        if not isinstance(data, dict):
            continue
        for cat, items in data.items():
            if not isinstance(items, list):
                continue
            n = lesson_updater.append_lessons(cat, items)
            if n:
                total_new += n
                print("  {0}: +{1} 讲".format(cat, n))
    print("合计新增 {0} 讲".format(total_new))
    print("当前各分类课数:", lesson_updater.counts())
    print("总计:", sum(lesson_updater.counts().values()))


if __name__ == "__main__":
    main()
