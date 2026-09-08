# -*- coding: utf-8 -*-
"""把 cache/today.json 导出成一份自包含的晨报网页（MorningBoard_web/index.html）。

用法：python tools/export_web.py
特点：单文件、离线可看、手机自适应、四套主题（沿用 app/ui/theme.py 的配色）。
"""
import datetime as dt
import html
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

CACHE = os.path.join(ROOT, "cache", "today.json")
OUT_DIR = os.path.join(os.path.dirname(ROOT), "MorningBoard_web")
OUT = os.path.join(OUT_DIR, "index.html")

# 新闻分组顺序（与桌面版一致）
ORDER = ["时政", "国内", "国际", "财经", "快讯"]


def classify(title):
    """复用桌面版分类逻辑；万一 import 失败则退回兜底。"""
    try:
        from app.ui.widgets import classify_news
        return classify_news(title) or "快讯"
    except Exception:  # noqa: BLE001
        t = title or ""
        for k in ("习近平", "中央", "国务院", "会议", "主席", "总理"):
            if k in t:
                return "时政"
        return "国内"


def esc(s):
    return html.escape(str(s if s is not None else ""))


def pct(v, digits=2):
    if v is None or v == "":
        return '<span class="flat">--</span>'
    try:
        f = float(v)
    except (TypeError, ValueError):
        return '<span class="flat">--</span>'
    cls = "up" if f > 0 else ("down" if f < 0 else "flat")
    sign = "+" if f > 0 else ""
    return '<span class="{}">{}{:.{}f}%</span>'.format(cls, sign, f, digits)


def num(v, digits=2):
    try:
        return "{:.{}f}".format(float(v), digits)
    except (TypeError, ValueError):
        return "--"


def spark(trend, w=108, h=30):
    """净值走势迷你图（内联 SVG，无外部依赖）。"""
    pts = [p for p in (trend or []) if isinstance(p, (list, tuple)) and len(p) >= 2]
    vals = []
    for p in pts:
        try:
            vals.append(float(p[1]))
        except (TypeError, ValueError):
            pass
    if len(vals) < 2:
        return ""
    mn, mx = min(vals), max(vals)
    rng = (mx - mn) or 1.0
    step = w / (len(vals) - 1)
    coords = " ".join(
        "{:.1f},{:.1f}".format(i * step, h - 2 - ((v - mn) / rng) * (h - 4))
        for i, v in enumerate(vals)
    )
    stroke = "var(--up)" if vals[-1] >= vals[0] else "var(--down)"
    return (
        '<svg class="spark" width="{w}" height="{h}" viewBox="0 0 {w} {h}" aria-hidden="true">'
        '<polyline points="{c}" fill="none" stroke="{s}" stroke-width="1.6" '
        'stroke-linejoin="round" stroke-linecap="round"/></svg>'
    ).format(w=w, h=h, c=coords, s=stroke)


# ---------------- 各板块渲染 ----------------

def render_news(news):
    items = news.get("items") or []
    if not items:
        return '<div class="empty">今日新闻暂未获取到</div>'
    groups = {}
    for it in items:
        groups.setdefault(classify(it.get("title", "")), []).append(it)
    out = []
    for cat in ORDER:
        arr = groups.pop(cat, [])
        if not arr:
            continue
        lis = []
        for it in arr:
            title = esc(it.get("title", ""))
            url = it.get("url") or ""
            if url:
                lis.append(
                    '<li><a href="{u}" target="_blank" rel="noopener">{t}</a></li>'.format(
                        u=esc(url), t=title
                    )
                )
            else:
                lis.append("<li>{}</li>".format(title))
        out.append(
            '<div class="group"><div class="ghead"><span class="gdot"></span>{c}'
            '<span class="gcount">{n}</span></div><ul class="glist">{l}</ul></div>'.format(
                c=esc(cat), n=len(arr), l="".join(lis)
            )
        )
    for cat, arr in groups.items():  # 兜底：未知分类
        lis = ["<li>{}</li>".format(esc(it.get("title", ""))) for it in arr]
        out.append(
            '<div class="group"><div class="ghead"><span class="gdot"></span>{c}'
            '<span class="gcount">{n}</span></div><ul class="glist">{l}</ul></div>'.format(
                c=esc(cat), n=len(arr), l="".join(lis)
            )
        )
    return "".join(out)


