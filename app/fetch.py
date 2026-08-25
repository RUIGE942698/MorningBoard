# -*- coding: utf-8 -*-
"""数据抓取层：新闻联播 + 大盘指数（国内/海外，多源备援）+ 基金净值/走势 + 涨幅榜。

全部走公开接口，零第三方依赖（仅标准库）。
"""
import datetime as dt
import email.utils
import json
import re
import ssl
import urllib.request

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
_CTX = ssl.create_default_context()


def http_get(url, timeout=12, referer=None):
    headers = {"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9"}
    if referer:
        headers["Referer"] = referer
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout, context=_CTX) as r:
        return r.status, r.read()


def _num(v):
    """容错数值转换：空/异常返回 '-'。"""
    if v in (None, "", "-"):
        return "-"
    try:
        return float(v)
    except (TypeError, ValueError):
        return "-"


# ---------------------------------------------------------------- 新闻联播
def fetch_news(target=None):
    """抓取央视网《新闻联播》每日节目单。优先当天，失败自动回退到前一天。"""
    d = target or dt.date.today()
    err = None
    for cand in (d, d - dt.timedelta(days=1)):
        url = "https://tv.cctv.com/lm/xwlb/day/{0:%Y%m%d}.shtml".format(cand)
        try:
            st, body = http_get(url)
            if st != 200:
                continue
            html = body.decode("utf-8", "ignore")
            titles, urls = [], []
            for m in re.finditer(r'<a href="([^"]+)"[^>]*title="\[视频\]([^"]+)"', html):
                u, t = m.group(1).strip(), m.group(2).strip()
                if t and t not in titles:
                    titles.append(t)
                    urls.append(u)
            if len(titles) < 3:  # 兜底：锚文本
                for m in re.finditer(r'<a href="([^"]+)"[^>]*>\[视频\]([^<]+)</a>', html):
                    u, t = m.group(1).strip(), m.group(2).strip()
                    if t and t not in titles:
                        titles.append(t)
                        urls.append(u)
            if titles:
                return {
                    "date": cand.isoformat(),
                    "source": "央视网《新闻联播》",
                    "items": [
                        {"title": t, "url": urls[i] if i < len(urls) else ""}
                        for i, t in enumerate(titles)
                    ],
                    "error": None,
                }
            err = "页面存在但未解析到条目"
        except Exception as e:  # noqa: BLE001
            err = "{0}: {1}".format(e.__class__.__name__, e)
    return {
        "date": d.isoformat(),
        "source": "央视网《新闻联播》",
        "items": [],
        "error": err or "未获取到联播内容（可能当天尚未播出）",
    }


# ---------------------------------------------------------------- 大盘指数
def _to_tencent_code(secid):
    """东财 secid('1.000001') -> 腾讯代码('sh000001')；海外代码原样('hkHSI')。"""
    if secid.startswith(("hk", "us")):
        return secid
    mkt, code = secid.split(".", 1)
    return ("sh" if mkt == "1" else "sz") + code


def _parse_tencent(text):
    """腾讯行情：v_sh000001=\"1~上证指数~000001~3905.20~...~1.48~0.04~...\"（GBK）"""
    out = []
    for m in re.finditer(r'v_(\w+)="([^"]*)"', text):
        f = m.group(2).split("~")
        if len(f) > 32 and f[1]:
            out.append(
                {
                    "code": f[2] or m.group(1),
                    "name": f[1],
                    "price": _num(f[3]),
                    "pct": _num(f[32]),
                    "chg": _num(f[31]),
                }
            )
    return out


def _parse_sina(text):
    """新浪行情：var hq_str_sh000001=\"上证指数,开,昨收,现价,...\"（GBK）"""
    out = []
    for m in re.finditer(r'hq_str_\w+="([^"]*)"', text):
        f = m.group(1).split(",")
        if len(f) > 5 and f[0]:
            try:
                cur = float(f[3])
                prev = float(f[2])
            except (TypeError, ValueError):
                continue
            out.append(
                {
                    "code": m.group(0)[9:15],
                    "name": f[0],
                    "price": cur,
                    "chg": round(cur - prev, 2),
                    "pct": round((cur / prev - 1) * 100, 2) if prev else 0.0,
                }
            )
    return out


