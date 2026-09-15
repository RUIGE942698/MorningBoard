# -*- coding: utf-8 -*-
"""AI 周报自动抓取工作流。

源池来自对「盘点一周AI大事」四期卡片（8/23、8/30、9/6、9/13）的链接反推，按 5 层分层。
抓取全部走公开 RSS / 列表页 / 开放 API，零第三方依赖（复用 app.fetch 的底座）。

流程：并发抓取 -> 结构化解析 -> URL 归一化 -> 跨源去重 -> AI 相关性过滤
      -> 时间窗口 + 增量判定 -> 重要性打分 -> 保底补足 -> 落 JSON 快照 + Markdown 周报

产出量约束（对齐原栏目）：每周 8-15 条，本工具默认保底 12 条、上限 20 条。
若自然入选不足，自动从次级池按分数补足，确保每期条数不低于对标栏目。

用法：
    python -m app.ai_weekly                    # 抓最近 7 天并出报告
    python -m app.ai_weekly --dry              # 只看统计不写文件
    python -m app.ai_weekly --snapshot-only    # 只更新基线（首次建议先跑一次）
    python -m app.ai_weekly --min-items 12 --max-items 20
"""
import argparse
import datetime as dt
import email.utils
import json
import os
import re
import sys
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed

from . import config
from . import fetch

OUT_DIR = os.path.join(config.CACHE_DIR, "ai_weekly")
REPORT_DIR = os.path.join(OUT_DIR, "reports")
SNAP_PATH = os.path.join(OUT_DIR, "snapshot.json")
LATEST_PATH = os.path.join(OUT_DIR, "latest.json")

MIN_ITEMS = 12   # 保底条数：对标栏目每期 8-15 条，取中位偏上
MAX_ITEMS = 20   # 上限：避免退化成新闻流

# ---------------------------------------------------------------- 源池
# tier 1 一手官方 newsroom（反推占比 ≈50%，全部直挂原文页）
# tier 2 社媒（X / YouTube 需登录，脚本内不可直抓，由 tier 3 媒体转述覆盖）
# tier 3 聚合与媒体（中文为主，需 AI 相关性过滤）
# tier 4 匿名测试位（模型未发布先上线跑分，最早信号）
# tier 5 观点原文（高管 / 研究者个人博客）
#
# 实测状态（本机网络，2026-09-16）：
#   OK   OpenAI News / Anthropic News / DeepSeek News / NVIDIA Blog
#        IT之家 / InfoQ / 量子位 / AIBase / The Technium
#   FAIL 需代理：Hacker News、Hugging Face（Tunnel 502）；Google AI Blog（SSL EOF）
SOURCES = [
    # ---- tier 1 一手官方
    {"name": "OpenAI News", "tier": 1, "kind": "feed",
     "url": "https://openai.com/news/rss.xml"},
    {"name": "Anthropic News", "tier": 1, "kind": "html",
     "url": "https://www.anthropic.com/news",
     "href_re": r"/news/[a-z0-9][a-z0-9\-]{4,}"},
    {"name": "DeepSeek News", "tier": 1, "kind": "html",
     "url": "https://www.deepseek.com/news/",
     "href_re": r"/news/[a-z0-9][a-z0-9\-]+/?$"},
    {"name": "NVIDIA Developer Blog", "tier": 1, "kind": "feed", "need_ai": True,
     "url": "https://developer.nvidia.com/blog/feed/"},
    # 用 DeepMind 而非 blog.google/technology/ai：后者实测混入 DevFest、宇航员访谈等
    # 活动宣传，不是模型发布源；DeepMind blog 才是 AlphaGenome / WeatherNext 这类首发地
    {"name": "Google DeepMind Blog", "tier": 1, "kind": "feed",
     "url": "https://deepmind.google/blog/rss.xml"},
    {"name": "Hugging Face 新模型", "tier": 1, "kind": "hf"},
    # ---- tier 3 聚合与媒体
    {"name": "量子位", "tier": 3, "kind": "feed", "need_ai": True,
     "url": "https://www.qbitai.com/feed"},
    {"name": "IT 之家", "tier": 3, "kind": "feed", "need_ai": True,
     "url": "https://www.ithome.com/rss/"},
    {"name": "InfoQ 中文", "tier": 3, "kind": "feed", "need_ai": True,
     "url": "https://www.infoq.cn/feed"},
    {"name": "AIBase 中文", "tier": 3, "kind": "html", "need_ai": True,
     "url": "https://www.aibase.com/zh/news", "href_re": r"/news/\d+"},
    {"name": "Hacker News", "tier": 3, "kind": "feed", "need_ai": True,
     "url": "https://news.ycombinator.com/rss"},
    # ---- tier 4 匿名测试位
    {"name": "OpenRouter 匿名测试位", "tier": 4, "kind": "openrouter"},
    # ---- tier 5 观点原文
    {"name": "Dario Amodei", "tier": 5, "kind": "html",
     "url": "https://darioamodei.com/", "href_re": r"/(?:post|essay)/[a-z0-9\-]{4,}"},
    {"name": "The Technium", "tier": 5, "kind": "feed", "need_ai": True,
     "url": "https://kk.org/thetechnium/feed/"},
]

