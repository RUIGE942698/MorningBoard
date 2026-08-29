# -*- coding: utf-8 -*-
"""网络素材抓取：给「思辨训练」提供当日真实热点议题。

定位：抓的是**议题**（发生了什么），不是论证。正方/反方/追问这类
论证结构网页上没有现成的，抓不到——要么交给 AI 基于真实议题加工，
要么退化成"议题卡"（标题 + 追问 + 原文链接）。

源可用性实测（2026-08-29，本机）：
  ✅ 头条热榜  https://www.toutiao.com/hot-event/hot-board/   JSON，约 50 条
  ✅ 澎湃热榜  https://cache.thepaper.cn/contentapi/wwwIndex/rightSidebar  JSON，20 条
  ❌ 知乎热榜  401 Authorization Required（需登录态）
  ❌ 微博热搜  403 Forbidden（需登录态）

新增源时照着 _fetch_* 的签名写一个、加进 SOURCES 即可，每个源独立 try，
挂掉不影响其它源。
"""
import json
import re
import urllib.request

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
TIMEOUT = 12

_PUNCT_RE = re.compile(r"[\s\W_]+", re.UNICODE)


def _norm(s):
    return _PUNCT_RE.sub("", (s or "").lower())


def _get_json(url, timeout=TIMEOUT):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "ignore"))


def _fetch_toutiao(limit=30):
    """头条热榜：{t, s, url, src, hot}"""
    d = _get_json("https://www.toutiao.com/hot-event/hot-board/?origin=toutiao_pc")
    out = []
    for it in (d.get("data") or [])[:limit]:
        title = (it.get("Title") or "").strip()
        if not title:
            continue
        # 头条的 Url 带一大串 log_pb 追踪参数（几百字符），截到 ? 之前
        url = (it.get("Url") or "").strip()
        if "?" in url:
            url = url.split("?", 1)[0]
        out.append(
            {
                "t": title,
                "s": "热度 {0}".format(it.get("HotValue") or "-"),
                "url": url,
                "src": "头条热榜",
                "hot": it.get("HotValue") or 0,
            }
        )
    return out


def _fetch_thepaper(limit=20):
    """澎湃热榜：{t, s, url, src, hot}"""
    d = _get_json("https://cache.thepaper.cn/contentapi/wwwIndex/rightSidebar")
    out = []
    for it in ((d.get("data") or {}).get("hotNews") or [])[:limit]:
        title = (it.get("name") or "").strip()
        cid = it.get("contId")
        if not title:
            continue
        out.append(
            {
                "t": title,
                "s": "澎湃热度 {0}".format(it.get("interactionNum") or "-"),
                "url": "https://www.thepaper.cn/newsDetail_forward_{0}".format(cid) if cid else "",
                "src": "澎湃热榜",
                "hot": int(it.get("interactionNum") or 0),
            }
        )
    return out


SOURCES = (
    ("头条热榜", _fetch_toutiao),
    ("澎湃热榜", _fetch_thepaper),
)


def fetch_hot_topics(limit=24, timeout=TIMEOUT):
    """抓取当日热点，去重后返回 [{t, s, url, src, hot}]。

    多源轮询交错，避免结果被单个源占满；任一源失败自动跳过。
    """
    buckets = []
    for name, fn in SOURCES:
        try:
            buckets.append(fn())
        except Exception:  # noqa: BLE001
            buckets.append([])

    out, seen = [], set()
    i = 0
    while len(out) < limit:
        added = False
        for b in buckets:
            if i >= len(b):
                continue
            it = b[i]
            key = _norm(it.get("t"))
            # 太短的标题基本没有信息量，直接丢
            if key and len(key) >= 6 and key not in seen:
                seen.add(key)
                out.append(it)
                added = True
                if len(out) >= limit:
                    break
        if not added:
            break
        i += 1
    return out