def fetch_indices(indices_cfg):
    """大盘指数（国内+海外）：腾讯主源（统一格式）-> 东财备援（仅国内）-> 新浪备援。"""
    # 1) 腾讯（支持 sh/sz/hk/us 全部市场）
    try:
        qs = ",".join(_to_tencent_code(i["secid"]) for i in indices_cfg)
        st, body = http_get("https://qt.gtimg.cn/q=" + qs)
        out = _parse_tencent(body.decode("gbk", "ignore"))
        if out:
            return {"indices": out, "error": None}
    except Exception:  # noqa: BLE001
        pass
    # 2) 东财（仅国内）
    dom = [i for i in indices_cfg if "." in i["secid"]]
    try:
        secids = ",".join(i["secid"] for i in dom)
        url = (
            "https://push2.eastmoney.com/api/qt/ulist.np/get"
            "?secids={0}&fields=f2,f3,f4,f12,f14&fltt=2".format(secids)
        )
        st, body = http_get(url, referer="https://quote.eastmoney.com/")
        data = json.loads(body.decode("utf-8", "ignore"))
        diff = (data.get("data") or {}).get("diff") or []
        if diff:
            out = []
            for it in diff:
                out.append(
                    {
                        "code": it.get("f12", ""),
                        "name": it.get("f14", ""),
                        "price": _num(it.get("f2")),
                        "pct": _num(it.get("f3")),
                        "chg": _num(it.get("f4")),
                    }
                )
            return {"indices": out, "error": "海外指数暂不可用"}
    except Exception:  # noqa: BLE001
        pass
    # 3) 新浪（仅国内）
    try:
        qs = ",".join(_to_tencent_code(i["secid"]) for i in dom)
        st, body = http_get("https://hq.sinajs.cn/list=" + qs, referer="https://finance.sina.com.cn/")
        out = _parse_sina(body.decode("gbk", "ignore"))
        if out:
            return {"indices": out, "error": "海外指数暂不可用"}
    except Exception:  # noqa: BLE001
        pass
    return {"indices": [], "error": "指数行情获取失败（腾讯/东财/新浪均不可用）"}


# ---------------------------------------------------------------- 基金
def fetch_fund(code):
    """天天基金 pingzhongdata：最新净值 + 日涨跌 + 近1周/1月/3月收益 + 近60日走势。

    净值历史可能是 [ts, nav] 数组或 {"x": ts, "y": nav} 对象，两者兼容。
    """
    url = "https://fund.eastmoney.com/pingzhongdata/{0}.js".format(code)
    try:
        st, body = http_get(url, referer="https://fund.eastmoney.com/")
        txt = body.decode("utf-8", "ignore")
        m_name = re.search(r'var fS_name = "([^"]*)"', txt)
        m_trend = re.search(r"var Data_netWorthTrend = (\[.*?\]);", txt, re.S)
        name = m_name.group(1) if m_name else code
        nav = nav_date = day_chg = None
        w1 = m1 = m3 = None
        trend = []
        if m_trend:
            arr = json.loads(m_trend.group(1))
            pts = []
            for p in arr:
                if isinstance(p, dict):
                    ts, v = p.get("x"), p.get("y")
                elif isinstance(p, (list, tuple)) and len(p) >= 2:
                    ts, v = p[0], p[1]
                else:
                    continue
                try:
                    pts.append((int(ts), float(v)))
                except (TypeError, ValueError):
                    continue
            pts.sort()
            if pts:
                last_ts, nav = pts[-1]
                nav_date = dt.datetime.fromtimestamp(last_ts / 1000).strftime("%Y-%m-%d")
                if len(pts) >= 2 and pts[-2][1]:
                    day_chg = round((nav / pts[-2][1] - 1) * 100, 2)

                def period(days):
                    target = last_ts - days * 86400000
                    base = None
                    for ts, v in reversed(pts):
                        if ts <= target:
                            base = v
                            break
                    if base in (None, 0):
                        return None
                    return (nav / base - 1) * 100

                def r2(v):
                    return round(v, 2) if v is not None else None

                w1 = r2(period(7))
                m1 = r2(period(30))
                m3 = r2(period(90))
                trend = [
                    [dt.datetime.fromtimestamp(ts / 1000).strftime("%m-%d"), v]
                    for ts, v in pts[-60:]
                ]
        return {
            "code": code,
            "name": name,
            "nav": nav,
            "nav_date": nav_date,
            "day_chg": day_chg,
            "w1": w1,
            "m1": m1,
            "m3": m3,
            "trend": trend,
            "error": None,
        }
    except Exception as e:  # noqa: BLE001
        return {
            "code": code,
            "name": code,
            "nav": None,
            "nav_date": None,
            "day_chg": None,
            "w1": None,
            "m1": None,
            "m3": None,
            "trend": [],
            "error": "{0}: {1}".format(e.__class__.__name__, e),
        }


