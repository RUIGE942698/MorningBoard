# -*- coding: utf-8 -*-
"""给表达能力模块加「每周复盘」能力。

改动（app/expression_coach.py）：
  1) 素材库条目带时间戳（兼容旧的无时间戳纯字符串）
  2) 场景清单完成时记录日期；四层自评记录历史（用于看变化）
  3) 新增：week_bounds / longest_streak / weekly_stats / 三问复盘存取 / review_text
  4) CLI 增加 --review
备份 .bak_review，逐项断言。
"""
import io
import os
import shutil

ROOT = r'C:\Users\lenovo\Desktop\压缩包\MorningBoard'
os.chdir(ROOT)
P = 'app/expression_coach.py'
src = io.open(P, encoding='utf-8').read()
orig = src


def sub(old, new, label):
    global src
    n = src.count(old)
    assert n == 1, '[%s] 锚点命中 %d 次' % (label, n)
    src = src.replace(old, new, 1)
    print('  OK', label)


# ---------- 1) 素材库带时间戳 ----------
sub('''def materials():
    d = _read_json(MATERIALS_PATH, {}) or {}
    d.setdefault("quotes", [])
    d.setdefault("stories", [])
    d.setdefault("data", [])
    return d
''', '''def materials():
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
''', 'materials 结构')

sub('''def add_material(kind, text):
    kind = kind if kind in ("quotes", "stories", "data") else "quotes"
    text = (text or "").strip()
    if not text:
        return False
    d = materials()
    if text not in d[kind]:
        d[kind].append(text)
    return _write_json(MATERIALS_PATH, d)


def remove_material(kind, text):
    d = materials()
    if kind in d and text in d[kind]:
        d[kind].remove(text)
        return _write_json(MATERIALS_PATH, d)
    return False''', '''def add_material(kind, text):
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
    return False''', 'add/remove_material')

# ---------- 2) 场景与自评留痕 ----------
sub('''def toggle_scenario(key):
    st = load_state()
    cur = bool((st.get("scenarios") or {}).get(key))
    st.setdefault("scenarios", {})[key] = not cur
    save_state(st)
    return not cur''', '''def toggle_scenario(key):
    st = load_state()
    cur = bool((st.get("scenarios") or {}).get(key))
    st.setdefault("scenarios", {})[key] = not cur
    if not cur:                      # 完成时记日期（用于周复盘）
        st.setdefault("scenario_log", {})[key] = dt.date.today().isoformat()
    save_state(st)
    return not cur''', 'toggle_scenario 记日期')

sub('''def set_rating(level, value=True):
    st = load_state()
    st.setdefault("rating", {})[str(level)] = bool(value)
    save_state(st)
    return st["rating"]''', '''def set_rating(level, value=True):
    st = load_state()
    key = str(level)
    st.setdefault("rating", {})[key] = bool(value)
    hist = st.setdefault("rating_history", [])
    hist.append({"date": dt.date.today().isoformat(), "level": key, "value": bool(value)})
    st["rating_history"] = hist[-200:]
    save_state(st)
    return st["rating"]''', 'set_rating 记历史')

# ---------- 3) 复盘统计 ----------
sub('''def stats():''', '''def week_bounds(day=None):
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
        "打卡：{0}/{1} 天（四段全做完 {2} 天）｜ 连续 {3} 天｜历史最长 {4} 天｜累计 {5} 天".format(
            st["practiced_days"], st["days_in_week"], st["full_days"],
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
    return "\\n".join(lines)


def stats():''', '复盘统计与文本')

# ---------- 4) CLI ----------
sub('''    ap.add_argument("--lesson", action="store_true", help="打印今日课（模块轮换）")''',
    '''    ap.add_argument("--lesson", action="store_true", help="打印今日课（模块轮换）")
    ap.add_argument("--review", action="store_true", help="打印本周复盘")''',
    'CLI --review 参数')

sub('''    if a.lesson:''', '''    if a.review:
        print(review_text())
        return 0
    if a.lesson:''', 'CLI --review 分支')

assert src != orig
shutil.copy2(P, P + '.bak_review')
io.open(P, 'w', encoding='utf-8').write(src)
print('\n已写入，备份 ->', P + '.bak_review')

import py_compile  # noqa: E402
py_compile.compile(P, doraise=True)
print('语法 OK')
