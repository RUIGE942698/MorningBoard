# -*- coding: utf-8 -*-
"""表达能力教练：把「每日练习系统 + 12 周路线 + 实战转化机制」变成可执行逻辑。

设计要点
  - 练习编排：每天 20 分钟四段（朗读 / 即兴 / 复盘 / 课+费曼），即兴题目与朗读材料按日期轮换
  - 进度：以首次使用日为起点自动推算处于 12 周路线的第几周，并按周调整当日要求
  - 打卡：cache/expression_state.json 记录每日完成情况，算出连续天数
  - 素材库：cache/expression_materials.json（观点金句 / 我的故事 / 数据案例 三栏，可自加）
  - 选课：静态库按「6 大模块轮换 + 当日不重复」挑选，AI 课时优先生效
用法
  python -m app.expression_coach --plan        打印今日练习计划
  python -m app.expression_coach --stats       打卡与进度统计
  python -m app.expression_coach --checkin improv   标记某一段完成
"""
import argparse
import datetime as dt
import io
import json
import os
import random
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app import config  # noqa: E402

PRACTICE_PATH = os.path.join(config.KNOWLEDGE_DIR, "expression_practice.json")
EXPRESSION_PATH = os.path.join(config.KNOWLEDGE_DIR, "expression.json")
STATE_PATH = os.path.join(config.CACHE_DIR, "expression_state.json")
MATERIALS_PATH = os.path.join(config.CACHE_DIR, "expression_materials.json")

MODULE_KEYS = ("structure", "persuasion", "story", "voice", "improv", "mindset")

# 静态库条目没有 module 字段时，按关键词推断所属模块
_MODULE_HINTS = (
    ("structure", ("金字塔", "MECE", "PREP", "SCQA", "电梯", "结构", "总分", "逻辑链")),
    ("persuasion", ("说服", "修辞", "Ethos", "Pathos", "Logos", "影响力", "互惠",
                    "稀缺", "社会认同", "权威", "承诺")),
    ("story", ("故事", "叙事", "冲突", "转折", "细节", "英雄", "类比", "比喻")),
    ("voice", ("停顿", "重音", "语速", "声音", "眼神", "手势", "肢体", "站姿",
               "语调", "节奏", "口头禅")),
    ("improv", ("即兴", "控场", "质疑", "打断", "救场", "Yes", "反驳", "辩论", "问答")),
    ("mindset", ("紧张", "焦虑", "心态", "自信", "失误", "恐惧", "情绪", "准备")),
)


def _read_json(path, default):
    try:
        with io.open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:  # noqa: BLE001
        return default


def _write_json(path, data):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with io.open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        return True
    except Exception:  # noqa: BLE001
        return False


# ------------------------------------------------------------------ 数据加载
def load_practice():
    return _read_json(PRACTICE_PATH, {}) or {}


def load_state():
    st = _read_json(STATE_PATH, {}) or {}
    st.setdefault("start_date", dt.date.today().isoformat())
    st.setdefault("checkins", {})
    st.setdefault("scenarios", {})
    st.setdefault("rating", {})
    return st


def save_state(st):
    return _write_json(STATE_PATH, st)


# ------------------------------------------------------------------ 进度与打卡
def week_number(day=None, st=None):
    """处于 12 周路线的第几周（从首次使用日算起，上限 12）。"""
    st = st or load_state()
    day = day or dt.date.today()
    try:
        start = dt.date.fromisoformat(str(st.get("start_date")))
    except Exception:  # noqa: BLE001
        start = day
    n = (day - start).days // 7 + 1
    return max(1, min(12, n))


def week_info(day=None, st=None):
    wk = week_number(day, st)
    weeks = (load_practice().get("weeks") or [])
    for w in weeks:
        if int(w.get("week") or 0) == wk:
            return wk, w
    return wk, {}