TIER_NAMES = {
    1: "一手官方发布",
    2: "社媒与视频",
    3: "聚合与媒体",
    4: "匿名测试位（最早信号）",
    5: "观点原文",
}

# ---------------------------------------------------------------- 过滤与归一化
# 综合源（tier 3）需要 AI 相关性过滤，否则会把财经 / 体育新闻一并带进来
AI_KEYWORDS = [
    "AI", "人工智能", "大模型", "大语言模型", "语言模型", "生成式", "智能体", "Agent",
    "GPT", "ChatGPT", "Claude", "Gemini", "Llama", "Mistral", "Grok", "Copilot", "Sora",
    "DeepSeek", "Qwen", "通义", "文心", "智谱", "GLM", "Kimi", "豆包", "混元", "MiniMax",
    "OpenAI", "Anthropic", "英伟达", "NVIDIA", "算力", "GPU", "TPU", "神经网络",
    "Transformer", "扩散模型", "多模态", "对齐", "AGI", "机器学习", "深度学习",
    "机器人", "具身智能", "开源模型", "微调", "提示词", "Token", "阶跃星辰", "月之暗面",
    "Hugging Face", "xAI", "Chatbot", "语音大模型", "世界模型", "推理模型",
]
_EN_KW = [w for w in AI_KEYWORDS if w.isascii()]
_CN_KW = [w for w in AI_KEYWORDS if not w.isascii()]
_EN_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(w) for w in sorted(_EN_KW, key=len, reverse=True)) + r")\b", re.I
)

# 重要性打分：保证入选的是「大事」而不是工程教程
_HIGH_WEIGHT = [
    "发布", "推出", "上线", "开源", "正式", "宣布", "问世", "首发", "面向所有用户",
    "introducing", "launch", "release", "unveil", "announcing", "generally available",
    "突破", "超越", "第一", "纪录", "sota", "benchmark", "state-of-the-art",
    "融资", "收购", "投资", "合作", "估值", "ipo", "监管", "政策", "法案", "禁令",
    "agi", "超级智能", "通用人工智能", "里程碑",
]
_LOW_WEIGHT = [
    "how to", "tutorial", "guide", "serving", "serve ", "optimiz", "walkthrough",
    "how a researcher", "ways to", "get ready", "frame by frame", "cuda", "toolkit",
    "runtime", "inference runtime", "best practices", "deep dive", "under the hood",
    "教程", "上手", "入门", "技巧", "指南", "手把手", "踩坑", "报错", "安装",
    "招聘", "征文", "直播预告", "活动报名", "详解", "配件", "开售",
]

# 判定「同一篇文章」时必须先剥掉的追踪参数
# 依据：nvda.ws 短链解析出 ncid=so-twit-543600，同文会以带参/不带参两种形态出现
_TRACKING_KEYS = {
    "ncid", "fbclid", "gclid", "spm", "scm", "ref", "ref_src", "ref_url",
    "share_token", "share_source", "share_medium", "weibo_id", "wechat", "wxshare",
    "mc_cid", "mc_eid", "igshid", "si", "app_id", "_hsenc", "_hsmi", "yclid", "msclkid",
}

_MONTHS = {m: i + 1 for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}


def _is_tracking(key):
    k = (key or "").lower()
    return k.startswith("utm_") or k in _TRACKING_KEYS


