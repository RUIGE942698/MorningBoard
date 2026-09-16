# -*- coding: utf-8 -*-
"""邮件推送：把当日晨报渲染成手机友好的单文件 HTML 并发送到指定邮箱。

零第三方依赖（仅标准库 smtplib / email）。
邮箱配置见 config.json 的 "mail" 段：
  enabled / smtp_host / smtp_port / sender / to / auth_code / subject_prefix

用法：
    python -m app.mailer            用今日缓存发送一封（忽略 enabled，直接发）
    python -m app.mailer --to x@qq.com   指定收件人（测试用）
    python -m app.mailer --html     不发送，只渲染 HTML 到 cache/preview.html
"""
import html as _html
import json
import os
import re
import smtplib
import sys
import urllib.parse
from datetime import datetime
from email.header import Header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, formatdate

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app import config  # noqa: E402

RED = "#C0392B"    # 涨
GREEN = "#1E8449"  # 跌
INK = "#2A2722"
MUTED = "#8A8577"
BG = "#F4F1E8"
CARD = "#FFFFFF"
ACCENT = "#8C6B3F"
BORDER = "#E6E0D0"
FONT = "'PingFang SC','Hiragino Sans GB','Microsoft YaHei',sans-serif"

GLYPHS = "▁▂▃▄▅▆▇█"

# ------------------------------------------------- 邮件内容安全模式
# QQ 邮箱会对邮件正文做内容过滤，命中时整个投递被拒：
#   550 The mail may contain inappropriate words or content.
# 降级重发时打开安全模式：敏感词中性化 + 去掉所有外链，桌面版内容不受影响。
_MODE = {"mask": False, "nolink": False}

SENSITIVE_TERMS = [
    # 时政人物/机构
    "习近平", "李强", "李克强", "赵乐际", "王沪宁", "蔡奇", "丁薛祥", "李希", "韩正",
    "总书记", "主席", "总理", "委员长", "中共中央", "共产党", "中共", "国务院", "政治局",
    "中央军委", "国家主席", "全国人大", "全国政协",
    # 涉台涉疆涉藏
    "台湾", "新疆", "西藏", "藏独", "台独",
    # 案件/负面新闻
    "获刑", "判刑", "一审", "二审", "被捕", "刑拘", "落马", "反腐", "受贿", "行贿",
    "诈骗", "赌博", "涉毒", "毒品", "色情", "裸", "代孕", "枪击", "凶杀", "自杀",
    "暴恐", "暴乱", "示威", "游行", "上访", "维权", "打假", "网红", "铁头",
    "嫖", "卖淫", "走私", "洗钱", "黑产", "造假", "间谍", "泄露",
    # 网络工具类(常被误判)
    "翻墙", "VPN", "vpn", "破解", "盗版", "比特币", "虚拟币", "炒币", "博彩", "彩票",
]


def _neutralize(s):
    """把敏感词替换为等长 ×，保留句子可读性。"""
    out = str(s)
    for w in SENSITIVE_TERMS:
        if w in out:
            out = out.replace(w, "×" * len(w))
    return out


# ---------------------------------------------------------------- helpers
def _esc(s):
    s = str(s if s is not None else "")
    if _MODE["mask"]:
        s = _neutralize(s)
    return _html.escape(s, quote=False)


def _pct(v, suffix="%"):
    """数字 -> 带色涨跌文本。v 为数字（1.23 表示 1.23%）。"""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return '<span style="color:{0};">--</span>'.format(MUTED)
    s = ("+" if f > 0 else "") + format(f, ".2f") + suffix
    c = RED if f > 0 else (GREEN if f < 0 else MUTED)
    return '<span style="color:{0};font-weight:600;">{1}</span>'.format(c, s)


def _subj(payload, cfg):
    prefix = cfg.get("subject_prefix") or "每日晨报"
    return "{0} · {1} {2}".format(
        prefix, payload.get("date", ""), payload.get("weekday", "")
    )


