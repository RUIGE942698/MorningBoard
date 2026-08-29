# -*- coding: utf-8 -*-
"""AI 生成内容查重。

用途：避免思辨题 / 表达课 / 每日一课 与「近期已生成过的内容」或「静态知识库里已有的条目」撞题。

设计要点：
- 已用标题存在 cache/ai_used.json（cache/ 已 gitignore，不入库），按 kind 分桶、带日期。
  比从历史归档里现读更可靠：归档会被清理，而缓存是累积的、可跨天、可限长。
- 查重不是比字符串相等，而是归一化后算相似度（difflib），
  并处理"一个标题被另一个完整包含"的情况，能挡住换汤不换药的近似题。
- 静态知识库标题也进比对池：AI 不该把库里已有的内容再生产一遍。
"""
import datetime as dt
import difflib
import json
import os
import re

from . import config, knowledge

# 相似度阈值：>= 该值判定为撞题。
# 0.66 是实测出来的分界线：换汤不换药的近似题约 0.69，
# 而不同议题之间普遍在 0.35~0.45，留了足够余量不误杀。
SIM_THRESHOLD = 0.66
# 静态知识库用更松的阈值：库里条目很多，太严会把正常新题误杀掉，只挡几乎一模一样的
STATIC_THRESHOLD = 0.85
# 每个 kind 最多保留的已用标题条数（防止文件无限增长）
MAX_ENTRIES = 400
# 已用标题参与比对的时间窗口（天）
WINDOW_DAYS = 180

KINDS = ("lesson", "thinking", "expression")

_PUNCT_RE = re.compile(r"[\s\W_]+", re.UNICODE)


def _path():
    return os.path.join(config.CACHE_DIR, "ai_used.json")