def render_tech(news):
    tech = news.get("tech") or {}
    items = tech.get("items") or []
    if not items:
        return ""
    lis = []
    for it in items[:10]:
        t = esc(it.get("title", ""))
        url = it.get("url") or ""
        src = it.get("source") or ""
        desc = it.get("desc") or ""
        block = '<a href="{u}" target="_blank" rel="noopener">{t}</a>'.format(u=esc(url), t=t) if url else t
        meta = " · ".join(x for x in (esc(src), esc(it.get("date", ""))) if x)
        lis.append(
            '<li><div class="tt">{b}</div>{d}{m}</li>'.format(
                b=block,
                d='<div class="td">{}</div>'.format(esc(desc)) if desc else "",
                m='<div class="tm">{}</div>'.format(meta) if meta else "",
            )
        )
    return '<ul class="techlist">{}</ul>'.format("".join(lis))


def render_funds(f):
    if not f:
        return ""
    parts = []
    idxs = f.get("indices") or []
    if idxs:
        cards = []
        for x in idxs:
            cards.append(
                '<div class="idx"><div class="iname">{n}</div>'
                '<div class="iprice">{p}</div><div class="ipct">{c}</div></div>'.format(
                    n=esc(x.get("name", "")), p=num(x.get("price")), c=pct(x.get("pct"))
                )
            )
        tone = f.get("market_tone")
        head = '<div class="shead">大盘指数{t}</div>'.format(
            t='<span class="chip chip-tone">{}</span>'.format(esc(tone)) if tone else ""
        )
        parts.append(head + '<div class="idxgrid">{}</div>'.format("".join(cards)))
    wl = f.get("watchlist") or []
    if wl:
        rows = []
        for x in wl:
            if x.get("error"):
                rows.append(
                    '<div class="fund"><div class="fmain"><div class="fname">{n}</div>'
                    '<div class="fmeta">数据暂不可用</div></div></div>'.format(n=esc(x.get("name", "")))
                )
                continue
            rows.append(
                '<div class="fund">'
                '<div class="fmain"><div class="fname">{n}</div>'
                '<div class="fmeta">{c} · 净值 {v}（{d}）</div></div>'
                '<div class="fspark">{s}</div>'
                '<div class="fnums">'
                '<div class="fn"><span class="lbl">日</span><span class="val">{day}</span></div>'
                '<div class="fn"><span class="lbl">周</span><span class="val">{w1}</span></div>'
                '<div class="fn"><span class="lbl">月</span><span class="val">{m1}</span></div>'
                "</div></div>".format(
                    n=esc(x.get("name", "")),
                    c=esc(x.get("code", "")),
                    v=num(x.get("nav"), 4),
                    d=esc(x.get("nav_date", "")),
                    s=spark(x.get("trend")),
                    day=pct(x.get("day_chg")),
                    w1=pct(x.get("w1")),
                    m1=pct(x.get("m1")),
                )
            )
        parts.append('<div class="shead">自选基金</div><div class="funds">{}</div>'.format("".join(rows)))
    return "".join(parts)


def render_lesson(l):
    if not l:
        return ""
    out = []
    main = l.get("main") or {}
    if main:
        body = "".join(
            "<p>{}</p>".format(esc(p)) for p in (main.get("body") or [])
        )
        links = "".join(
            '<span class="chip chip-soft">{}</span>'.format(esc(x)) for x in (main.get("links") or [])
        )
        out.append(
            '<div class="lcat">{cat} · 第 {i}/{t}</div>'
            '<h3 class="ltitle">{ti}</h3>'
            '<div class="lsub">{s}</div>'
            '<div class="lbody">{b}</div>'
            "{lk}".format(
                cat=esc(main.get("cat", "")),
                i=main.get("idx", 0) + 1 if isinstance(main.get("idx"), int) else 1,
                t=main.get("total", 1),
                ti=esc(main.get("title", "")),
                s=esc(main.get("sub", "")),
                b=body,
                lk='<div class="chips">{}</div>'.format(links) if links else "",
            )
        )
    quote = l.get("quote") or {}
    if quote.get("text"):
        out.append(
            '<div class="quote">“{t}”<span class="qauthor">—— {a}</span></div>'.format(
                t=esc(quote.get("text")), a=esc(quote.get("author") or "")
            )
        )
    cards = l.get("cards") or []
    if cards:
        inner = []
        for c in cards:
            b = "".join("<p>{}</p>".format(esc(p)) for p in (c.get("body") or [])[:3])
            inner.append(
                '<div class="kcard"><div class="kcat">{cat}</div>'
                '<div class="ktitle">{ti}</div><div class="ksub">{s}</div>'
                '<div class="kbody">{b}</div></div>'.format(
                    cat=esc(c.get("cat", "")),
                    ti=esc(c.get("title", "")),
                    s=esc(c.get("sub", "")),
                    b=b,
                )
            )
        out.append(
            '<details class="more"><summary>更多知识卡片（{n}）</summary>'
            '<div class="kcards">{c}</div></details>'.format(n=len(cards), c="".join(inner))
        )
    return "".join(out)