def focus_module(day=None, st=None):
    """本周主攻模块：(key, name, week, focus_text)。

    前 8 周按 12 周路线推进模块；模块与周次对齐，保证「学」与「练」同向。
    """
    day = day or dt.date.today()
    wk = week_number(day, st)
    key = MODULE_KEYS[(wk - 1) % len(MODULE_KEYS)]
    name = key
    for m in (load_practice().get("modules") or []):
        if m.get("key") == key:
            name = m.get("name") or key
            break
    _, winfo = week_info(day, st)
    return key, name, wk, winfo.get("focus", "")


def checkin(block_key, day=None, value=True):
    st = load_state()
    day = (day or dt.date.today()).isoformat()
    rec = st["checkins"].setdefault(day, {})
    if value:
        rec[block_key] = True
    else:
        rec.pop(block_key, None)
    save_state(st)
    return rec


def today_checkins(day=None, st=None):
    st = st or load_state()
    day = (day or dt.date.today()).isoformat()
    return st.get("checkins", {}).get(day, {}) or {}


def streak(day=None, st=None):
    """连续打卡天数（当天未打卡则从昨天往前算）。"""
    st = st or load_state()
    day = day or dt.date.today()
    ck = st.get("checkins", {})
    n = 0
    cur = day
    if not ck.get(cur.isoformat()):
        cur = cur - dt.timedelta(days=1)
    while ck.get(cur.isoformat()):
        n += 1
        cur = cur - dt.timedelta(days=1)
    return n


def total_days(st=None):
    st = st or load_state()
    return len([d for d, v in (st.get("checkins") or {}).items() if v])


# ------------------------------------------------------------------ 今日练习编排
def today_plan(day=None, st=None):
    """今日 20 分钟练习计划（题目/材料/要求随日期与周次变化）。"""
    day = day or dt.date.today()
    st = st or load_state()
    p = load_practice()
    daily = p.get("daily") or {}
    blocks = list(daily.get("blocks") or [])
    wk, winfo = week_info(day, st)

    topics = p.get("improv_topics") or []
    topic = topics[(day.timetuple().tm_yday - 1) % len(topics)] if topics else "自由命题"

    out = []
    for b in blocks:
        b = dict(b)
        key = b.get("key")
        if key == "read":
            mats = b.get("materials") or []
            if mats:
                b["prompt"] = "今日材料：" + mats[(day.timetuple().tm_yday - 1) % len(mats)]
        elif key == "improv":
            b["prompt"] = "今日题目：「{0}」——不准备，直接讲 2 分钟并录像".format(topic)
            if wk >= 9:
                b["prompt"] = "今日题目（说服型）：「说服一个反对你的人：{0}」——先复述对方立场，再给方案".format(topic)
            elif wk >= 5:
                b["prompt"] = "今日题目：「{0}」——必须塞一个自己的真实小故事（30 秒版）".format(topic)
            elif wk >= 3:
                b["prompt"] = "今日题目：「{0}」——强制 PREP：先亮观点，再理由，再例子，最后重申".format(topic)
        elif key == "review":
            b["prompt"] = "只记三件事：口头禅次数 / 眼神是否飘 / 重点句有没有被强调"
        elif key == "learn":
            b["prompt"] = "今日课见下方卡片；看完合上讲义，录 60 秒讲给完全不懂的人听（费曼）"
        out.append(b)

    return {
        "date": day.isoformat(),
        "weekday": "周" + "一二三四五六日"[day.weekday()],
        "week": wk,
        "week_focus": winfo.get("focus", ""),
        "week_goal": winfo.get("goal", ""),
        "week_twist": winfo.get("daily_twist", ""),
        "week_pass": winfo.get("pass", ""),
        "topic": topic,
        "rule": daily.get("rule", ""),
        "total_minutes": daily.get("total_minutes", 20),
        "blocks": out,
    }


# ------------------------------------------------------------------ 选课（模块轮换）
def _infer_module(item):
    m = (item or {}).get("module")
    if m in MODULE_KEYS:
        return m
    text = " ".join([str(item.get("t", "")), str(item.get("s", ""))] +
                    [str(x) for x in (item.get("b") or [])[:2]])
    for key, words in _MODULE_HINTS:
        for w in words:
            if w in text:
                return key
    return "structure"


