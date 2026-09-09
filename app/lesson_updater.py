# -*- coding: utf-8 -*-
"""每日一课课程库扩充：AI 给全部分类写新课，写入 extra 文件由 knowledge.load_all 合并。

- 开发模式写 knowledge/knowledge_extra.json（随 git 保存，属课程资产）
- 打包版内置库只读，写 %APPDATA%/MorningBoard/lessons_extra.json
- 每周日由 generate_today 触发：每门课 +N 讲，拉长循环周期；
  循环本身即复习（艾宾浩斯间隔），新课持续稀释重复感。
"""
import json
import os

from . import ai_gen, config, knowledge


def _load_extra():
    try:
        with open(config.LESSONS_EXTRA, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def append_lessons(cat, items):
    """把 AI 新课追加到某分类（按标题去重，同时排除基础库已有标题）。返回新增条数。"""
    if not cat or not isinstance(items, list):
        return 0
    items = [
        it
        for it in items
        if isinstance(it, dict) and it.get("t") and isinstance(it.get("b"), list) and it["b"]
    ]
    if not items:
        return 0
    data = _load_extra()
    bucket = data.get(cat) if isinstance(data.get(cat), list) else []
    existing = {it.get("t") for it in bucket}
    for it in knowledge.load_all().get(cat) or []:
        existing.add(it.get("t"))
    added = [it for it in items if it["t"] not in existing]
    if not added:
        return 0
    data[cat] = bucket + added
    try:
        os.makedirs(os.path.dirname(config.LESSONS_EXTRA), exist_ok=True)
        with open(config.LESSONS_EXTRA, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        knowledge.invalidate_cache()
        return len(added)
    except OSError:
        return 0


def expand_all(per=3, cats=None):
    """给全部分类各扩 per 讲新课。返回 {cat: 新增数}；单个分类失败不影响其它。"""
    out = {}
    targets = cats or [c for c, _ in knowledge.CATS]
    for cat in targets:
        entries = knowledge.load_all().get(cat) or []
        titles = [it.get("t") for it in entries if it.get("t")]
        try:
            items = ai_gen.generate_with_retry(
                lambda c=cat, e=titles, n=per: ai_gen.generate_lesson_batch(c, e, n)
            )
        except Exception:  # noqa: BLE001
            items = None
        if items:
            n = append_lessons(cat, items)
            if n:
                out[cat] = n
    return out


def counts():
    """当前各分类课数（含扩充）。"""
    lib = knowledge.load_all()
    return {c: len(lib.get(c) or []) for c, _ in knowledge.CATS}