def fetch_top_gainers(limit=5):
    """今日基金涨幅榜 Top N（东财 rankhandler，日涨幅排序）。"""
    url = (
        "https://fund.eastmoney.com/data/rankhandler.aspx"
        "?op=ph&dt=kf&ft=all&rs=&gs=0&sc=rzdf&st=desc&sd=&ed=&qdii="
        "&tabSubtype=,,,,,&pi=1&pn={0}&dx=1".format(limit)
    )
    try:
        st, body = http_get(url, referer="https://fund.eastmoney.com/")
        txt = body.decode("utf-8", "ignore")
        m = re.search(r"datas:(\[.*?\]),", txt, re.S)
        if not m:
            return {"top": [], "error": "接口格式变化"}
        arr = json.loads(m.group(1))
        out = []
        seen = set()
        for s in arr:
            f = s.split(",")
            if len(f) > 7:
                key = re.sub(r"[AC]$", "", f[1])  # A/C 份额去重
                if key in seen:
                    continue
                seen.add(key)
                out.append(
                    {
                        "code": f[0],
                        "name": f[1],
                        "date": f[3],
                        "day": _num(f[6]),
                    }
                )
        return {"top": out, "error": None}
    except Exception as e:  # noqa: BLE001
        return {"top": [], "error": "{0}: {1}".format(e.__class__.__name__, e)}


# ---------------------------------------------------------------- 周K线
# 美股指数东财 secid 映射（备用源）
US_EMAP = {"usIXIC": "100.NDX", "usDJI": "100.DJIA", "usINX": "100.SPX"}


def fetch_qbitai_week(days=7, limit=10):
    """量子位 RSS：近 days 天文章（标题/链接/日期/摘要），供每周总结科技要闻。"""
    try:
        st, body = http_get("https://www.qbitai.com/feed/", referer="https://www.qbitai.com/")
        txt = body.decode("utf-8", "ignore")
        out = []
        now = dt.datetime.now()
        for it in re.findall(r"<item>(.*?)</item>", txt, re.S):
            m_t = re.search(r"<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>", it, re.S)
            m_l = re.search(r"<link>(.*?)</link>", it, re.S)
            m_p = re.search(r"<pubDate>(.*?)</pubDate>", it, re.S)
            m_d = re.search(r"<description>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</description>", it, re.S)
            if not (m_t and m_l and m_p):
                continue
            try:
                pd = email.utils.parsedate_to_datetime(m_p.group(1).strip())
            except (TypeError, ValueError):
                continue
            try:
                age = (now - pd).days
            except TypeError:
                age = 0
            if age > days:
                continue
            desc = re.sub(r"<[^>]+>", " ", m_d.group(1)) if m_d else ""
            out.append(
                {
                    "title": m_t.group(1).strip(),
                    "url": m_l.group(1).strip(),
                    "date": pd.strftime("%m-%d"),
                    "desc": desc.strip()[:110],
                }
            )
        return out[:limit]
    except Exception:  # noqa: BLE001
        return []


def _rss_entries(body, days=7, limit=10):
    """通用 RSS 2.0 解析：按发布时间过滤 + 截取（IT 之家 / InfoQ 复用）。"""
    txt = body.decode("utf-8", "ignore")
    out = []
    now = dt.datetime.now()
    for it in re.findall(r"<item>(.*?)</item>", txt, re.S):
        m_t = re.search(r"<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>", it, re.S)
        m_l = re.search(r"<link>(.*?)</link>", it, re.S)
        m_p = re.search(r"<pubDate>(.*?)</pubDate>", it, re.S)
        m_d = re.search(r"<description>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</description>", it, re.S)
        if not (m_t and m_l and m_p):
            continue
        try:
            pd = email.utils.parsedate_to_datetime(m_p.group(1).strip())
        except (TypeError, ValueError):
            continue
        try:
            age = (now - pd).days
        except TypeError:
            age = 0
        if age > days:
            continue
        desc = re.sub(r"<[^>]+>", " ", m_d.group(1)) if m_d else ""
        out.append(
            {
                "title": m_t.group(1).strip(),
                "url": m_l.group(1).strip(),
                "date": pd.strftime("%m-%d"),
                "desc": desc.strip()[:110],
            }
        )
    return out[:limit]


def fetch_ithome(days=3, limit=5):
    """IT 之家 RSS：综合科技资讯（量大、覆盖广）。"""
    try:
        st, body = http_get("https://www.ithome.com/rss/")
        if st != 200:
            return []
        return _rss_entries(body, days=days, limit=limit)
    except Exception:  # noqa: BLE001
        return []


def fetch_infoq(days=7, limit=5):
    """InfoQ 中文 RSS：技术架构 / 软件工程 / AI / 云原生深度内容。"""
    try:
        st, body = http_get("https://www.infoq.cn/feed")
        if st != 200:
            return []
        return _rss_entries(body, days=days, limit=limit)
    except Exception:  # noqa: BLE001
        return []