def lesson_of_day(day=None, offset=0):
    """按模块轮换选课：优先挑当日模块下尚未出现的条目，保证 6 大模块依次覆盖。"""
    day = day or dt.date.today()
    items = _read_json(EXPRESSION_PATH, []) or []
    if not items:
        return None, "structure"
    wk = week_number(day)
    # 前 8 周：模块按周推进（每周主攻 1–2 个模块）；之后轮换
    focus = MODULE_KEYS[(wk - 1) % len(MODULE_KEYS)]
    pool = [x for x in items if _infer_module(x) == focus]
    if not pool:
        pool = items
    idx = (day.timetuple().tm_yday - 1 + offset * 7) % len(pool)
    if offset:                      # 「换一课」：随机换同模块的另一条
        idx = random.randrange(len(pool))
    return pool[idx], focus


def module_progress():
    """各模块条目数 + 静态库总条目数。"""
    items = _read_json(EXPRESSION_PATH, []) or []
    counts = {k: 0 for k in MODULE_KEYS}
    for x in items:
        counts[_infer_module(x)] = counts.get(_infer_module(x), 0) + 1
    names = {m["key"]: m["name"] for m in (load_practice().get("modules") or [])
             if m.get("key")}
    return [{"key": k, "name": names.get(k, k), "count": counts.get(k, 0)}
            for k in MODULE_KEYS], len(items)


# ------------------------------------------------------------------ 素材库
def materials():
    """素材库：条目为 {"t": 文本, "at": 日期}；兼容早期的纯字符串。"""
    d = _read_json(MATERIALS_PATH, {}) or {}
    d.setdefault("quotes", [])
    d.setdefault("stories", [])
    d.setdefault("data", [])
    return d


def _mat_text(x):
    return (x.get("t") if isinstance(x, dict) else str(x)) or ""


def _mat_date(x):
    return (x.get("at") if isinstance(x, dict) else "") or ""


def materials_text(kind):
    """素材文本列表（界面显示用）。"""
    return [_mat_text(x) for x in (materials().get(kind) or []) if _mat_text(x)]


def preset_quotes():
    return list(load_practice().get("inspiration") or [])


def add_material(kind, text):
    kind = kind if kind in ("quotes", "stories", "data") else "quotes"
    text = (text or "").strip()
    if not text:
        return False
    d = materials()
    have = [_mat_text(x) for x in d[kind]]
    if text not in have:
        d[kind].append({"t": text, "at": dt.date.today().isoformat()})
    return _write_json(MATERIALS_PATH, d)


def remove_material(kind, text):
    d = materials()
    rows = d.get(kind) or []
    for i, x in enumerate(rows):
        if _mat_text(x) == text:
            rows.pop(i)
            return _write_json(MATERIALS_PATH, d)
    return False


# ------------------------------------------------------------------ 场景清单与自评
def scenarios():
    st = load_state()
    return [{"key": s.get("key"), "text": s.get("text"),
             "done": bool((st.get("scenarios") or {}).get(s.get("key")))}
            for s in (load_practice().get("scenarios") or [])]


def toggle_scenario(key):
    st = load_state()
    cur = bool((st.get("scenarios") or {}).get(key))
    st.setdefault("scenarios", {})[key] = not cur
    if not cur:                      # 完成时记日期（用于周复盘）
        st.setdefault("scenario_log", {})[key] = dt.date.today().isoformat()
    save_state(st)
    return not cur


def get_rating():
    return load_state().get("rating") or {}


def set_rating(level, value=True):
    st = load_state()
    key = str(level)
    st.setdefault("rating", {})[key] = bool(value)
    hist = st.setdefault("rating_history", [])
    hist.append({"date": dt.date.today().isoformat(), "level": key, "value": bool(value)})
    st["rating_history"] = hist[-200:]
    save_state(st)
    return st["rating"]


