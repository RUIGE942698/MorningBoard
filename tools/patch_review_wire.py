# -*- coding: utf-8 -*-
"""补充「最近 7 天」口径 + 接到界面与邮件。"""
import io
import os
import shutil

ROOT = r'C:\Users\lenovo\Desktop\压缩包\MorningBoard'
os.chdir(ROOT)

# ---------- 1) coach：最近 7 天统计 ----------
P = 'app/expression_coach.py'
src = io.open(P, encoding='utf-8').read()
old = '''    mats = materials()
    mat_week = sum(1 for kind in mats for x in mats[kind]
                   if _mat_date(x) and start.isoformat() <= _mat_date(x) <= end.isoformat())'''
new = '''    # 最近 7 天（含今天）滚动口径：周中复盘也有意义
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
                   if _mat_date(x) and start.isoformat() <= _mat_date(x) <= end.isoformat())'''
assert src.count(old) == 1
src = src.replace(old, new, 1)

old2 = '''        "practiced_days": practiced_days, "full_days": full_days,
        "per_block": per_block, "block_keys": block_keys,'''
new2 = '''        "practiced_days": practiced_days, "full_days": full_days,
        "per_block": per_block, "block_keys": block_keys,
        "last7_days": days7, "per_block7": per_block7,'''
assert src.count(old2) == 1
src = src.replace(old2, new2, 1)

old3 = '''        "打卡：{0}/{1} 天（四段全做完 {2} 天）｜ 连续 {3} 天｜历史最长 {4} 天｜累计 {5} 天".format(
            st["practiced_days"], st["days_in_week"], st["full_days"],
            st["streak"], st["longest_streak"], st["total_days"]),'''
new3 = '''        "打卡：本周 {0}/{1} 天（四段全做完 {2} 天）｜ 最近 7 天 {3}/7 天｜ 连续 {4} 天｜"
        "历史最长 {5} 天｜累计 {6} 天".format(
            st["practiced_days"], st["days_in_week"], st["full_days"], st["last7_days"],
            st["streak"], st["longest_streak"], st["total_days"]),'''
assert src.count(old3) == 1
src = src.replace(old3, new3, 1)

shutil.copy2(P, P + '.bak_review7')
io.open(P, 'w', encoding='utf-8').write(src)
import py_compile  # noqa: E402
py_compile.compile(P, doraise=True)
print('coach: 已加最近 7 天口径，语法 OK（备份 .bak_review7）')

# ---------- 2) 邮件：练习卡片里加一行本周统计 ----------
M = 'app/mailer.py'
ms = io.open(M, encoding='utf-8').read()
oldm = '''    head = ('<div style="font-weight:700;margin:4px 0 2px;">🎯 今日练习'
            '（{0} 分钟 · 第 {1} 周 {2} · 连续打卡 {3} 天）</div>').format(
        plan.get("total_minutes"), plan.get("week"),
        _esc(plan.get("week_focus", "")), coach.streak())'''
newm = '''    st = coach.weekly_stats()
    head = ('<div style="font-weight:700;margin:4px 0 2px;">🎯 今日练习'
            '（{0} 分钟 · 第 {1} 周 {2} · 连续打卡 {3} 天）</div>').format(
        plan.get("total_minutes"), plan.get("week"),
        _esc(plan.get("week_focus", "")), coach.streak())
    head += ('<div style="color:#5A5544;font-size:12px;">📅 本周打卡 {0}/{1} 天 ｜ '
             '最近 7 天 {2}/7 天 ｜ 历史最长连续 {3} 天 ｜ 素材 {4} 条 ｜ '
             '实战场景 {5} 条</div>').format(
        st.get("practiced_days"), st.get("days_in_week"), st.get("last7_days"),
        st.get("longest_streak"), st.get("materials_total"), st.get("scenarios_total"))'''
assert ms.count(oldm) == 1
ms = ms.replace(oldm, newm, 1)

# 周日邮件附完整复盘
oldw = '''def _sec_weekly(p):'''
neww = '''def _expression_review_block():
    """周日邮件里附「表达能力周复盘」全文。"""
    try:
        from app import expression_coach as coach
        if dt.date.today().weekday() != 6:      # 仅周日
            return ""
        txt = coach.review_text()
    except Exception:  # noqa: BLE001
        return ""
    body = "".join("<p style='margin:4px 0;'>{0}</p>".format(_esc(x))
                   for x in txt.split("\\n") if x.strip())
    return _wrap("📅 表达能力 · 本周复盘", body)


def _sec_weekly(p):'''
assert ms.count(oldw) == 1
ms = ms.replace(oldw, neww, 1)

olds = '''        _sec_expression(payload),'''
news = '''        _sec_expression(payload),
        _expression_review_block(),'''
assert ms.count(olds) == 1
ms = ms.replace(olds, news, 1)

shutil.copy2(M, M + '.bak_review')
io.open(M, 'w', encoding='utf-8').write(ms)
py_compile.compile(M, doraise=True)
print('mailer: 已加练习统计行 + 周日复盘块，语法 OK（备份 .bak_review）')