def normalize_url(url):
    """剥追踪参数 + 统一 host/尾斜杠，得到跨源去重用的规范 URL。"""
    if not url:
        return ""
    u = url.strip()
    if u.startswith("//"):
        u = "https:" + u
    try:
        p = urllib.parse.urlsplit(u)
    except ValueError:
        return u
    q = [(k, v) for k, v in urllib.parse.parse_qsl(p.query, keep_blank_values=False) if not _is_tracking(k)]
    netloc = p.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    path = p.path.rstrip("/") or "/"
    return urllib.parse.urlunsplit((p.scheme or "https", netloc, path, urllib.parse.urlencode(q), ""))


def ai_related(title, desc="", strict=False):
    """AI 相关性判定：英文词走词边界，中文词直接包含。

    strict=True（综合源）时：标题必须命中；标题不命中则要求摘要至少命中 2 个不同
    关键词才放行——否则「手机应用一碰上车」这类靠摘要里一个泛词混入的条目会漏进来。
    """
    title = title or ""
    if _EN_RE.search(title) or any(w in title for w in _CN_KW):
        return True
    blob = "{0} {1}".format(title, desc or "")
    loose = bool(_EN_RE.search(blob)) or any(w in blob for w in _CN_KW)
    if not strict or not loose:
        return loose
    d = desc or ""
    hits = {w for w in _CN_KW if w in d}
    hits |= {m.group(0).lower() for m in _EN_RE.finditer(d)}
    return len(hits) >= 2


def score_item(item):
    """重要性打分：模型发布 / 能力突破 / 商业动作加分，工程教程减分。"""
    text = "{0} {1}".format(item.get("title") or "", item.get("desc") or "").lower()
    s = 0
    for w in _HIGH_WEIGHT:
        if w in text:
            s += 3
    for w in _LOW_WEIGHT:
        if w in text:
            s -= 2
    if item.get("tier") == 1:
        s += 2          # 一手官方源权重更高
    elif item.get("tier") == 4:
        s += 3          # 匿名测试位是稀缺信号，优先露出
    if item.get("also_seen"):
        s += 2          # 多源交叉印证 = 更可能是大事
    return s


def _title_bigrams(title):
    """标题的字符 bigram 集合，用于跨源判重（中文短标题下比分词更稳）。"""
    s = re.sub(r"[\s\W_]+", "", (title or "").lower())
    if len(s) < 2:
        return {s} if s else set()
    return {s[i:i + 2] for i in range(len(s) - 1)}


def _too_similar(t1, t2, threshold=0.55):
    """两个标题是否为同一事件（bigram Jaccard）。"""
    a, b = _title_bigrams(t1), _title_bigrams(t2)
    if not a or not b:
        return False
    inter = len(a & b)
    union = len(a | b)
    return union > 0 and inter / union >= threshold