def week_bounds(day=None):
    """本周（周一~周日）日期区间。"""
    day = day or dt.date.today()
    start = day - dt.timedelta(days=day.weekday())
    return start, start + dt.timedelta(days=6)


def longest_streak(st=None):
    """历史最长连续打卡天数。"""
    st = st or load_state()
    days = sorted(d for d, v in (st.get("checkins") or {}).items() if v)
    if not days:
        return 0
    best = cur = 1
    prev = dt.date.fromisoformat(days[0])
    for d in days[1:]:
        cur_d = dt.date.fromisoformat(d)
        cur = cur + 1 if (cur_d - prev).days == 1 else 1
        best = max(best, cur)
        prev = cur_d
    return best


def weekly_stats(day=None):
    """本周练习统计（周复盘用）。"""
    day = day or dt.date.today()
    st = load_state()
    start, end = week_bounds(day)
    ck = st.get("checkins") or {}
    block_keys = [b.get("key") for b in (load_practice().get("daily") or {}).get("blocks", [])]
    per_block = {k: 0 for k in block_keys}
    practiced_days = 0
    full_days = 0
    for d, rec in ck.items():
        try:
            dd = dt.date.fromisoformat(d)
        except Exception:  # noqa: BLE001
            continue
        if not (start <= dd <= end) or not rec:
            continue
        practiced_days += 1
        if all(rec.get(k) for k in block_keys):
            full_days += 1
        for k in block_keys:
            if rec.get(k):
                per_block[k] += 1

    # 最近 7 天（含今天）滚动口径：周中复盘也有意义
    d7 = day - dt.timedelta(days=6)
    days7 = 0
    per_block7 = {k: 0 for k in block_keys}
    for d, rec in ck.items():
        try:
            dd = dt.date.fromisoformat(d)
        except Exception:  # noqa: BLE001
            continue
        if not (d7 <= dd <= day) or not rec:
            continue
        days7 += 1
        for k in block_keys:
            if rec.get(k):
                per_block7[k] += 1

    mats = materials()
    mat_week = sum(1 for kind in mats for x in mats[kind]
                   if _mat_date(x) and start.isoformat() <= _mat_date(x) <= end.isoformat())
    mat_total = sum(len(mats[k]) for k in mats)

    sclog = st.get("scenario_log") or {}
    scen_week = sum(1 for v in sclog.values() if start.isoformat() <= str(v) <= end.isoformat())
    scen_total = len([k for k, v in (st.get("scenarios") or {}).items() if v])

    hist_changes = [h for h in (st.get("rating_history") or [])
                    if start.isoformat() <= str(h.get("date")) <= end.isoformat()]

    return {
        "week_start": start.isoformat(), "week_end": end.isoformat(),
        "days_in_week": (min(end, day) - start).days + 1,
        "practiced_days": practiced_days, "full_days": full_days,
        "per_block": per_block, "block_keys": block_keys,
        "last7_days": days7, "per_block7": per_block7,
        "streak": streak(st=st), "longest_streak": longest_streak(st=st),
        "total_days": total_days(st=st),
        "materials_week": mat_week, "materials_total": mat_total,
        "scenarios_week": scen_week, "scenarios_total": scen_total,
        "rating_changes": hist_changes,
    }


REVIEW_PATH = os.path.join(config.CACHE_DIR, "expression_review.json")
REVIEW_QUESTIONS = (
    ("q1", "本周哪一次表达你最满意？为什么（别人给了什么反馈）？"),
    ("q2", "哪里卡住了？（口头禅/结构乱/紧张/被问倒/没素材…）"),
    ("q3", "下周只改一件事，改什么？（写具体动作）"),
)


def get_reflection(week_start=None):
    d = _read_json(REVIEW_PATH, {}) or {}
    ws = week_start or week_bounds()[0].isoformat()
    return d.get(ws) or {}


def save_reflection(answers, week_start=None):
    d = _read_json(REVIEW_PATH, {}) or {}
    ws = week_start or week_bounds()[0].isoformat()
    rec = dict(d.get(ws) or {})
    rec.update({k: (v or "").strip() for k, v in (answers or {}).items()})
    rec["saved_at"] = dt.datetime.now().isoformat(timespec="seconds")
    d[ws] = rec
    return _write_json(REVIEW_PATH, d)