def _load():
    try:
        with open(_path(), encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def _save(d):
    try:
        config.ensure_dirs()
        with open(_path(), "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=1)
    except Exception:  # noqa: BLE001
        pass


def used_titles(kind, days=WINDOW_DAYS):
    """最近 N 天内已用过的标题（按时间由近到远）。"""
    today = dt.date.today()
    out = []
    for e in (_load().get(kind) or []):
        if not isinstance(e, dict) or not e.get("t"):
            continue
        raw = e.get("date") or ""
        try:
            day = dt.date.fromisoformat(raw) if raw else today
        except ValueError:
            day = today
        if (today - day).days <= days:
            out.append(e["t"])
    return out


def record(kind, titles, day=None):
    """登记一批已用标题（按标题去重，只保留最近 MAX_ENTRIES 条）。"""
    titles = [t for t in (titles or []) if t]
    if not titles:
        return
    d = _load()
    arr = [x for x in (d.get(kind) or []) if isinstance(x, dict)]
    have = {x.get("t") for x in arr}
    iso = (day or dt.date.today()).isoformat()
    changed = False
    for t in titles:
        if t not in have:
            arr.append({"t": t, "date": iso})
            have.add(t)
            changed = True
    if changed:
        d[kind] = arr[-MAX_ENTRIES:]
        _save(d)


def static_titles(kind):
    """静态知识库里已有的标题（AI 不该重复生产它们）。"""
    try:
        if kind == "thinking":
            arr = knowledge.load_thinking()
        elif kind == "expression":
            arr = knowledge.load_expression()
        else:
            arr = []
    except Exception:  # noqa: BLE001
        arr = []
    return [x.get("t", "") for x in arr if isinstance(x, dict) and x.get("t")]


def pool(kind, days=WINDOW_DAYS):
    """完整比对池 = 近期已用标题 + 静态知识库标题。"""
    return used_titles(kind, days) + static_titles(kind)


def norm(s):
    """归一化：去空白与标点、转小写，便于比较。"""
    return _PUNCT_RE.sub("", (s or "").lower())


def similarity(a, b):
    """两个标题的相似度 0~1。

    取两种算法里较高的值：
    - 序列比对 ratio：整体字符重合度
    - 公共子串覆盖率：两标题共享一段长核心、仅前后缀不同时（如
      「测试题目：AI 会不会取代老师」vs「AI 会不会取代老师：一个测试」），
      纯序列比对会明显低估，用最长公共子串占较短标题的比例来补。
    """
    na, nb = norm(a), norm(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    # 一个标题被另一个完整包含（如加了副标题），也视为高度相似
    if na in nb or nb in na:
        return 0.95
    seq = difflib.SequenceMatcher(None, na, nb)
    lcs = seq.find_longest_match(0, len(na), 0, len(nb)).size
    cover = lcs / max(1, min(len(na), len(nb)))
    return max(seq.ratio(), cover)


def find_conflict(kind, title, extra=None, threshold=SIM_THRESHOLD, static_threshold=STATIC_THRESHOLD):
    """在比对池中找与该标题冲突的项。返回 (是否撞题, 撞上的标题, 最高相似度)。

    近期 AI 生成的内容用 threshold（较严，防重复出题）；
    静态知识库用 static_threshold（较松，只挡几乎一模一样的，避免误杀新题）。
    """
    best, best_score = None, 0.0
    top, top_score = None, 0.0

    def _scan(cands, th):
        nonlocal best, best_score, top, top_score
        for c in cands:
            s = similarity(title, c)
            # 记录真实最高分（即便没到阈值，日志里也要看得到"差多少"）
            if s > top_score:
                top, top_score = c, s
            if s >= th and s > best_score:
                best, best_score = c, s

    _scan(list(extra or []) + used_titles(kind), threshold)
    _scan(static_titles(kind), static_threshold)
    if best is not None:
        return True, best, best_score
    # 没撞题时把最接近的一条也回传，便于排查
    return False, top, top_score


def batch_conflict(kind, titles, threshold=SIM_THRESHOLD, static_threshold=STATIC_THRESHOLD):
    """一批标题内部 + 与历史/静态库的撞题检查。

    思辨一次出 2 题，两题之间也不能相似，所以要把同批其它标题也放进 extra。
    返回 (是否撞题, 撞上的标题, 最高相似度)。
    """
    titles = [t for t in (titles or []) if t]
    worst, ws = None, 0.0
    for i, t in enumerate(titles):
        others = [x for j, x in enumerate(titles) if j != i]
        hit, who, score = find_conflict(
            kind, t, extra=others, threshold=threshold, static_threshold=static_threshold
        )
        if hit and score > ws:
            worst, ws = who, score
    return (worst is not None), worst, ws


def sync_from_history(days=WINDOW_DAYS):
    """把历史归档里已有的 AI 内容标题回填进已用表（老数据也能参与查重）。"""
    hist_dir = os.path.join(config.CACHE_DIR, "history")
    if not os.path.isdir(hist_dir):
        return 0
    today = dt.date.today()
    n = 0
    try:
        files = sorted(f for f in os.listdir(hist_dir) if f.endswith(".json"))
    except OSError:
        return 0
    for f in files:
        try:
            day = dt.date.fromisoformat(f[:10])
        except ValueError:
            day = today
        if (today - day).days > days:
            continue
        try:
            with open(os.path.join(hist_dir, f), encoding="utf-8") as fp:
                data = json.load(fp)
        except Exception:  # noqa: BLE001
            continue
        th = [x.get("t", "") for x in (data.get("thinking") or []) if isinstance(x, dict)]
        ex = (data.get("expression") or {})
        ex = ex.get("t") if isinstance(ex, dict) else None
        ls = (data.get("lesson") or {})
        ls = ls.get("title") if (isinstance(ls, dict) and data.get("ai_generated")) else None
        if th:
            record("thinking", th, day=day)
            n += len(th)
        if ex:
            record("expression", [ex], day=day)
            n += 1
        if ls:
            record("lesson", [ls], day=day)
            n += 1
    return n