# ---------------------------------------------------------------- 日期与解析
def extract_date(blk, text=""):
    """从条目块里提日期：<time> / ISO / 中文年月日 / 英文 Month D, YYYY / 相对时间。"""
    m = re.search(r"<time[^>]*>(.*?)</time>", blk, re.S | re.I)
    raw = fetch._clean_text(m.group(1)) if m else ""
    hay = raw or text

    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", hay)
    if m:
        return m.group(0)
    m = re.search(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日", hay)
    if m:
        return "{0:04d}-{1:02d}-{2:02d}".format(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = re.search(r"([A-Z][a-z]{2})[a-z]*\s+(\d{1,2}),\s*(\d{4})", hay)
    if m and m.group(1).lower() in _MONTHS:
        return "{0:04d}-{1:02d}-{2:02d}".format(
            int(m.group(3)), _MONTHS[m.group(1).lower()], int(m.group(2)))
    if re.search(r"刚刚|分钟前|小时前|今天|\bjust now\b|\bminutes? ago\b|\bhours? ago\b", hay, re.I):
        return dt.date.today().isoformat()
    m = re.search(r"(\d{1,2})\s*天前", hay)
    if m:
        return (dt.date.today() - dt.timedelta(days=int(m.group(1)))).isoformat()
    return None


def _strip_prefix(title):
    """剥掉列表页常见的「分类 + 日期」前缀（Anthropic、DeepSeek 等源会带上）。"""
    t = title or ""
    t = re.sub(r"^\s*(?:动态|公告|新闻|Announcements?|Product|Policy|Research|Engineering|News)\s*", "", t)
    t = re.sub(r"^\s*\d{4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日\s*", "", t)
    t = re.sub(r"^\s*[A-Z][a-z]{2}[a-z]*\s+\d{1,2},\s*\d{4}\s*", "", t)
    return t.strip()


def parse_feed(body, days=7, limit=30):
    """RSS 2.0 与 Atom 通吃：按发布时间过滤 + 截取。失败返回 []。"""
    txt = body.decode("utf-8", "ignore")
    out = []
    now = dt.datetime.now(dt.timezone.utc)
    blocks = re.findall(r"<item>(.*?)</item>", txt, re.S)
    is_atom = False
    if not blocks:
        blocks = re.findall(r"<entry>(.*?)</entry>", txt, re.S)
        is_atom = True
    for it in blocks:
        m_t = re.search(r"<title[^>]*>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>", it, re.S)
        if is_atom:
            m_l = re.search(r'<link[^>]*href="([^"]+)"', it, re.S) or re.search(r"<link>(.*?)</link>", it, re.S)
        else:
            m_l = re.search(r"<link>(.*?)</link>", it, re.S)
        m_d = re.search(r"<(?:pubDate|published|updated|dc:date)>([^<]+)</", it, re.I)
        m_s = re.search(
            r"<(?:description|summary|content:encoded)[^>]*>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</", it, re.S)
        if not (m_t and m_l):
            continue
        pub = None
        if m_d:
            raw = m_d.group(1).strip()
            try:
                pub = email.utils.parsedate_to_datetime(raw)
            except Exception:  # noqa: BLE001
                try:
                    pub = dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
                except Exception:  # noqa: BLE001
                    pub = None
        if pub is not None and pub.tzinfo is None:
            pub = pub.replace(tzinfo=dt.timezone.utc)
        if pub is not None and (now - pub).days > days:
            continue
        out.append({
            "title": fetch._clean_text(m_t.group(1), 200),
            "url": m_l.group(1).strip(),
            "date": pub.astimezone().strftime("%Y-%m-%d") if pub else None,
            "desc": fetch._clean_text(m_s.group(1), 120) if m_s else "",
        })
        if len(out) >= limit:
            break
    return out


def parse_html_list(body, base_url, href_re, limit=25):
    """列表页解析：标题优先取 <h1>-<h4>，日期与摘要分别提取。

    列表页多数不带可靠时间戳——提不到日期的条目靠「相对上次快照是否为新 URL」判新旧。
    """
    txt = body.decode("utf-8", "ignore")
    out, seen = [], set()
    for m in re.finditer(r'<a\s[^>]*href="([^"]+)"[^>]*>(.*?)</a>', txt, re.S | re.I):
        href, blk = m.group(1), m.group(2)
        if not re.search(href_re, href, re.I):
            continue
        title = ""
        for tag in ("h1", "h2", "h3", "h4"):
            mt = re.search(r"<" + tag + r"[^>]*>(.*?)</" + tag + r">", blk, re.S | re.I)
            if mt:
                title = fetch._clean_text(mt.group(1), 200)
                if len(title) >= 6:
                    break
        plain = fetch._clean_text(blk, 300)
        if len(title) < 6:                       # 无标题标签：回退到纯文本再剥前缀
            title = _strip_prefix(plain)
        title = _strip_prefix(title)
        if len(title) < 6:
            continue
        desc = ""
        for mp in re.findall(r"<p[^>]*>(.*?)</p>", blk, re.S | re.I):
            c = fetch._clean_text(mp, 140)
            if len(c) >= 20 and c != title:
                desc = c
                break
        url = urllib.parse.urljoin(base_url, href)
        key = normalize_url(url)
        if key in seen:
            continue
        seen.add(key)
        out.append({"title": title, "url": url, "date": extract_date(blk, plain), "desc": desc})
        if len(out) >= limit:
            break
    return out


def fetch_hf_models(limit=20):
    """Hugging Face 最新模型：开源首发第一时间出现在这里。"""
    st, body = fetch.http_get(
        "https://huggingface.co/api/models?sort=createdAt&direction=-1&limit={0}".format(limit),
        timeout=15,
    )
    if st != 200:
        return []
    data = json.loads(body.decode("utf-8", "ignore"))
    out = []
    for m in data if isinstance(data, list) else []:
        mid = m.get("modelId") or m.get("id") or ""
        if not mid:
            continue
        out.append({
            "title": "新模型开源：{0}".format(mid),
            "url": "https://huggingface.co/{0}".format(mid),
            "date": (m.get("createdAt") or "")[:10] or None,
            "desc": "下载 {0} · 点赞 {1}".format(m.get("downloads", 0), m.get("likes", 0)),
        })
    return out


def fetch_openrouter_stealth():
    """OpenRouter 模型列表：挑出匿名 / 隐形测试位，这是整条流水线里最早的信号层。"""
    st, body = fetch.http_get("https://openrouter.ai/api/v1/models", timeout=15)
    if st != 200:
        return []
    data = json.loads(body.decode("utf-8", "ignore"))
    rows = data.get("data") if isinstance(data, dict) else data
    out = []
    for m in rows or []:
        mid = m.get("id") or ""
        name = m.get("name") or ""
        blob = "{0} {1} {2}".format(mid, name, m.get("description") or "").lower()
        if not re.search(r"stealth|cloak|anonymous|anon-|hidden|隐身|匿名", blob):
            continue
        out.append({
            "title": "匿名测试位出现：{0}".format(mid),
            "url": "https://openrouter.ai/models?q={0}".format(urllib.parse.quote(mid)),
            "date": None,
            "desc": fetch._clean_text(name, 100),
        })
    return out


# ---------------------------------------------------------------- 抓取调度
def fetch_source(src, days=7):
    """单个源抓取。网络抖动重试一次，任何异常都吞掉并返回 ([], 状态串)。"""
    name, kind = src["name"], src["kind"]
    need_ai = bool(src.get("need_ai"))
    last_err = "unknown"
    for _ in range(2):
        try:
            if kind == "feed":
                st, body = fetch.http_get(src["url"], timeout=15)
                items = parse_feed(body, days=days) if st == 200 else []
            elif kind == "html":
                st, body = fetch.http_get(src["url"], timeout=15)
                items = parse_html_list(body, src["url"], src["href_re"]) if st == 200 else []
            elif kind == "hf":
                items = fetch_hf_models()
            elif kind == "openrouter":
                items = fetch_openrouter_stealth()
            else:
                return [], "未知类型"
            for it in items:
                it["source"] = name
                it["tier"] = src["tier"]
                it["need_ai"] = need_ai
            return items, "ok({0})".format(len(items))
        except Exception as e:  # noqa: BLE001
            last_err = "{0}: {1}".format(type(e).__name__, str(e)[:60])
    return [], last_err


def fetch_all(days=7, workers=8):
    """并发抓取全部源。失败源自动跳过并记录状态，不影响整体。"""
    items, status = [], {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        jobs = {pool.submit(fetch_source, s, days): s for s in SOURCES}
        for fut in as_completed(jobs):
            src = jobs[fut]
            got, st = fut.result()
            status[src["name"]] = st
            items.extend(got)
    return items, status


# ---------------------------------------------------------------- 快照与筛选
def load_snapshot():
    try:
        with open(SNAP_PATH, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def _apply_quota(kept, max_items):
    """按对标栏目的层级构成分配名额，取各层最高分条目。

    原栏目实测构成：一手官方 ≈50%、聚合媒体 ≈30%、匿名测试位 ≈10%、观点 ≈10%。
    配额只约束上限，某层候选不足时剩余名额回流给其他层，不会造成空层。
    """
    weight = {1: 0.5, 3: 0.3, 4: 0.1, 5: 0.1, 2: 0.0}
    by_tier = {}
    for it in kept:
        by_tier.setdefault(it.get("tier", 9), []).append(it)
    picked, leftover = [], []
    for t in (1, 3, 4, 5, 2):
        group = by_tier.get(t) or []
        if not group:
            continue
        n = max(1, int(round(max_items * weight.get(t, 0.1))))
        picked.extend(group[:n])
        leftover.extend(group[n:])
    remaining = max_items - len(picked)
    if remaining > 0:                      # 某层候选不足时，名额回流给其他层
        leftover.sort(key=lambda x: (x.get("tier", 9), -x.get("score", 0)))
        picked.extend(leftover[:remaining])
    picked.sort(key=lambda x: (x.get("tier", 9), -x.get("score", 0), x.get("date") or ""))
    return picked[:max_items]


def select_items(items, days=7, snap=None, first_run=False, min_items=MIN_ITEMS, max_items=MAX_ITEMS):
    """完整筛选链：时间窗口 / 增量 -> AI 相关性 -> 跨源判重 -> 打分 -> 保底补足。

    返回 (入选条目, 新 URL 表, 过滤统计)。入选条数保证落在 [min_items, max_items]。
    """
    snap = snap or {}
    seen_urls = snap.get("urls") or {}
    today = dt.date.today()
    window_start = today - dt.timedelta(days=days)
    kept, pool, new_urls = [], [], {}
    first_run_seen = {}
    dropped = {"窗口外": 0, "非AI": 0, "重复": 0, "无日期且已见": 0, "首跑无日期丢弃": 0}

    for it in items:
        norm = normalize_url(it.get("url"))
        it["norm_url"] = norm
        if not norm:
            continue
        it["is_new"] = norm not in seen_urls
        new_urls[norm] = seen_urls.get(norm) or dt.datetime.now().isoformat(timespec="seconds")

        if it.get("date"):
            try:
                d = dt.date.fromisoformat(it["date"][:10])
            except ValueError:
                d = None
            if d and d < window_start:
                # 窗口外的不直接丢：进候选池，条数不足时按分数补足（保底机制）
                dropped["窗口外"] += 1
                it["score"] = score_item(it)
                it["url"] = norm
                pool.append(it)
                continue
        elif not it["is_new"]:
            dropped["无日期且已见"] += 1
            continue
        elif first_run:
            # 首次跑没有基线：列表页通常按时间倒序，每源只取最靠前的 2 条——
            # 既避免把历史文章当成新闻，又不让「观点」这类无日期源整层缺席
            n = first_run_seen.get(it.get("source"), 0)
            if n >= 2:
                dropped["首跑无日期丢弃"] += 1
                continue
            first_run_seen[it.get("source")] = n + 1

        if it.get("need_ai") and not ai_related(it.get("title"), it.get("desc"), strict=True):
            dropped["非AI"] += 1
            continue

        dup_idx = None
        for i, k in enumerate(kept):
            if k["norm_url"] == norm or _too_similar(k["title"], it["title"]):
                dup_idx = i
                break
        if dup_idx is not None:
            old = kept[dup_idx]
            if it["tier"] < old["tier"]:      # 更一手的源替换掉聚合源
                it["also_seen"] = (old.get("also_seen") or []) + [old["source"]]
                kept[dup_idx] = it
            else:
                old.setdefault("also_seen", []).append(it["source"])
            dropped["重复"] += 1
            continue

        it["score"] = score_item(it)
        it["url"] = norm          # 输出统一用归一化 URL（剥掉 utm_* 等参数，链接更干净）
        kept.append(it)

    # 打分排序：tier 优先（一手在前），同层按重要性分降序，再按日期
    kept.sort(key=lambda x: (x.get("tier", 9), -x.get("score", 0), x.get("date") or ""))

    # 保底：条数不足时从「被压在下限外」的条目按分数补足（此时放宽到全部候选）
    if len(kept) < min_items:
        short = min_items - len(kept)
        extra = [x for x in pool if x not in kept]
        extra.sort(key=lambda x: -x.get("score", 0))
        kept.extend(extra[:short])

    if len(kept) > max_items:
        kept = _apply_quota(kept, max_items)

    return kept, new_urls, dropped


def save_snapshot(urls):
    os.makedirs(OUT_DIR, exist_ok=True)
    old = load_snapshot()
    merged = dict(old.get("urls") or {})
    merged.update(urls)
    cutoff = (dt.datetime.now() - dt.timedelta(days=180)).isoformat(timespec="seconds")
    merged = {k: v for k, v in merged.items() if not v or v >= cutoff}
    data = {
        "urls": merged,
        "last_run": dt.datetime.now().isoformat(timespec="seconds"),
        "total_seen": len(merged),
    }
    with open(SNAP_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    return data


# ---------------------------------------------------------------- 输出
def build_markdown(items, status, days=7, dropped=None, stamp=None, target=None):
    stamp = stamp or dt.date.today()
    window_start = stamp - dt.timedelta(days=days)
    ok = sum(1 for v in status.values() if v.startswith("ok"))
    tiers_hit = sorted({i.get("tier", 9) for i in items})
    lines = [
        "# 盘点一周AI大事 · {0}".format(stamp.strftime("%Y年%m月%d日")),
        "",
        "> 窗口 {0} ~ {1} ｜ 源 {2}/{3} 可用 ｜ 条目 {4} ｜ 覆盖层级 {5}/4".format(
            window_start.strftime("%m-%d"), stamp.strftime("%m-%d"), ok, len(status),
            len(items), len(tiers_hit)
        ),
        "",
    ]
    if target and len(items) < target:
        lines.append("> ⚠️ 本期条目 {0} 条，低于目标下限 {1} 条，建议放宽窗口或补齐源。".format(len(items), target))
        lines.append("")
    by_tier = {}
    for it in items:
        by_tier.setdefault(it.get("tier", 9), []).append(it)
    for tier in sorted(by_tier):
        group = by_tier[tier]
        lines.append("## {0}".format(TIER_NAMES.get(tier, "其他")))
        lines.append("")
        for it in group:
            tag = " · {0}".format(it["source"]) if it.get("also_seen") else ""
            meta = " `{0}`".format(it["date"]) if it.get("date") else ""
            lines.append("- **{0}**{1}".format(it["title"], meta))
            if it.get("desc"):
                lines.append("  {0}".format(it["desc"]))
            lines.append("  <{0}>{1}".format(it["url"], tag))
        lines.append("")
    if dropped:
        lines.append("---")
        lines.append("")
        lines.append("过滤统计：{0}".format(
            " ｜ ".join("{0} {1}".format(k, v) for k, v in dropped.items() if v)
        ))
        lines.append("")
    lines.append("## 源状态")
    lines.append("")
    for name, st in sorted(status.items(), key=lambda kv: kv[1].startswith("ok"), reverse=True):
        lines.append("- `{0}` {1}".format("OK " if st.startswith("ok") else "FAIL", name + " " + st))
    return "\n".join(lines)


def write_outputs(items, status, days=7, dropped=None, target=None):
    os.makedirs(REPORT_DIR, exist_ok=True)
    stamp = dt.date.today()
    payload = {
        "date": stamp.isoformat(),
        "days": days,
        "count": len(items),
        "items": items,
        "sources": status,
        "dropped": dropped or {},
    }
    with open(LATEST_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
    md = build_markdown(items, status, days=days, dropped=dropped, stamp=stamp, target=target)
    md_path = os.path.join(REPORT_DIR, "AI周报_{0}.md".format(stamp.isoformat()))
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md)
    return md_path, payload


# ---------------------------------------------------------------- CLI
def run(days=7, dry=False, snapshot_only=False, workers=8,
        min_items=MIN_ITEMS, max_items=MAX_ITEMS):
    snap = load_snapshot()
    first_run = not snap
    items, status = fetch_all(days=days, workers=workers)
    kept, new_urls, dropped = select_items(
        items, days=days, snap=snap, first_run=first_run, min_items=min_items, max_items=max_items)
    ok = sum(1 for v in status.values() if v.startswith("ok"))
    tiers = sorted({i.get("tier", 9) for i in kept})
    print("抓取完成：源 {0}/{1} 可用，原始 {2} 条 -> 入选 {3} 条（覆盖 {4} 层）".format(
        ok, len(status), len(items), len(kept), len(tiers)))
    if len(kept) < min_items:
        print("  ⚠️ 低于保底下限 {0} 条".format(min_items))
    for k, v in dropped.items():
        if v:
            print("  过滤 {0}: {1}".format(k, v))
    for name, st in sorted(status.items(), key=lambda kv: kv[1].startswith("ok")):
        print("  [{0}] {1} {2}".format("OK  " if st.startswith("ok") else "FAIL", name, st))
    if dry:
        return kept, status
    snap_data = save_snapshot(new_urls)
    print("快照已更新：累计记录 {0} 条 URL".format(snap_data["total_seen"]))
    if snapshot_only:
        return kept, status
    md_path, _ = write_outputs(kept, status, days=days, dropped=dropped, target=min_items)
    print("报告已生成：{0}".format(md_path))
    return kept, status


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass
    ap = argparse.ArgumentParser(description="AI 周报自动抓取")
    ap.add_argument("--days", type=int, default=7, help="时间窗口天数，默认 7")
    ap.add_argument("--dry", action="store_true", help="只打印统计，不写任何文件")
    ap.add_argument("--snapshot-only", action="store_true", help="只更新快照基线，不出报告")
    ap.add_argument("--workers", type=int, default=8, help="并发数，默认 8")
    ap.add_argument("--min-items", type=int, default=MIN_ITEMS, help="保底条数，默认 12")
    ap.add_argument("--max-items", type=int, default=MAX_ITEMS, help="上限条数，默认 20")
    args = ap.parse_args(argv)
    run(days=args.days, dry=args.dry, snapshot_only=args.snapshot_only,
        workers=args.workers, min_items=args.min_items, max_items=args.max_items)


if __name__ == "__main__":
    main()
