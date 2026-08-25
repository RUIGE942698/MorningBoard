# -*- coding: utf-8 -*-
"""知识库加载与每日轮转。

每日课程 = 主课（按天轮换分类）+ 其余 4 类各一张小卡。
每个分类内部按"年内第几天"取条目，保证每天都向前推进、不重复（转完一圈自动循环）。
"""
import datetime as dt
import json
import os

from . import config

CATS = [
    ("周易", "zhouyi.json"),
    ("哲学", "philosophy.json"),
    ("文学", "literature.json"),
    ("音乐", "music.json"),
    ("毛选", "mao.json"),
    ("心理学", "psychology.json"),
    ("美学", "aesthetics.json"),
    ("摄影", "photography.json"),
    ("经济学", "economics.json"),
    ("历史", "history.json"),
    ("茶艺", "tea.json"),
    ("礼仪", "etiquette.json"),
    ("官场文化", "officialdom.json"),
]

_cache = None
_terms_cache = None


def load_terms():
    """全局术语表：汇总所有条目的 links 名词（按长度降序，供正文内联跳转）。"""
    global _terms_cache
    if _terms_cache is None:
        s = set()
        for entries in load_all().values():
            for it in entries:
                for x in it.get("links", []):
                    x = str(x).strip()
                    if len(x) >= 2:
                        s.add(x)
        _terms_cache = sorted(s, key=len, reverse=True)
    return _terms_cache


def load_all():
    """加载全部知识库 -> {分类名: [条目, ...]}"""
    global _cache
    if _cache is None:
        lib = {}
        for cat, fn in CATS:
            p = os.path.join(config.KNOWLEDGE_DIR, fn)
            try:
                with open(p, encoding="utf-8") as f:
                    lib[cat] = json.load(f)
            except Exception:  # noqa: BLE001
                lib[cat] = []
        _cache = lib
    return _cache


def _fmt_weekday(d):
    return "星期" + "一二三四五六日"[d.weekday()]


def load_quotes():
    """加载金句库 -> [{"t","s"}, ...]"""
    try:
        with open(os.path.join(config.KNOWLEDGE_DIR, "quotes.json"), encoding="utf-8") as f:
            q = json.load(f)
        return q if isinstance(q, list) else []
    except Exception:  # noqa: BLE001
        return []


def load_thinking():
    """加载思辨题库（第五板块）-> [{"t","s","pro","con","ask","links"}, ...]"""
    return _load_json_file("thinking.json")


def load_thinking_tools():
    """加载思维工具库 -> [{"t","s","b","links"}, ...]"""
    return _load_json_file("thinking_tools.json")


def load_fallacies():
    """加载逻辑谬误库 -> [{"t","s","b","links"}, ...]"""
    return _load_json_file("fallacies.json")


def load_expression():
    """加载表达能力库 -> [{"t","s","b","links"}, ...]"""
    return _load_json_file("expression.json")


def load_term_library():
    """术语词典（第七模块）：遍历 knowledge/terms/*.json -> [{"domain","t","s","b","links"}, ...]"""
    out = []
    d = os.path.join(config.KNOWLEDGE_DIR, "terms")
    try:
        files = sorted(f for f in os.listdir(d) if f.endswith(".json"))
    except OSError:
        return out
    for fn in files:
        try:
            with open(os.path.join(d, fn), encoding="utf-8") as f:
                data = json.load(f)
        except Exception:  # noqa: BLE001
            continue
        domain = data.get("domain", fn[:-5])
        for it in data.get("items", []):
            item = dict(it)
            item["domain"] = domain
            out.append(item)
    return out


def _load_json_file(fn):
    try:
        with open(os.path.join(config.KNOWLEDGE_DIR, fn), encoding="utf-8") as f:
            arr = json.load(f)
        return arr if isinstance(arr, list) else []
    except Exception:  # noqa: BLE001
        return []


def daily_plan(day=None):
    d = day or dt.date.today()
    doy = d.timetuple().tm_yday
    lib = load_all()
    cats = [c for c, _ in CATS]
    main_cat = cats[(doy - 1) % len(cats)]
    plan = {
        "date": d.isoformat(),
        "weekday": _fmt_weekday(d),
        "main_cat": main_cat,
        "main": None,
        "cards": [],
        "quote": None,
    }
    qs = load_quotes()
    if qs:
        qi = (doy - 1) % len(qs)
        plan["quote"] = {"text": qs[qi].get("t", ""), "author": qs[qi].get("s", "")}
    for c in cats:
        entries = lib.get(c) or []
        if not entries:
            continue
        idx = (doy - 1) % len(entries)
        item = {
            "cat": c,
            "idx": idx,
            "total": len(entries),
            "title": entries[idx].get("t", ""),
            "sub": entries[idx].get("s", ""),
            "body": entries[idx].get("b", []),
            "links": entries[idx].get("links", []),
        }
        if c == main_cat:
            plan["main"] = item
        else:
            plan["cards"].append(item)
    return plan