def render_thinking(t):
    if not t:
        return ""
    items = t.get("items") or []
    if not items:
        return '<div class="empty">今日思辨题暂未生成</div>'
    out = []
    for i, it in enumerate(items, 1):
        pro = "".join(
            '<li class="pro"><b>正方</b>{}</li>'.format(esc(p)) for p in (it.get("pro") or [])
        )
        con = "".join(
            '<li class="con"><b>反方</b>{}</li>'.format(esc(p)) for p in (it.get("con") or [])
        )
        ask = "".join('<li>{}</li>'.format(esc(p)) for p in (it.get("ask") or []))
        ref = ""
        if it.get("ref"):
            url = it.get("url") or ""
            txt = esc(it.get("ref"))
            ref = '<div class="ref">📎 依据热点：{r}</div>'.format(
                r='<a href="{u}" target="_blank" rel="noopener">{t}</a>'.format(u=esc(url), t=txt) if url else txt
            )
        out.append(
            '<div class="tk"><div class="tkh">思辨题 {i}</div>'
            '<div class="tkt">{t}</div><div class="tks">{s}</div>'
            '<ul class="tklist">{p}{c}</ul>'
            '{a}{r}</div>'.format(
                i=i,
                t=esc(it.get("t", "")),
                s=esc(it.get("s", "")),
                p=pro,
                c=con,
                a='<div class="tkask"><b>思考</b><ul>{}</ul></div>'.format(ask) if ask else "",
                r=ref,
            )
        )
    return "".join(out)


def render_expression(e):
    if not e or not (e.get("t") or e.get("b")):
        return '<div class="empty">今日表达课暂未生成</div>'
    body = "".join("<p>{}</p>".format(esc(p)) for p in (e.get("b") or []))
    return '<div class="ext">{t}</div><div class="exs">{s}</div><div class="exbody">{b}</div>'.format(
        t=esc(e.get("t", "")), s=esc(e.get("s", "")), b=body
    )


def render_weekly(w):
    if not w or not w.get("news_count"):
        return (
            '<div class="empty">本周总结还没生成<br>'
            '<span class="muted">每周日《新闻联播》播出后（约 20:00）自动生成，'
            "汇总本周八大主题与科技要闻</span></div>"
        )
    out = [
        '<div class="wrange">{r} · 梳理本周联播 {n} 条</div>'.format(
            r=esc(w.get("range", "")), n=w.get("news_count")
        )
    ]
    cats = w.get("cats") or []
    if cats:
        blocks = []
        for c in cats:
            lis = "".join("<li>{}</li>".format(esc(x)) for x in (c.get("items") or [])[:12])
            blocks.append(
                '<div class="wcat"><div class="wcname">{n}<span class="gcount">{c}</span></div>'
                '<ul class="glist">{l}</ul></div>'.format(
                    n=esc(c.get("cat", "")), c=len(c.get("items") or []), l=lis
                )
            )
        out.append('<div class="wcats">{}</div>'.format("".join(blocks)))
    idx = w.get("indices") or []
    if idx:
        cards = [
            '<div class="idx"><div class="iname">{n}</div><div class="ipct">{p}</div></div>'.format(
                n=esc(x.get("name", "")), p=pct(x.get("pct"))
            )
            for x in idx
        ]
        out.append('<div class="shead">本周指数涨跌</div><div class="idxgrid">{}</div>'.format("".join(cards)))
    media = w.get("media") or {}
    qb = media.get("qbitai") or []
    tc = media.get("tech") or []
    if qb or tc:
        lis = []
        for it in (qb + tc)[:14]:
            t = esc(it.get("title", ""))
            u = it.get("url") or it.get("link") or ""
            lis.append(
                "<li>{}</li>".format(
                    '<a href="{u}" target="_blank" rel="noopener">{t}</a>'.format(u=esc(u), t=t) if u else t
                )
            )
        out.append('<div class="shead">⚡ 本周科技要闻</div><ul class="glist">{}</ul>'.format("".join(lis)))
    return "".join(out)