def fetch_juejin_hot(limit=5):
    """掘金热榜：公开推荐接口（POST），开发者社区热门文章。"""
    try:
        payload = json.dumps({"id_type": 2, "sort_type": 3, "cursor": "0", "limit": 20}).encode("utf-8")
        req = urllib.request.Request(
            "https://api.juejin.cn/recommend_api/v1/article/recommend_all_feed",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "User-Agent": UA,
                "Referer": "https://juejin.cn/",
            },
        )
        with urllib.request.urlopen(req, timeout=12, context=_CTX) as r:
            d = json.loads(r.read().decode("utf-8", "ignore"))
        out = []
        for it in d.get("data") or []:
            art = (it.get("item_info") or {}).get("article_info") or {}
            t = (art.get("title") or "").strip()
            if not t:
                continue
            out.append(
                {
                    "title": t,
                    "url": "https://juejin.cn/post/{0}".format(art.get("article_id", "")),
                    "date": dt.date.today().strftime("%m-%d"),
                    "desc": (art.get("brief_content") or "").strip()[:110],
                }
            )
            if len(out) >= limit:
                break
        return out
    except Exception:  # noqa: BLE001
        return []


# 科技前沿信源（按内容深度优先级排序；36氪/机器之心因接口签名保护仅保留官网入口）
TECH_FEEDS = [
    ("InfoQ 中文", fetch_infoq, {"days": 7, "limit": 4}),
    ("IT 之家", fetch_ithome, {"days": 3, "limit": 4}),
    ("量子位", fetch_qbitai_week, {"days": 7, "limit": 4}),
    ("掘金", fetch_juejin_hot, {"limit": 4}),
]


def fetch_tech_feeds(limit_each=4):
    """聚合科技前沿：按优先级抓取多源，失败源自动跳过，条目标注 source。"""
    items = []
    for name, fn, kw in TECH_FEEDS:
        try:
            params = dict(kw)
            params["limit"] = limit_each
            got = fn(**params)
        except Exception:  # noqa: BLE001
            got = []
        for it in got:
            item = dict(it)
            item["source"] = name
            items.append(item)
    return items


def _parse_week_rows(rows):
    """周K行 -> 最近一周涨跌 dict（行格式 [date, open, close, high, low, ...]）。"""
    if len(rows) < 2:
        return None
    last, prev = rows[-1], rows[-2]
    try:
        close = float(last[2])
        prev_close = float(prev[2])
    except (TypeError, ValueError):
        return None
    return {
        "date": last[0],
        "open": float(last[1]),
        "close": close,
        "high": float(last[3]),
        "low": float(last[4]),
        "week_pct": round((close / prev_close - 1) * 100, 2) if prev_close else None,
    }


def fetch_week_kline(code, weeks=10):
    """周K：腾讯 web（sh/sz/hk）-> 腾讯 proxy（美股）-> 东财（美股备用）。"""
    # 1) 腾讯 web
    try:
        url = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={0},week,,,{1},qfq".format(code, weeks)
        st, body = http_get(url)
        d = json.loads(body.decode("utf-8", "ignore"))
        data = (d.get("data") or {}).get(code) or {}
        key = [k for k in data if "week" in k]
        if key:
            r = _parse_week_rows(data[key[0]])
            if r:
                return r
    except Exception:  # noqa: BLE001
        pass
    # 2) 腾讯 proxy（美股指数）
    try:
        url = (
            "https://proxy.finance.qq.com/ifzqgtimg/appstock/app/newfqkline/get"
            "?param={0},week,,,{1},320".format(code, weeks)
        )
        st, body = http_get(url)
        d = json.loads(body.decode("utf-8", "ignore"))
        data = (d.get("data") or {}).get(code) or {}
        key = [k for k in data if "week" in k]
        if key:
            r = _parse_week_rows(data[key[0]])
            if r:
                return r
    except Exception:  # noqa: BLE001
        pass
    # 3) 东财（美股指数）
    em = US_EMAP.get(code)
    if em:
        try:
            url = (
                "https://push2his.eastmoney.com/api/qt/stock/kline/get"
                "?secid={0}&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56,f57,f58"
                "&klt=102&fqt=1&end=20500101&lmt={1}".format(em, weeks)
            )
            st, body = http_get(url, referer="https://quote.eastmoney.com/")
            d = json.loads(body.decode("utf-8", "ignore"))
            kls = (d.get("data") or {}).get("klines") or []
            if len(kls) >= 2:
                rows = [k.split(",") for k in kls]
                r = _parse_week_rows(rows)
                if r:
                    return r
        except Exception:  # noqa: BLE001
            return None
    return None