def review_text(day=None):
    """周复盘纯文本（界面展示/复制/邮件用）。"""
    st = weekly_stats(day)
    plan = today_plan(day)
    names = {"read": "朗读", "improv": "即兴", "review": "复盘", "learn": "今日课+费曼"}
    lines = [
        "本周复盘（{0} ~ {1}）".format(st["week_start"], st["week_end"]),
        "打卡：本周 {0}/{1} 天（四段全做完 {2} 天）｜ 最近 7 天 {3}/7 天｜ 连续 {4} 天｜"
        "历史最长 {5} 天｜累计 {6} 天".format(
            st["practiced_days"], st["days_in_week"], st["full_days"], st["last7_days"],
            st["streak"], st["longest_streak"], st["total_days"]),
        "四段完成：" + "、".join(
            "{0} {1} 次".format(names.get(k, k), v) for k, v in st["per_block"].items()),
        "素材库：本周新增 {0} 条，累计 {1} 条（目标 20 故事 + 30 金句）".format(
            st["materials_week"], st["materials_total"]),
        "实战场景：本周完成 {0} 条，累计 {1} 条".format(
            st["scenarios_week"], st["scenarios_total"]),
        "本周主题：第 {0} 周 · {1}".format(plan["week"], plan["week_focus"]),
    ]
    if plan.get("week_pass"):
        lines.append("通过标准：" + plan["week_pass"])
    ref = get_reflection()
    lines.append("")
    for key, q in REVIEW_QUESTIONS:
        lines.append("· " + q)
        lines.append("  " + (ref.get(key) or "（未填写）"))
    return "\n".join(lines)


def stats():
    st = load_state()
    wk, winfo = week_info(st=st)
    ck = today_checkins(st=st)
    plan = today_plan(st=st)
    return {
        "start_date": st.get("start_date"),
        "week": wk, "week_focus": winfo.get("focus", ""),
        "streak": streak(st=st), "total_days": total_days(st=st),
        "today_done": len(ck), "today_total": len(plan.get("blocks") or []),
        "materials": {k: len(v) for k, v in materials().items()},
    }


def feynman_guide():
    for m in (load_practice().get("mechanisms") or []):
        if m.get("key") == "feynman":
            return m
    return {}


def main():
    ap = argparse.ArgumentParser(description="表达能力教练")
    ap.add_argument("--plan", action="store_true", help="打印今日练习计划")
    ap.add_argument("--stats", action="store_true", help="打印进度统计")
    ap.add_argument("--checkin", metavar="BLOCK", help="标记某段完成（read/improv/review/learn）")
    ap.add_argument("--lesson", action="store_true", help="打印今日课（模块轮换）")
    ap.add_argument("--review", action="store_true", help="打印本周复盘")
    a = ap.parse_args()

    if a.checkin:
        rec = checkin(a.checkin)
        print("已打卡:", json.dumps(rec, ensure_ascii=False))
        return 0
    if a.stats:
        print(json.dumps(stats(), ensure_ascii=False, indent=1))
        return 0
    if a.review:
        print(review_text())
        return 0
    if a.lesson:
        it, focus = lesson_of_day()
        print("[{0}] {1}\n  {2}".format(focus, (it or {}).get("t", ""),
                                        (it or {}).get("s", "")))
        return 0
    plan = today_plan()
    print("今日练习（{0} {1} · 第 {2} 周：{3}）共 {4} 分钟".format(
        plan["date"], plan["weekday"], plan["week"], plan["week_focus"],
        plan["total_minutes"]))
    if plan.get("week_twist"):
        print("本周加练：", plan["week_twist"])
    for b in plan["blocks"]:
        print("  [{0} 分钟] {1}：{2}".format(b.get("minutes"), b.get("name"),
                                             b.get("prompt") or b.get("how", "")[:40]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