# ---------------- 样式 / 脚本 ----------------

CSS = """
:root{--r:14px}
body[data-theme="morandi"]{--bg:#F4F1E8;--card:#FFFFFF;--ink:#2A2722;--sub:#6E685C;--line:#DCD4C2;
--accent:#9A4A3F;--teal:#33545C;--gold:#A98E4A;--up:#B03A2E;--down:#1E7A5A;--soft:#FBF5E7;--softline:#E4D5AC}
body[data-theme="dark"]{--bg:#1A1A1D;--card:#25252B;--ink:#E8E6E1;--sub:#A8A49C;--line:#3A3A44;
--accent:#E08A6E;--teal:#6FB3C4;--gold:#D9BC6A;--up:#E5484D;--down:#3FA85F;--soft:#2C2C34;--softline:#3E3E4A}
body[data-theme="mint"]{--bg:#E2F0E9;--card:#F8FCFA;--ink:#1F2A26;--sub:#567068;--line:#A8CFBE;
--accent:#2F7A63;--teal:#3D6B7A;--gold:#8A7A2E;--up:#C0392B;--down:#1E7A5A;--soft:#EAF5EF;--softline:#9CC9B5}
body[data-theme="contrast"]{--bg:#EAEAEA;--card:#FFFFFF;--ink:#000;--sub:#404040;--line:#000;
--accent:#C0392B;--teal:#1A5490;--gold:#7D6608;--up:#C0392B;--down:#0E7A46;--soft:#F5F5F5;--softline:#B0B0B0}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
font-family:system-ui,-apple-system,"Microsoft YaHei UI","PingFang SC",sans-serif;
font-size:15px;line-height:1.75;-webkit-font-smoothing:antialiased;transition:background .25s,color .25s}
a{color:inherit;text-decoration:none}
.wrap{max-width:760px;margin:0 auto;padding:20px 16px 56px}
header{position:sticky;top:0;z-index:9;background:var(--bg);padding:14px 0 10px;
border-bottom:1px solid var(--line);margin-bottom:18px}
.hrow{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.logo{width:38px;height:38px;border-radius:11px;background:var(--accent);color:#fff;
display:flex;align-items:center;justify-content:center;font-size:20px;font-weight:700;flex:none}
h1{font-size:20px;margin:0;font-weight:700;letter-spacing:.5px}
.hsub{color:var(--sub);font-size:12.5px}
.tbtn{margin-left:auto;background:var(--card);border:1px solid var(--line);color:var(--ink);
border-radius:999px;padding:6px 13px;font-size:12.5px;cursor:pointer;font-family:inherit}
.tbtn:hover{border-color:var(--accent);color:var(--accent)}
.card{background:var(--card);border:1px solid var(--line);border-radius:var(--r);
padding:18px;margin-bottom:16px}
.sec{margin-bottom:8px}
.stitle{font-size:16.5px;font-weight:700;display:flex;align-items:center;gap:8px;margin:0 0 12px}
.stitle .tag{margin-left:auto;font-size:11.5px;color:var(--sub);font-weight:400}
.shead{font-size:13px;color:var(--sub);margin:16px 0 10px;font-weight:600}
.ghead{display:flex;align-items:center;gap:7px;font-weight:600;font-size:13.5px;
color:var(--accent);margin:14px 0 6px}
.gdot{width:7px;height:7px;border-radius:50%;background:var(--accent);flex:none}
.gcount{margin-left:auto;color:var(--sub);font-size:11.5px;font-weight:400}
.glist{list-style:none;margin:0;padding:0}
.glist li{padding:7px 0;border-bottom:1px dashed var(--line);font-size:14.5px}
.glist li:last-child{border-bottom:none}
.glist a:hover{color:var(--accent);text-decoration:underline}
.empty{color:var(--sub);text-align:center;padding:26px 10px;font-size:14px}
.muted{color:var(--sub);font-size:12.5px}
.idxgrid{display:grid;grid-template-columns:repeat(4,1fr);gap:9px}
.idx{background:var(--soft);border:1px solid var(--softline);border-radius:10px;padding:9px 8px;text-align:center}
.iname{font-size:11.5px;color:var(--sub);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.iprice{font-size:15px;font-weight:700;margin:2px 0}
.ipct{font-size:12.5px;font-weight:600}
.up{color:var(--up)}.down{color:var(--down)}.flat{color:var(--sub)}
.funds{display:flex;flex-direction:column;gap:9px}
.fund{display:flex;align-items:center;gap:10px;background:var(--soft);
border:1px solid var(--softline);border-radius:10px;padding:10px 12px}
.fmain{flex:1;min-width:0}
.fname{font-size:14px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.fmeta{font-size:11.5px;color:var(--sub)}
.fspark{flex:none;opacity:.9}
.fnums{display:flex;gap:10px;flex:none}
.fn{text-align:center;font-size:11.5px}
.fn .lbl{display:block;color:var(--sub);font-size:10.5px}
.fn .val{font-weight:600}
.chips{display:flex;flex-wrap:wrap;gap:6px;margin-top:10px}
.chip{background:var(--soft);border:1px solid var(--softline);color:var(--sub);
border-radius:999px;padding:2px 10px;font-size:11.5px}
.chip-tone{margin-left:8px;background:transparent}
.lcat{font-size:12px;color:var(--teal);font-weight:600}
.ltitle{font-size:17px;margin:6px 0 4px;font-weight:700}
.lsub{color:var(--sub);font-size:13.5px}
.lbody p{margin:9px 0;font-size:14.5px}
.quote{margin-top:16px;padding:12px 14px;background:var(--soft);
border-left:3px solid var(--gold);border-radius:0 10px 10px 0;font-size:14px}
.qauthor{display:block;color:var(--sub);font-size:12.5px;margin-top:4px}
details.more{margin-top:14px;border-top:1px solid var(--line);padding-top:10px}
details.more summary{cursor:pointer;color:var(--sub);font-size:13px}
.kcards{display:grid;grid-template-columns:1fr;gap:10px;margin-top:12px}
.kcard{background:var(--soft);border:1px solid var(--softline);border-radius:10px;padding:12px}
.kcat{font-size:11.5px;color:var(--teal);font-weight:600}
.ktitle{font-weight:700;font-size:14.5px;margin:3px 0}
.ksub{color:var(--sub);font-size:12.5px}
.kbody p{margin:7px 0 0;font-size:13.5px;color:var(--sub)}
.tk{border:1px solid var(--line);border-radius:11px;padding:13px;margin-bottom:11px}
.tkh{font-size:12px;color:var(--accent);font-weight:600}
.tkt{font-size:15px;font-weight:700;margin:4px 0}
.tks{color:var(--sub);font-size:13px}
.tklist{list-style:none;margin:10px 0 0;padding:0}
.tklist li{font-size:13.5px;padding:6px 9px;border-radius:8px;margin-bottom:5px}
.tklist .pro{background:var(--soft)}
.tklist b{margin-right:6px;font-size:12px}
.tklist .pro b{color:var(--down)}
.tklist .con b{color:var(--up)}
.tkask{margin-top:9px;font-size:13.5px}
.tkask ul{margin:5px 0 0;padding-left:19px}
.tkask li{margin-bottom:3px}
.ref{margin-top:9px;font-size:12px;color:var(--sub)}
.ref a{color:var(--teal)}
.ext{font-size:16px;font-weight:700}
.exs{color:var(--sub);font-size:13.5px;margin-bottom:8px}
.exbody p{margin:9px 0;font-size:14.5px}
.wrange{font-size:13.5px;color:var(--sub);margin-bottom:12px}
.wcats{display:flex;flex-direction:column;gap:12px}
.wcname{font-weight:600;color:var(--accent);font-size:13.5px;display:flex;align-items:center}
.techlist{list-style:none;margin:0;padding:0}
.techlist li{padding:9px 0;border-bottom:1px dashed var(--line)}
.techlist li:last-child{border-bottom:none}
.tt{font-size:14.5px;font-weight:500}
.tt a:hover{color:var(--accent);text-decoration:underline}
.td{font-size:13px;color:var(--sub);margin-top:3px}
.tm{font-size:11.5px;color:var(--sub);margin-top:3px;opacity:.85}
footer{text-align:center;color:var(--sub);font-size:12px;margin-top:26px;line-height:1.9}
@media(max-width:520px){
 .wrap{padding:14px 12px 40px}
 .idxgrid{grid-template-columns:repeat(2,1fr)}
 .fspark{display:none}
 h1{font-size:18px}
}
"""