def _spark(points):
    """[[date,value],...] -> 等宽字符迷你走势（邮件兼容，不依赖 SVG）。"""
    vals = [v for _, v in points if isinstance(v, (int, float))]
    if len(vals) < 2:
        return ""
    lo, hi = min(vals), max(vals)
    span = (hi - lo) or 1.0
    n = len(vals)
    step = max(1, n // 24)
    chars = []
    for i in range(0, n, step):
        k = int((vals[i] - lo) / span * (len(GLYPHS) - 1) + 0.5)
        chars.append(GLYPHS[max(0, min(len(GLYPHS) - 1, k))])
    return '<span title="{0:.4f} ~ {1:.4f}" style="color:#5A6B4A;' \
           'letter-spacing:1px;font-size:14px;">{2}</span>'.format(lo, hi, "".join(chars))


def _term_chip(term):
    """术语延伸：邮件里默认跳百度搜索（国内可达、免登录）。"""
    if _MODE["nolink"]:
        return ('<span style="display:inline-block;margin:2px 4px 2px 0;'
                'padding:1px 8px;border:1px solid {0};border-radius:10px;'
                'color:{0};font-size:12px;">{1}</span>').format(ACCENT, _esc(term))
    q = urllib.parse.quote(str(term))
    return ('<a href="https://www.baidu.com/s?wd={0}" style="display:inline-block;'
            'margin:2px 4px 2px 0;padding:1px 8px;border:1px solid {1};'
            'border-radius:10px;color:{1};text-decoration:none;font-size:12px;">'
            "{2}</a>").format(q, ACCENT, _esc(term))


def _chips(links):
    return '<div style="margin-top:6px;">' + "".join(
        _term_chip(x) for x in (links or [])
    ) + "</div>"


def _wrap(title, inner, badge=None):
    """一张白卡：标题行 + 内容。"""
    head = '<td style="padding:12px 16px 8px;font-size:16px;font-weight:700;' \
           'color:{0};">{1}'.format(INK, _esc(title))
    if badge:
        head += ' <span style="font-size:11px;font-weight:400;color:#fff;' \
                'background:{1};border-radius:8px;padding:1px 7px;' \
                'vertical-align:middle;">{0}</span>'.format(_esc(badge), ACCENT)
    head += "</td>"
    return ('<table width="100%" cellpadding="0" cellspacing="0" style="'
            'margin:10px 0;background:{1};border:1px solid {2};'
            'border-radius:10px;"><tr>{0}</tr>'
            '<tr><td style="padding:2px 16px 14px;font-size:14px;'
            'line-height:1.7;color:{3};">{4}</td></tr></table>').format(
        head, CARD, BORDER, INK, inner)


def _a(text, url, color=None):
    c = color or "#3B6FA0"
    if _MODE["nolink"]:
        # 安全模式第二轮：去掉所有外链（外链数量也是垃圾邮件判定因子）
        return '<span style="color:{0};">{1}</span>'.format(c, _esc(text))
    return '<a href="{0}" style="color:{1};text-decoration:none;">{2}</a>'.format(
        _esc(url), c, _esc(text))


# ---------------------------------------------------------------- sections
def _sec_news(p):
    news = p.get("news") or {}
    items = news.get("items") or []
    rows = []
    for i, it in enumerate(items, 1):
        t = it.get("title", "")
        u = it.get("url", "")
        rows.append(
            '<div style="padding:5px 0;border-bottom:1px dashed {0};">'
            '<span style="color:{1};font-weight:600;">{2}.</span>&nbsp;{3}'
            "</div>".format(BORDER, ACCENT, i, _a(t, u) if u else _esc(t))
        )
    if not rows:
        rows.append('<div style="color:{0};">今日联播暂未获取到节目单（'
                    '详见桌面版或稍后刷新）。</div>'.format(MUTED))
    return _wrap("📰 新闻联播 · 完整节目单", "".join(rows),
                 badge=str(len(items)) + " 条")


def _sec_tech(p):
    """前沿速报：分组展示 + 质量分 + 相对时间 + 摘要 + 延伸阅读（邮件版）。"""
    tech = ((p.get("news") or {}).get("tech")) or {}
    items = tech.get("items") or []
    sites = tech.get("sites") or []
    names = {"ai": "前沿 AI", "tech": "科技产业", "physics": "物理",
             "medicine": "医学", "biology": "生物", "math": "数学"}
    blocks = []
    if not items:
        blocks.append('<div style="color:{0};">今日前沿速报暂未抓到内容。</div>'.format(MUTED))
    cur = None
    for it in items:
        g = it.get("group") or "tech"
        if g != cur:
            cur = g
            blocks.append(
                '<div style="margin:10px 0 2px;font-weight:700;color:{0};">'
                '{1}</div>'.format(ACCENT, _esc(names.get(g, g))))
        src = _esc(it.get("source") or "")
        score = it.get("score")
        stars = ("★" * max(1, min(5, int(round((score or 0) / 20.0))))) if score else ""
        age = it.get("age_hours")
        if age is None:
            rel = ""
        elif age < 1:
            rel = "{0} 分钟前".format(int(age * 60))
        elif age < 48:
            rel = "{0} 小时前".format(int(round(age)))
        else:
            rel = "{0} 天前".format(int(age // 24))
        t = it.get("title", "")
        u = it.get("url", "")
        d = _esc((it.get("desc") or "")[:150])
        desc_html = ('<div style="color:#5A5544;font-size:12px;margin-top:2px;">'
                     '{0}</div>').format(d) if d else ""
        tag = ('<span style="display:inline-block;background:#EFE9DA;color:{0};'
               'border-radius:4px;padding:0 5px;font-size:11px;margin-right:6px;">'
               '{1}</span>').format(ACCENT, src) if src else ""
        _dl = ((it.get("explain") or {}).get("difficulty")) or ""
        _dtag = ('<span style="color:{0};font-size:11px;"> · {1}</span>'
                 .format(ACCENT, _esc(_dl))) if _dl else ""
        meta = ('<span style="color:{0};font-size:11px;">{1} {2} {3}</span>{4}'
                .format(MUTED, _esc(rel), score if score is not None else "", stars, _dtag))
        q = urllib.parse.quote(t)
        ext = " · ".join([x for x in [
            _a("原文", u) if u else "",
            _a("百度", "https://www.baidu.com/s?wd=" + q),
            _a("知乎", "https://www.zhihu.com/search?type=content&q=" + q),
            _a("学术", "https://xueshu.baidu.com/s?wd=" + q),
        ] if x])
        ex = it.get("explain") or {}
        ex_html = ""
        if ex.get("eli5"):
            ex_html += ('<div style="font-size:12px;color:{0};margin-top:3px;">'
                        '🧠 人话版：{1}</div>').format(INK, _esc(ex["eli5"]))
        tms = ex.get("terms") or []
        if tms:
            ex_html += ('<div style="font-size:11px;color:#6B6558;margin-top:2px;">'
                        '📘 {0}</div>').format(" · ".join(
                            "{0}：{1}".format(_esc(x.get("t")), _esc(x.get("d")))
                            for x in tms[:2]))
        if ex.get("why"):
            ex_html += ('<div style="font-size:11px;color:#6B6558;margin-top:2px;">'
                        '💡 {0}</div>').format(_esc(ex["why"]))
        pre = ex.get("prereq") or []
        if pre and ex.get("difficulty") == "专业":
            ex_html += ('<div style="font-size:11px;color:#8C6B3F;margin-top:2px;">'
                        '📎 先修：{0}</div>').format(" · ".join(
                            "{0}：{1}".format(_esc(x.get("t")), _esc(x.get("d")))
                            for x in pre[:2]))
        blocks.append(
            '<div style="padding:7px 0;border-bottom:1px dashed {0};">{1}{2}{3}{4}{5}'
            '<div style="font-size:11px;color:{6};margin-top:3px;">延伸阅读：{7}</div>'
            '</div>'.format(BORDER, tag, _a(t, u) if u else _esc(t), meta, desc_html,
                            ex_html, MUTED, ext)
        )
    vocab = tech.get("vocab_today") or []
    if vocab:
        blocks.append(
            '<div style="margin-top:10px;padding:8px 10px;background:#F7F3E9;'
            'border:1px solid {0};border-radius:8px;">'
            '<div style="font-weight:700;color:{1};font-size:13px;">📓 今日生词本'
            '（{2} 个新概念）</div><div style="font-size:12px;color:#5A5544;'
            'margin-top:4px;">{3}</div></div>'.format(
                BORDER, INK, len(vocab),
                "<br>".join("• {0}：{1}".format(_esc(v.get("t")), _esc(v.get("d")))
                            for v in vocab[:12])))
    chips = ""
    sites = [s for s in sites if s.get("name") and s.get("url")]
    if sites:
        chips = ('<div style="margin-top:8px;font-size:12px;color:{0};">'
                 '信源入口（点名称直达官网）：</div>').format(MUTED)
        cells = "".join(
            ('<span style="display:inline-block;margin:2px 4px 2px 0;padding:1px 8px;'
             'border:1px solid {0};border-radius:10px;font-size:12px;">{1}</span>').format(
                ACCENT, _a(s.get("name", ""), s.get("url", ""), ACCENT))
            for s in sites[:14])
        chips = chips + '<div style="margin-top:4px;">{0}</div>'.format(cells)
    upd = tech.get("updated_at") or ""
    badge = str(len(items)) + " 条"
    cons = tech.get("constraints") or {}
    if cons:
        badge += " · 一手 {0:.0%} · 48h内 {1:.0%}".format(
            cons.get("paper_ratio", 0), cons.get("fresh48_ratio", 0))
    if upd:
        badge += " · " + upd[11:16]
    return _wrap("⚡ 前沿速报 · AI / 科技 / 科学", "".join(blocks) + chips, badge=badge)


def _sec_funds(p):
    f = p.get("funds") or {}
    out = []
    tone = f.get("market_tone") or ""
    if tone:
        tcol = RED if ("涨" in str(tone)) else (GREEN if "跌" in str(tone) else MUTED)
        out.append('<div style="text-align:center;padding:8px 0;background:'
                   '#F7F3E9;border:1px solid {0};border-radius:8px;'
                   'margin-bottom:8px;font-weight:600;color:{1};">'
                   "今日市场 · {2}</div>".format(BORDER, tcol, _esc(tone)))

    # 指数表
    idxs = f.get("indices") or []
    if idxs:
        trs = []
        for it in idxs:
            trs.append(
                "<tr><td style='padding:4px 6px;color:{0};'>{1}</td>"
                "<td style='padding:4px 6px;text-align:right;'>{2}</td>"
                "<td style='padding:4px 6px;text-align:right;'>{3}</td>"
                "<td style='padding:4px 6px;text-align:right;'>{4}</td></tr>"
                .format(INK, _esc(it.get("name", "")),
                        _esc(it.get("price", "")), _pct(it.get("chg")),
                        _pct(it.get("pct")))
            )
        out.append(
            '<table width="100%" cellpadding="0" cellspacing="0" style='
            '"font-size:13px;">'
            '<tr style="color:{0};"><td style="padding:4px 6px;">指数</td>'
            "<td style='text-align:right;'>点位</td>"
            "<td style='text-align:right;'>涨跌</td>"
            "<td style='text-align:right;'>涨跌幅</td></tr>{1}</table>"
            .format(MUTED, "".join(trs))
        )

    # 自选基金
    wl = f.get("watchlist") or []
    if wl:
        blocks = []
        for it in wl:
            nm = _esc(it.get("name", it.get("code", "")))
            cd = _esc(str(it.get("code", "")))
            nav = it.get("nav")
            nav_txt = _esc(str(nav)) if nav is not None else "--"
            nd = _esc(str(it.get("nav_date", "")))
            err = it.get("error")
            trend = _spark(it.get("trend") or [])
            if err:
                blocks.append(
                    '<div style="padding:6px 0;border-bottom:1px dashed {0};'
                    'color:{1};">{2} <span style="color:#B03A2E;">（{3}）</span>'
                    "</div>".format(BORDER, INK, nm + " " + cd, _esc(err)))
                continue
            blocks.append(
                '<div style="padding:7px 0;border-bottom:1px dashed {0};">'
                '<div style="font-weight:600;">{1} <span style="color:{2};'
                'font-size:12px;font-weight:400;">{3}</span></div>'
                '<div style="font-size:12px;color:{2};">净值 {4} · {5}'
                '&nbsp;&nbsp;日 {6} &nbsp;周 {7} &nbsp;月 {8} &nbsp;3月 {9}'
                "</div><div style='margin-top:3px;'>{10}</div></div>"
                .format(BORDER, nm, MUTED, cd, nav_txt, nd,
                        _pct(it.get("day_chg")), _pct(it.get("w1")),
                        _pct(it.get("m1")), _pct(it.get("m3")), trend)
            )
        out.append('<div style="margin-top:10px;font-size:15px;font-weight:'
                   "700;color:{0};\">自选基金</div>".format(INK))
        out.append("".join(blocks))

    # 今日涨幅榜
    tg = f.get("top_gainers") or []
    if tg:
        rows = []
        for i, it in enumerate(tg, 1):
            rows.append(
                '<div style="padding:4px 0;font-size:13px;"><span style='
                '"color:{0};font-weight:600;\">{1}.</span> {2} '
                '<span style="color:{3};">{4}</span> <span style="color:{5};'
                'font-size:11px;">{6}</span></div>'.format(
                    ACCENT, i, _esc(it.get("name", "")),
                    _esc(str(it.get("code", ""))), _pct(it.get("day")),
                    MUTED, _esc(str(it.get("date", ""))))
            )
        out.append('<div style="margin-top:10px;font-size:15px;font-weight:'
                   "700;color:{0};\">今日基金涨幅榜 TOP</div>".format(INK))
        out.append("".join(rows))

    if f.get("index_error"):
        out.append('<div style="color:#B03A2E;font-size:12px;margin-top:6px;">'
                   "部分行情源失败：{0}</div>".format(_esc(f["index_error"])))
    return _wrap("📈 基金投资", "".join(out))


def _sec_lesson(p):
    L = p.get("lesson") or {}
    out = []
    main = L.get("main")
    if isinstance(main, dict):
        head = '<div style="font-size:17px;font-weight:700;">{0}</div>'.format(
            _esc(main.get("title", "")))
        if main.get("sub"):
            head += '<div style="color:{0};margin:3px 0 6px;">{1}</div>'.format(
                ACCENT, _esc(main["sub"]))
        body = "".join(
            "<p style='margin:6px 0;'>{0}</p>".format(_esc(x))
            for x in (main.get("body") or [])
        )
        out.append(head + body + _chips(main.get("links")))

    quote = L.get("quote")
    if quote:
        if isinstance(quote, dict):
            qt = _esc(quote.get("text", ""))
            qa = _esc(quote.get("author", ""))
        else:
            qt, qa = _esc(quote), ""
        out.append('<div style="margin:10px 0;padding:8px 12px;background:'
                   '#F7F3E9;border-left:3px solid {0};color:#5A5544;">'
                   "“{1}”{2}</div>".format(
                       ACCENT, qt, (" —— " + qa) if qa else ""))

    cards = L.get("cards") or []
    if cards:
        out.append('<div style="margin-top:8px;color:{0};font-size:13px;">'
                   "—— 今日小卡 · 共 {1} 张（完整见桌面版）——</div>"
                   .format(MUTED, len(cards)))
        for c in cards[:6]:
            cat = _esc(c.get("cat", ""))
            tt = _esc(c.get("title", ""))
            sb = _esc(c.get("sub", ""))
            b0 = _esc((c.get("body") or [""])[0])[:110]
            out.append(
                '<div style="padding:7px 0;border-bottom:1px dashed {0};">'
                '<span style="display:inline-block;background:#EFE9DA;color:'
                '{1};border-radius:4px;padding:0 5px;font-size:11px;'
                'margin-right:5px;">{2}</span><span style="font-weight:600;">'
                "{3}</span><div style='color:#5A5544;font-size:13px;"
                "margin-top:2px;'>{4} {5}</div></div>".format(
                    BORDER, ACCENT, cat, tt, sb,
                    ("…" if b0 else "") + b0)
            )
        if len(cards) > 6:
            out.append('<div style="color:{0};font-size:12px;margin-top:4px;">'
                       "其余 {1} 张在桌面版「每日一课」可看。</div>"
                       .format(MUTED, len(cards) - 6))
    return _wrap("📚 每日一课 · " + _esc(str(L.get("main_cat", ""))),
                 "".join(out),
                 badge="AI 生成" if L.get("ai_generated") else "知识库")


def _sec_thinking(p):
    th = p.get("thinking") or {}
    items = th.get("items") or []
    if not items:
        return ""
    out = []
    for it in items:
        t = _esc(it.get("t", ""))
        s = _esc(it.get("s", ""))
        rows = [('<div style="font-weight:700;">{0}</div>'
                 '<div style="color:#5A5544;margin:2px 0 6px;">{1}</div>'
                 .format(t, s))]
        for lab, key, col in (("正方观点", "pro", RED),
                              ("反方观点", "con", GREEN),
                              ("思考题", "ask", ACCENT)):
            v = it.get(key)
            if v:
                rows.append('<div style="margin:4px 0;"><span style="color:{1};'
                            "font-weight:600;\">{0}：</span>{2}</div>"
                            .format(lab, col, _esc(v)))
        rows.append(_chips(it.get("links")))
        out.append('<div style="padding:8px 0;border-bottom:1px dashed {0};">'
                   "{1}</div>".format(BORDER, "".join(rows)))
    return _wrap("🧠 思辨训练", "".join(out),
                 badge="AI 出题" if th.get("ai") else "")


def _practice_block():
    """邮件里的「今日 20 分钟练习」+ 12 周进度（表达能力模块专用）。"""
    try:
        from app import expression_coach as coach
        plan = coach.today_plan()
        ck = coach.today_checkins()
    except Exception:  # noqa: BLE001
        return ""
    rows = []
    for b in plan.get("blocks") or []:
        mark = "✅" if ck.get(b.get("key")) else "⬜"
        rows.append(
            '<div style="padding:4px 0;border-bottom:1px dashed {0};">'
            '<span style="font-weight:600;">{1} {2}（{3} 分钟）</span>'
            '<div style="color:#5A5544;font-size:13px;">{4}</div></div>'.format(
                BORDER, mark, _esc(b.get("name", "")), b.get("minutes"),
                _esc(b.get("prompt") or b.get("how", ""))))
    st = coach.weekly_stats()
    head = ('<div style="font-weight:700;margin:4px 0 2px;">🎯 今日练习'
            '（{0} 分钟 · 第 {1} 周 {2} · 连续打卡 {3} 天）</div>').format(
        plan.get("total_minutes"), plan.get("week"),
        _esc(plan.get("week_focus", "")), coach.streak())
    head += ('<div style="color:#5A5544;font-size:12px;">📅 本周打卡 {0}/{1} 天 ｜ '
             '最近 7 天 {2}/7 天 ｜ 历史最长连续 {3} 天 ｜ 素材 {4} 条 ｜ '
             '实战场景 {5} 条</div>').format(
        st.get("practiced_days"), st.get("days_in_week"), st.get("last7_days"),
        st.get("longest_streak"), st.get("materials_total"), st.get("scenarios_total"))
    twist = ""
    if plan.get("week_twist"):
        twist = ('<div style="margin-top:6px;color:{0};font-size:13px;">'
                 "📌 本周加练：{1}</div>").format(ACCENT, _esc(plan["week_twist"]))
    return head + "".join(rows) + twist


def _sec_expression(p):
    ex = p.get("expression")
    if not ex or not isinstance(ex, dict):
        return ""
    t = _esc(str(ex.get("t", ""))).replace("技巧名：", "")
    s = _esc(ex.get("s", ""))
    body = "".join(
        "<p style='margin:6px 0;'>{0}</p>".format(_esc(x))
        for x in (ex.get("b") or [])
    )
    head = '<div style="font-size:16px;font-weight:700;">{0}</div>'.format(t)
    if s:
        head += '<div style="color:{0};margin:2px 0 6px;">{1}</div>'.format(
            ACCENT, s)
    drill = ex.get("drill")
    if drill:
        head += ('<div style="margin:6px 0;padding:6px 10px;background:#F7F3E9;'
                 'border-left:3px solid {0};font-size:13px;">🎯 今天就用出去：'
                 "{1}</div>").format(ACCENT, _esc(drill))
    practice = _practice_block()
    if practice:
        head += ('<div style="margin-top:8px;padding-top:6px;border-top:1px '
                 'solid {0};">{1}</div>').format(BORDER, practice)
    return _wrap("📣 表达能力", head + body)


def _expression_review_block():
    """周日邮件里附「表达能力周复盘」全文。"""
    try:
        from app import expression_coach as coach
        if dt.date.today().weekday() != 6:      # 仅周日
            return ""
        txt = coach.review_text()
    except Exception:  # noqa: BLE001
        return ""
    body = "".join("<p style='margin:4px 0;'>{0}</p>".format(_esc(x))
                   for x in txt.split("\n") if x.strip())
    return _wrap("📅 表达能力 · 本周复盘", body)


def _sec_weekly(p):
    w = p.get("weekly")
    if not w or not isinstance(w, dict):
        return ""
    out = []
    out.append('<div style="color:{0};font-size:13px;">{1} · 联播 {2} 条'
               "</div>".format(MUTED, _esc(w.get("range", "")),
                               w.get("news_count", "")))
    idxw = w.get("indices") or []
    if idxw:
        out.append('<div style="margin-top:8px;font-weight:700;">指数周涨跌'
                   "</div>")
        for it in idxw:
            out.append('<div style="padding:3px 0;font-size:13px;">{0} '
                       "{1}</div>".format(_esc(it.get("name", "")),
                                          _pct(it.get("pct", it.get("chg")))))
    for g in w.get("cats") or []:
        cat = _esc(g.get("cat", ""))
        its = g.get("items") or []
        body = "<div style='margin-top:6px;font-weight:700;'>{0}（{1}）</div>" \
               .format(cat, len(its))
        body += "".join(
            '<div style="padding:2px 0;font-size:13px;color:#4A463C;">· {0}'
            "</div>".format(_esc(x)) for x in its
        )
        out.append(body)
    return _wrap("🗓 每周总结", "".join(out))


# ---------------------------------------------------------------- assemble
def build_html(payload):
    """today.json 结构 -> 单文件邮件 HTML（UTF-8，内联样式）。"""
    date = _esc(payload.get("date", ""))
    weekday = _esc(payload.get("weekday", ""))
    gen = _esc(str(payload.get("generated_at", "")))[:16]
    ai_note = ""
    if (payload.get("lesson") or {}).get("ai_generated"):
        ai_note = ("（今日一课/思辨题由 AI 动态生成，正文为当日实时内容）")
    head = (
        '<div style="font-size:20px;font-weight:800;color:{0};">'
        "📮 每日晨报 <span style='font-size:14px;color:{1};'>"
        "{2} {3}</span></div>"
        '<div style="color:{1};font-size:12px;margin:4px 0 2px;">'
        "生成于 {4} · 每晚 20:00 自动推送 · 手机阅读版{5}</div>"
    ).format(INK, MUTED, date, weekday, gen, ai_note)

    secs = [
        _sec_news(payload),
        _sec_tech(payload),
        _sec_funds(payload),
        _sec_lesson(payload),
        _sec_thinking(payload),
        _sec_expression(payload),
        _expression_review_block(),
        _sec_weekly(payload),
    ]
    foot = (
        '<div style="color:{0};font-size:11px;line-height:1.8;padding:6px 0 '
        '16px;text-align:center;">—— 每日晨报 · 电脑端生成后自动推送 ——<br>'
        "术语延伸默认打开百度搜索；想看可交互的完整 8 板块，请在电脑上打开"
        "桌面版应用。</div>"
    ).format(MUTED)

    return (
        '<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>每日晨报</title></head>'
        '<body style="margin:0;padding:0;background:{0};font-family:{1};">'
        '<table width="100%" cellpadding="0" cellspacing="0" style='
        '"background:{0};\"><tr><td align="center"><table width="100%" '
        'cellpadding="0" cellspacing="0" style="max-width:680px;'
        'padding:12px 10px;">'
        "<tr><td style='padding:10px 6px;'>{2}</td></tr>"
        "<tr><td>{3}</td></tr>"
        "<tr><td>{4}</td></tr>"
        "</table></td></tr></table></body></html>"
    ).format(BG, FONT, head, "".join(secs), foot)


# ---------------------------------------------------------------- send
def _log(msg):
    try:
        logp = os.path.join(config.CACHE_DIR, "mail.log")
        with open(logp, "a", encoding="utf-8") as f:
            f.write("{0}  {1}\n".format(
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"), msg))
        lines = open(logp, encoding="utf-8").read().splitlines()
        if len(lines) > 300:
            with open(logp, "w", encoding="utf-8") as f:
                f.write("\n".join(lines[-200:]) + "\n")
    except Exception:
        pass


def _split_recipients(raw):
    """收件人支持多个：逗号/分号/空格/中文逗号分隔，自动去重。"""
    out = []
    for part in re.split(r"[,;，；\s]+", raw or ""):
        part = part.strip()
        if part and part not in out:
            out.append(part)
    return out


def _is_content_reject(err):
    """判断是否为邮箱内容过滤拒绝（只有这类错误才值得降级重发）。"""
    s = str(err).lower()
    return ("550" in s) or ("inappropriate" in s) or ("content" in s)


def _build_text(payload, safe=True):
    """纯文本摘要（最后降级手段）：无 HTML、无外链、极简。"""
    old = dict(_MODE)
    _MODE["mask"] = safe
    _MODE["nolink"] = True
    try:
        def T(s):
            s = str(s or "")
            return _neutralize(s) if safe else s
        lines = []
        lines.append("每日晨报 · {0} {1}".format(payload.get("date", ""),
                                            payload.get("weekday", "")))
        lines.append("（因邮箱内容过滤，本条为纯文本摘要；完整版请打开电脑上的每日播报）")
        lines.append("")
        news = payload.get("news") or {}
        items = (news.get("items") or [])[:12]
        if items:
            lines.append("【新闻联播】")
            for i, it in enumerate(items, 1):
                lines.append("{0}. {1}".format(i, T(it.get("title", ""))))
            lines.append("")
        tech = ((news.get("tech")) or {}).get("items") or []
        if tech:
            lines.append("【科技前沿】")
            for it in tech[:6]:
                lines.append("· " + T(it.get("title", "")))
            lines.append("")
        f = payload.get("funds") or {}
        tone = f.get("market_tone") or ""
        if tone:
            lines.append("【市场】" + T(tone))
        for it in (f.get("indices") or [])[:6]:
            lines.append("  {0} {1} {2}%".format(it.get("name", ""),
                                                 it.get("price", ""),
                                                 it.get("pct", "")))
        lines.append("")
        L = payload.get("lesson") or {}
        main = L.get("main") if isinstance(L.get("main"), dict) else None
        if main:
            lines.append("【每日一课】" + T(main.get("title", "")))
        th = payload.get("thinking") or {}
        for it in (th.get("items") or [])[:3]:
            lines.append("【思辨】" + T(it.get("t", "")))
        lines.append("")
        lines.append("—— 每日晨报 · 电脑端生成 ——")
        return "\n".join(lines)
    finally:
        _MODE.update(old)


def _variants(payload):
    """按"保真度"从高到低生成降级方案。"""
    out = []
    for name, mask, nolink in (("full", False, False),
                               ("safe", True, False),
                               ("safe-nolink", True, True)):
        _MODE["mask"] = mask
        _MODE["nolink"] = nolink
        out.append((name, build_html(payload), None))
    _MODE["mask"] = False
    _MODE["nolink"] = False
    out.append(("plain", None, _build_text(payload, safe=True)))
    return out


def _smtp_send(cfg, recipients, subject, html_body, text_body):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = Header(subject, "utf-8")
    msg["From"] = formataddr((str(Header("每日晨报", "utf-8")),
                              cfg.get("sender", "")))
    msg["To"] = ", ".join(recipients)
    msg["Date"] = formatdate(localtime=True)
    if text_body:
        msg.attach(MIMEText(text_body, "plain", "utf-8"))
    if html_body:
        msg.attach(MIMEText(html_body, "html", "utf-8"))
    srv = smtplib.SMTP_SSL(cfg.get("smtp_host", "smtp.qq.com"),
                           int(cfg.get("smtp_port", 465)), timeout=40)
    try:
        srv.login(cfg.get("sender", ""), cfg.get("auth_code", ""))
        srv.sendmail(cfg.get("sender", ""), recipients, msg.as_string())
    finally:
        try:
            srv.quit()
        except Exception:
            pass


def send_report(payload, to=None, cfg=None, mode=None):
    """渲染并发送（可多收件人）。成功返回 True；失败抛异常。

    QQ 邮箱内容过滤（550 inappropriate words）时自动降级重发：
      full(原样) -> safe(敏感词中性化) -> safe-nolink(再去外链) -> plain(纯文本摘要)
    """
    cfg = cfg or config.load_config().get("mail") or {}
    if not cfg.get("auth_code"):
        raise RuntimeError("mail.auth_code 未配置，跳过发送")
    recipients = _split_recipients(to or cfg.get("to"))
    if not recipients:
        raise RuntimeError("mail.to 未配置，无法发送")
    subject = _subj(payload, cfg)

    variants = _variants(payload)
    if mode:
        picked = [v for v in variants if v[0] == mode]
        variants = picked or variants
    last_err = None
    for name, html_body, text_body in variants:
        try:
            _smtp_send(cfg, recipients, subject, html_body, text_body)
            _log("sent to {0} | mode={1} | subject: {2}".format(
                ", ".join(recipients), name, subject))
            return True
        except Exception as e:  # noqa: BLE001
            last_err = e
            _log("attempt {0} FAIL: {1}".format(name, e))
            if not _is_content_reject(e):
                break  # 认证/网络类错误，降级重发无意义
    raise last_err if last_err is not None else RuntimeError("发送失败")


def send_daily(payload):
    """供每晚任务调用：enabled 才发，任何失败只记日志不抛出。"""
    cfg = config.load_config().get("mail") or {}
    if not cfg.get("enabled"):
        _log("mail disabled, skip")
        return False
    try:
        return send_report(payload)
    except Exception as e:  # noqa: BLE001
        _log("FAIL: {0}".format(e))
        return False


def main():
    args = [a for a in sys.argv[1:]]
    payload = None
    try:
        with open(config.TODAY_PATH, encoding="utf-8") as f:
            payload = json.load(f)
    except Exception as e:
        print("无法读取今日缓存:", e)
        return 2
    html_body = build_html(payload)
    if "--html" in args:
        out = os.path.join(config.CACHE_DIR, "preview.html")
        with open(out, "w", encoding="utf-8") as f:
            f.write(html_body)
        print("[OK] HTML preview ->", out, "({0} bytes)".format(len(html_body)))
        return 0
    to = None
    if "--to" in args:
        to = args[args.index("--to") + 1]
    try:
        ok = send_report(payload, to=to)
        print("[OK] sent:", ok)
        return 0
    except Exception as e:  # noqa: BLE001
        print("[FAIL]", e)
        return 1


if __name__ == "__main__":
    sys.exit(main())