JS = """
var THEMES=['morandi','dark','mint','contrast'];
var NAMES={'morandi':'纸感莫兰迪','dark':'深色墨','mint':'护眼青','contrast':'高对比'};
var cur=localStorage.getItem('mb-theme')||'morandi';
if(THEMES.indexOf(cur)<0){cur='morandi';}
function apply(t){document.body.dataset.theme=t;localStorage.setItem('mb-theme',t);
  var el=document.getElementById('themeName');if(el){el.textContent=NAMES[t];}}
document.getElementById('themeBtn').onclick=function(){
  cur=THEMES[(THEMES.indexOf(cur)+1)%THEMES.length];apply(cur);};
apply(cur);
"""


def build():
    with open(CACHE, encoding="utf-8") as f:
        d = json.load(f)

    date = d.get("date") or ""
    weekday = d.get("weekday") or ""
    generated = (d.get("generated_at") or "").replace("T", " ")[:16]
    news = d.get("news") or {}
    funds = d.get("funds") or {}
    weekly = d.get("weekly") or {}
    lesson = d.get("lesson") or {}
    thinking = d.get("thinking") or {}
    expression = d.get("expression") or {}

    sections = []

    # 新闻联播
    tech_html = render_tech(news)
    sections.append(
        '<div class="card"><div class="stitle">📰 新闻联播'
        '<span class="tag">{dt} · {n} 条</span></div>{body}{tech}</div>'.format(
            dt=esc(news.get("date") or date),
            n=len(news.get("items") or []),
            body=render_news(news),
            tech='<div class="shead">🔬 科技栏</div>{}'.format(tech_html) if tech_html else "",
        )
    )

    # 行情
    fh = render_funds(funds)
    if fh:
        sections.append('<div class="card"><div class="stitle">📈 行情速览</div>{}</div>'.format(fh))

    # 今日一课
    sections.append(
        '<div class="card"><div class="stitle">📚 今日一课</div>{}</div>'.format(
            render_lesson(lesson) or '<div class="empty">今日课程暂未生成</div>'
        )
    )

    # 思辨
    sections.append(
        '<div class="card"><div class="stitle">🧠 思辨训练</div>{}</div>'.format(
            render_thinking(thinking) or '<div class="empty">今日思辨题暂未生成</div>'
        )
    )

    # 表达
    sections.append(
        '<div class="card"><div class="stitle">📣 表达课</div>{}</div>'.format(render_expression(expression))
    )

    # 每周总结
    sections.append(
        '<div class="card"><div class="stitle">🗓 每周总结</div>{}</div>'.format(render_weekly(weekly))
    )

    html_doc = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>每日晨报 · {date}</title>
<style>{css}</style>
</head>
<body data-theme="morandi">
<div class="wrap">
<header>
  <div class="hrow">
    <div class="logo">晨</div>
    <div>
      <h1>每日晨报</h1>
      <div class="hsub">{date} {weekday} · MorningBoard · 生成于 {gen}</div>
    </div>
    <button class="tbtn" id="themeBtn">🎨 <span id="themeName">纸感莫兰迪</span></button>
  </div>
</header>
{body}
<footer>
  数据来源：《新闻联播》央视网 · 腾讯行情 · InfoQ/量子位等 ·{gen2}<br>
  MorningBoard 自动生成 · 点击标题可跳转原文
</footer>
</div>
<script>{js}</script>
</body>
</html>
""".format(
        date=esc(date),
        weekday=esc(weekday),
        gen=esc(generated),
        gen2=(" 数据生成 " + esc(generated)) if generated else "",
        body="".join(sections),
        css=CSS,
        js=JS,
    )

    if not os.path.isdir(OUT_DIR):
        os.makedirs(OUT_DIR)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(html_doc)
    return OUT, len(html_doc), d


if __name__ == "__main__":
    path, size, d = build()
    print("已生成:", path)
    print("大小: {:.1f} KB".format(size / 1024.0))
    print("日期:", d.get("date"), "| 新闻", len((d.get("news") or {}).get("items") or []), "条")
