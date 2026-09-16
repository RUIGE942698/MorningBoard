# -*- coding: utf-8 -*-
"""前沿速报 v2：六维百分制评分 + 领域配额 + 事件去重（对标用户提供的 25 条情报筛选方案）。

与 v1 的差别
-----------
1) 信源分层 S/A/B（权威 20/14/8），共 19 源（含实测可达的 Cell / bioRxiv / medRxiv /
   DeepMind / MIT Tech Review / Simons / WHO / Hacker News）
2) 六维百分制：时效30（按领域 τ 指数衰减）｜权威20｜含金量20｜影响力15｜新颖性10｜领域相关5
3) 领域配额（AI 10 / 科技 4 / 物理 3 / 医学 3 / 生物 3 / 数学 2 = 25 条）
4) 约束：单源 ≤3；一手/论文占比 ≥40%；48h 内 ≥70%（可调）
5) 去重：SimHash 相似度（>0.9 合并，0.85~0.9 视为同一事件簇只留一条）+ 7 天历史新颖性
6) 影响力：论文用 OpenAlex 真实引用数，英文科技新闻用 Hacker News 讨论热度，中文用跨源共识度

国内不可达（故未采纳）：OpenAI / Anthropic / Meta 博客、Reddit、Quanta、FDA、PapersWithCode、
Semantic Scholar（429）。embedding 语义聚类无可用服务，改用 SimHash + 实体词近似。

对外接口与 v1 兼容：build_frontier / load_cached / to_tech_payload / check_new_for_push
"""
import difflib
import hashlib
import html as _html
import json
import math
import os
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

try:
    from . import config as _config
    CACHE_DIR = _config.CACHE_DIR
except Exception:  # noqa: BLE001
    CACHE_DIR = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cache")

try:
    from . import ai_gen
except Exception:  # noqa: BLE001
    ai_gen = None

CACHE_FRONTIER = os.path.join(CACHE_DIR, "frontier.json")
CACHE_ZH = os.path.join(CACHE_DIR, "frontier_zh.json")
CACHE_PUSH_STATE = os.path.join(CACHE_DIR, "frontier_push_state.json")
CACHE_ARXIV = os.path.join(CACHE_DIR, "frontier_arxiv.json")
CACHE_HISTORY = os.path.join(CACHE_DIR, "frontier_history.json")
CACHE_INFLUENCE = os.path.join(CACHE_DIR, "frontier_influence.json")

ARXIV_MIN_INTERVAL = 7200
ARXIV_CANDIDATES = 40
ARXIV_PICK_N = 3
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "Chrome/126 Safari/537.36")

# ---------------------------------------------------------------- 信源与账本
# (名称, 地址, 级别, 语言, 抓取类型, 领域提示)
SOURCES = [
    # ---- S 级：一手/权威 ----
    ("Nature", "https://www.nature.com/nature.rss", "S", "en", "rss", None),
    ("Science", "https://www.science.org/rss/news_current.xml", "S", "en", "rss", None),
    ("Cell", "https://www.cell.com/action/showFeed?type=etoc&feed=rss&jc=cell",
     "S", "en", "rss", "biology"),
    ("bioRxiv", "https://api.biorxiv.org/details/biorxiv/{d0}/{d1}",
     "A", "en", "biorxiv", "biology"),
    ("medRxiv", "https://api.medrxiv.org/details/medrxiv/{d0}/{d1}",
     "A", "en", "medrxiv", "medicine"),
    ("arXiv cs.AI", "https://rss.arxiv.org/rss/cs.AI", "S", "en", "arxiv", "ai"),
    ("DeepMind", "https://deepmind.google/blog/rss.xml", "S", "en", "rss", "ai"),
    ("WHO", "https://www.who.int/rss-feeds/news-english.xml", "S", "en", "rss", "medicine"),
    ("Nature Medicine", "https://www.nature.com/nm.rss", "S", "en", "rss", "medicine"),
    ("Nature Biotechnology", "https://www.nature.com/nbt.rss", "S", "en", "rss", "biology"),
    ("Nature Physics", "https://www.nature.com/nphys.rss", "S", "en", "rss", "physics"),
    ("The Lancet", "https://www.thelancet.com/rssfeed/lancet_current.xml",
     "S", "en", "rss", "medicine"),
    ("NEJM", "https://www.nejm.org/action/showFeed?jc=nejm&type=etoc&feed=rss",
     "S", "en", "rss", "medicine"),
    ("JAMA", "https://jamanetwork.com/rss/site_3/67.xml", "S", "en", "rss", "medicine"),
    ("PNAS", "https://www.pnas.org/action/showFeed?type=etoc&feed=rss&jc=pnas",
     "S", "en", "rss", "biology"),
    # ---- A 级：优质编译/深度 ----
    ("MIT Tech Review", "https://www.technologyreview.com/feed/", "A", "en", "rss", "tech"),
    ("Simons Foundation", "https://www.simonsfoundation.org/feed/", "A", "en", "rss", None),
    ("量子位", "https://www.qbitai.com/feed", "A", "zh", "rss", "ai"),
    ("InfoQ 中文", "https://www.infoq.cn/feed", "A", "zh", "rss", "tech"),
    ("Quanta", "https://www.quantamagazine.org/feed/", "A", "en", "rss", None),
    ("eLife", "https://elifesciences.org/rss/recent.xml", "A", "en", "rss", "biology"),
    ("IEEE Spectrum", "https://spectrum.ieee.org/feeds/feed.rss", "A", "en", "rss", "tech"),
    ("Ars Technica", "https://feeds.arstechnica.com/arstechnica/index",
     "A", "en", "rss", "tech"),
    # ---- B 级：高信噪比社区/媒体 ----
    ("Phys.org", "https://phys.org/rss-feed/", "B", "en", "rss", "physics"),
    ("ScienceNews", "https://www.sciencenews.org/feed", "B", "en", "rss", None),
    ("Hacker News", "https://hn.algolia.com/api/v1/search?tags=front_page&hitsPerPage=30",
     "B", "en", "hn", "tech"),
    ("雷峰网", "https://www.leiphone.com/feed", "B", "zh", "rss", "ai"),
    ("极客公园", "https://www.geekpark.net/rss", "B", "zh", "rss", "tech"),
    ("IT 之家", "https://www.ithome.com/rss/", "B", "zh", "rss", "tech"),
    ("少数派", "https://sspai.com/feed", "B", "zh", "rss", "tech"),
    ("掘金", "https://api.juejin.cn/recommend_api/v1/article/recommend_all_feed",
     "B", "zh", "juejin", "tech"),
    ("Solidot", "https://www.solidot.org/index.rss", "B", "zh", "rss", "tech"),
    # ---- 数学：arXiv 分类 RSS（math 总 feed 在本机不可达，分类可用） ----
    ("arXiv math.RT", "https://rss.arxiv.org/rss/math.RT", "S", "en", "arxiv", "math"),
    ("arXiv math.GT", "https://rss.arxiv.org/rss/math.GT", "S", "en", "arxiv", "math"),
    ("arXiv quant-ph", "https://rss.arxiv.org/rss/quant-ph", "S", "en", "arxiv", "physics"),
    ("arXiv astro-ph", "https://rss.arxiv.org/rss/astro-ph", "S", "en", "arxiv", "physics"),
]

AUTHORITY = {"S": 20.0, "A": 14.0, "B": 8.0}

# 信源入口（**网站首页**，不是抓取用的 RSS/API 地址；含第一版的机器之心/InfoQ/掘金等）
SITES = [
    {"name": "量子位", "url": "https://www.qbitai.com/"},
    {"name": "机器之心", "url": "https://www.jiqizhixin.com/"},
    {"name": "InfoQ 中文", "url": "https://www.infoq.cn/"},
    {"name": "掘金", "url": "https://juejin.cn/"},
    {"name": "雷峰网", "url": "https://www.leiphone.com/"},
    {"name": "极客公园", "url": "https://www.geekpark.net/"},
    {"name": "少数派", "url": "https://sspai.com/"},
    {"name": "IT 之家", "url": "https://www.ithome.com/"},
    {"name": "Nature", "url": "https://www.nature.com/news"},
    {"name": "Science", "url": "https://www.science.org/news"},
    {"name": "Cell", "url": "https://www.cell.com/cell/current"},
    {"name": "bioRxiv", "url": "https://www.biorxiv.org/"},
    {"name": "medRxiv", "url": "https://www.medrxiv.org/"},
    {"name": "arXiv", "url": "https://arxiv.org/list/cs.AI/recent"},
    {"name": "DeepMind", "url": "https://deepmind.google/discover/blog/"},
    {"name": "WHO", "url": "https://www.who.int/news"},
    {"name": "MIT Tech Review", "url": "https://www.technologyreview.com/"},
    {"name": "Quanta", "url": "https://www.quantamagazine.org/"},
    {"name": "Simons Foundation", "url": "https://www.simonsfoundation.org/news/"},
    {"name": "Phys.org", "url": "https://phys.org/"},
    {"name": "ScienceNews", "url": "https://www.sciencenews.org/"},
    {"name": "Hacker News", "url": "https://news.ycombinator.com/"},
    {"name": "Nature Medicine", "url": "https://www.nature.com/nm/"},
    {"name": "Nature Biotechnology", "url": "https://www.nature.com/nbt/"},
    {"name": "Nature Physics", "url": "https://www.nature.com/nphys/"},
    {"name": "The Lancet", "url": "https://www.thelancet.com/"},
    {"name": "NEJM", "url": "https://www.nejm.org/"},
    {"name": "JAMA", "url": "https://jamanetwork.com/"},
    {"name": "PNAS", "url": "https://www.pnas.org/"},
    {"name": "eLife", "url": "https://elifesciences.org/"},
    {"name": "IEEE Spectrum", "url": "https://spectrum.ieee.org/"},
    {"name": "Ars Technica", "url": "https://arstechnica.com/"},
    {"name": "Solidot", "url": "https://www.solidot.org/"},
]
DOMAINS = ("ai", "tech", "physics", "medicine", "biology", "math")
DOMAIN_CN = {"ai": "前沿 AI", "tech": "科技产业", "physics": "物理",
             "medicine": "医学", "biology": "生物", "math": "数学"}
TAU_DAYS = {"ai": 1.5, "tech": 2.5, "biology": 3.0, "medicine": 3.0,
            "math": 5.0, "physics": 5.0}

# 领域配额（合计 25）
QUOTA = {"ai": 10, "tech": 4, "physics": 3, "medicine": 3, "biology": 3, "math": 2}
MIN_SCORE = 50.0            # 百分制淘汰线
PUSH_MIN_SCORE = 70.0       # 桌面弹窗阈值（2026-09-12 由 75 下调）
PER_SOURCE_MAX = 3          # 单源上限
SOURCE_MAX = {"bioRxiv": 2, "medRxiv": 2, "Cell": 2, "arXiv cs.AI": 3,
              "Hacker News": 2, "WHO": 1, "arXiv math.RT": 1, "arXiv math.GT": 1,
              "arXiv quant-ph": 1, "arXiv astro-ph": 1,
              "The Lancet": 2, "NEJM": 2, "JAMA": 2, "PNAS": 2,
              "Nature Medicine": 2, "Nature Biotechnology": 2,
              "eLife": 2, "IEEE Spectrum": 2, "Ars Technica": 2, "Solidot": 2}
PAPER_RATIO_TARGET = 0.4    # 一手/论文占比下限（方案要求 0.6，因未审预印本过多会伤质量而调低）
FRESH_48H_TARGET = 0.70     # 48h 内占比下限
INFLUENCE_TOP_N = 12        # 只给前 N 条查真实影响力（控制 API 调用与耗时）
ENRICH_LIMIT = 10
TRANSLATE_LIMIT = 18

PAPER_SOURCES = {"arXiv cs.AI", "bioRxiv", "medRxiv", "Cell", "Nature", "Science",
                 "Simons Foundation", "Nature Medicine", "Nature Biotechnology",
                 "Nature Physics", "The Lancet", "NEJM", "JAMA", "PNAS", "eLife"}

# ---------------------------------------------------------------- 词表
AI_WORDS = [
    "AI", "人工智能", "大模型", "模型", "Agent", "智能体", "推理", "训练", "微调",
    "多模态", "LLM", "GPT", "DeepSeek", "Qwen", "通义", "豆包", "Kimi", "算力",
    "对齐", "强化学习", "RAG", "上下文", "Token", "神经网络", "具身", "机器人",
    "自动驾驶", "Copilot", "MoE", "语言模型", "扩散模型", "transformer", "diffusion",
    "machine learning", "neural", "reasoning", "fine-tun",
]
TECH_WORDS = [
    "芯片", "半导体", "操作系统", "云原生", "开源", "框架", "数据库", "网络安全",
    "6G", "5G", "量子计算", "能源", "电池", "光伏", "航天", "火箭", "卫星", "工程",
    "架构", "编译器", "GPU", "数据中心", "开源模型", "漏洞", "攻击", "chip",
    "semiconductor", "open source", "framework", "database", "security", "satellite",
]
PHYSICS_WORDS = [
    "物理", "量子", "粒子", "引力波", "超导", "核聚变", "天文", "黑洞", "宇宙",
    "中子星", "系外行星", "激光", "拓扑", "相对论", "physics", "quantum", "particle",
    "astronomy", "black hole", "superconduct", "fusion", "galaxy", "cosmic",
]
MED_WORDS = [
    "医学", "临床", "疾病", "癌症", "肿瘤", "疫苗", "药物", "患者", "疗法", "免疫",
    "病毒", "基因治疗", "手术", "公共卫生", "流行病", "阿尔茨海默", "糖尿病",
    "clinical", "cancer", "vaccine", "drug", "patient", "therapy", "disease",
    "trial", "health",
]
BIO_WORDS = [
    "生物", "基因", "蛋白质", "细胞", "基因组", "RNA", "DNA", "CRISPR", "进化",
    "生态", "微生物", "神经科学", "脑", "物种", "gene", "protein", "cell", "genome",
    "CRISPR", "species", "ecosystem", "neuron", "brain", "microb",
]
MATH_WORDS = [
    "数学", "定理", "猜想", "组合", "代数", "几何", "数论", "拓扑", "概率",
    "mathematic", "theorem", "conjecture", "topology", "algebra",
    "geometry", "number theory",
]
# 用户偏好加权：AI 为重点（约 40%）、科技次之
DOMAIN_BOOST = {"ai": 5.0, "tech": 2.0}
DOMAIN_WORDS = {"ai": AI_WORDS, "tech": TECH_WORDS, "physics": PHYSICS_WORDS,
                "medicine": MED_WORDS, "biology": BIO_WORDS, "math": MATH_WORDS}

STRONG_SIGNALS = ["突破", "首次", "首个", "开源", "刷新", "登顶", "领先", "超越",
                  "SOTA", "论文", "发现", "揭示", "实现", "发布", "上线", "测评",
                  "基准", "创纪录", "里程碑", "新纪录", "颠覆",
                  "breakthrough", "first", "novel", "state-of-the-art", "release"]
HEFT_SIGNALS = {
    "code": ["代码", "开源", "github", "code", "dataset", "数据集", "模型权重",
             "checkpoint", "复现", "reproduc"],
    "experiment": ["随机对照", "双盲", "临床试验", "预注册", "消融", "对照实验",
                   "benchmark", "ablation", "randomized", "placebo"],
    "method": ["方法", "架构", "算法", "机理", "机制", "推导", "证明",
               "method", "architecture", "algorithm", "proof"],
    "result": ["提升", "降低", "超过", "优于", "刷新", "显著",
               "improve", "outperform", "reduce", "significant"],
    "original": ["独家", "专访", "原创", "深度", "解读", "复盘", "调研", "实测"],
}
NOISE_WORDS = [
    "游戏", "手游", "网游", "耳机", "鼠标", "键盘", "手机壳", "促销", "优惠",
    "降价", "折扣", "秒杀", "明星", "综艺", "电视剧", "票房", "球员", "赛事",
    "直播回放", "开箱", "晒单", "壁纸", "表情包", "抽奖", "会员订阅", "充值",
    "返现", "如何设置", "手机", "相机", "主摄", "像素", "显示器", "固件",
    "笔记本", "平板", "汽车", "SUV", "轿车", "新车", "预约", "开售", "散热",
    "续航", "充电", "显卡", "路由器", "智能手表", "音箱", "空调", "冰箱", "电视",
    "外卖", "快递", "维修", "防水补漏", "高铁", "铁路", "航班", "民航", "地铁",
    "纪录片", "榜单", "新规", "罚款", "抗议", "起诉", "判刑", "校园", "婚礼",
    "失联", "寻人", "天气", "台风", "暴雨", "菜价", "超市", "餐饮", "景区",
    # 玄学/伪科学内容（避免"紫微几何/道统"这类混入）
    "玄学", "道统", "紫微", "风水", "占卜", "八字", "预言",
    # 期刊样板条目（非内容）
    "audio highlights", "in this issue", "correction", "erratum", "retraction",
    "call for papers", "editorial board", "author correction", "table of contents",
    # 社会案件/事故类（避免伪装成科技新闻混入）
    "被捕", "警方", "审判", "判决", "量刑", "事故", "坠机", "车祸", "失火",
]
PR_WORDS = ["大会", "论坛", "峰会", "揭晓", "颁奖", "获奖", "签约", "发布会直击"]
BOILERPLATE = ["点击查看原文", "阅读原文", "查看更多", "查看全文", "原文链接",
               "责任编辑", "本文来自", "头图来源", "题图来源", "图片来源"]


# ---------------------------------------------------------------- 基础工具
def _clean(text):
    s = _html.unescape(str(text or ""))
    s = re.sub(r"<!\[CDATA\[|\]\]>", "", s)
    s = re.sub(r"<script[\s\S]*?</script>", " ", s, flags=re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    s = _html.unescape(s)
    s = re.sub(r"<[^>]+>", " ", s)
    for b in BOILERPLATE:
        s = s.replace(b, " ")
    return re.sub(r"\s+", " ", s).strip()


def _clean_desc(text):
    s = _clean(text)
    s = re.sub(r"^[>》\-\s|:：,，。]+", "", s).strip()
    if len(s) < 12 or not re.search(r"[\u4e00-\u9fffA-Za-z0-9]", s):
        return ""
    return s


def _norm_url(url):
    u = str(url or "").strip()
    if not u:
        return u
    try:
        p = urlsplit(u)
        q = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True)
             if not k.lower().startswith("utm_")]
        return urlunsplit((p.scheme, p.netloc, p.path, urlencode(q), ""))
    except Exception:  # noqa: BLE001
        return u


def http_get(url, timeout=12, retries=1, backoff=5):
    last = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": UA,
                "Accept": ("application/rss+xml, application/atom+xml, "
                           "application/xml, text/xml, application/json, */*"),
                "Accept-Encoding": "identity",
            })
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8", "ignore")
        except Exception as e:  # noqa: BLE001
            last = e
            if attempt < retries:
                time.sleep(backoff * (attempt + 1))
    raise last


def http_post_json(url, payload, timeout=15, referer="https://juejin.cn/"):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={
        "Content-Type": "application/json", "User-Agent": UA,
        "Referer": referer, "Accept-Encoding": "identity"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "ignore"))


def _parse_date(raw):
    s = _clean(raw)
    if not s:
        return None, ""
    date_only = bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", s))
    dt = None
    try:
        dt = parsedate_to_datetime(s)
    except Exception:  # noqa: BLE001
        try:
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except Exception:  # noqa: BLE001
            return None, ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    if date_only:
        dt = dt + timedelta(hours=12)
    dt = dt.astimezone(timezone.utc)
    return dt, dt.strftime("%Y-%m-%d %H:%M")


def _parse_feed(body):
    out = []
    for b in re.findall(r"<(?:item|entry)[\s>][\s\S]*?</(?:item|entry)>", body or ""):
        t = re.search(r"<title[^>]*>([\s\S]*?)</title>", b)
        m1 = re.search(r"<link[^>]*href=\"([^\"]+)\"", b)
        m2 = re.search(r"<link[^>]*>([\s\S]*?)</link>", b)
        m3 = re.search(r"<guid[^>]*>([\s\S]*?)</guid>", b)
        link = (m1.group(1) if m1 else (m2.group(1) if m2 else (m3.group(1) if m3 else "")))
        d = re.search(r"<(?:pubDate|published|updated|dc:date)[^>]*>([\s\S]*?)"
                      r"</(?:pubDate|published|updated|dc:date)>", b)
        desc = re.search(r"<(?:description|summary|content:encoded)[^>]*>([\s\S]*?)"
                         r"</(?:description|summary|content:encoded)>", b)
        out.append({
            "title": _clean(t.group(1)) if t else "",
            "url": _norm_url(_clean(link)),
            "date_raw": d.group(1) if d else "",
            "desc": _clean_desc(desc.group(1)) if desc else "",
        })
    return out


def _hits(text, words):
    return sum(1 for w in words if w in text)


def _load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:  # noqa: BLE001
        return default


def _save_json(path, data):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
    except Exception:  # noqa: BLE001
        pass


def _mk_item(name, authority, lang, hint, title, url, desc, ts, date):
    return {"source": name, "auth_level": authority, "lang": lang,
            "group_hint": hint, "title": title, "url": url, "desc": desc,
            "ts": ts, "date": date, "date_unknown": ts == 0.0, "paper": False}


# ---------------------------------------------------------------- 抓取
def fetch_source(name, url, level, lang, kind, hint, timeout=12, retries=1):
    try:
        body = http_get(url, timeout=timeout, retries=retries)
    except Exception:  # noqa: BLE001
        return []
    items = []
    for e in _parse_feed(body):
        if not e["title"] or not e["url"]:
            continue
        dt, ds = _parse_date(e["date_raw"])
        it = _mk_item(name, level, lang, hint, e["title"], e["url"], e["desc"],
                      dt.timestamp() if dt else 0.0, ds)
        it["paper"] = (kind == "arxiv")
        items.append(it)
    return items


def _fetch_arxiv_source(name, timeout=20):
    """按源分别缓存（cs.AI / math.RT / math.GT 各自独立，避免互相污染）。"""
    cache = _load_json(CACHE_ARXIV, {"sources": {}})
    sources = cache.get("sources") or {}
    rec = sources.get(name)
    if rec and rec.get("items") and (time.time() - rec.get("ts", 0)) < ARXIV_MIN_INTERVAL:
        return rec["items"], "cache"
    spec = [s for s in SOURCES if s[0] == name]
    if not spec:
        return [], "none"
    _, url, level, lang, kind, hint = spec[0]
    got = fetch_source(name, url, level, lang, kind, hint,
                       timeout=timeout, retries=2)
    if got:
        got.sort(key=lambda x: -(x.get("ts") or 0))
        got = got[:ARXIV_CANDIDATES]
        for x in got:
            x["paper"] = True
        sources[name] = {"ts": time.time(), "items": got}
        _save_json(CACHE_ARXIV, {"sources": sources})
        return got, "live"
    stale = (rec or {}).get("items") or []
    return stale, ("stale-cache" if stale else "failed")


def fetch_biorxiv(api_tpl, name, level, hint, days=2, timeout=20):
    """bioRxiv/medRxiv 预印本 API：按日期区间取最近提交。"""
    today = datetime.now(timezone.utc).date()
    d0 = (today - timedelta(days=days)).isoformat()
    d1 = today.isoformat()
    url = api_tpl.format(d0=d0, d1=d1)
    try:
        d = json.loads(http_get(url, timeout=timeout, retries=1))
    except Exception:  # noqa: BLE001
        return []
    out = []
    for row in (d.get("collection") or [])[:60]:
        title = _clean(row.get("title"))
        if not title:
            continue
        doi = (row.get("doi") or "").strip()
        dt, ds = _parse_date(row.get("date"))
        it = _mk_item(name, level, "en", hint, title,
                      "https://doi.org/" + doi if doi else "",
                      _clean_desc(row.get("abstract") or ""),
                      dt.timestamp() if dt else 0.0, ds)
        it["paper"] = True
        it["doi"] = doi
        it["category"] = _clean(row.get("category") or "")
        out.append(it)
    return out


def fetch_jqzx(limit=20, timeout=15):
    """机器之心首页列表（无 RSS，抓 HTML）。"""
    try:
        body = http_get("https://www.jiqizhixin.com/", timeout=timeout, retries=1)
    except Exception:  # noqa: BLE001
        return []
    out, seen = [], set()
    for m in re.finditer(r'<a[^>]+href="(/articles/[^"]+)"[^>]*>([\s\S]{6,120}?)</a>', body):
        href, text = m.group(1), _clean(m.group(2))
        if not text or len(text) < 8 or href in seen:
            continue
        seen.add(href)
        out.append(_mk_item("机器之心", "A", "zh", "ai", text,
                            "https://www.jiqizhixin.com" + href, "", 0.0, ""))
        if len(out) >= limit:
            break
    return out


def fetch_hn(limit=30, timeout=12):
    """Hacker News 首页（Algolia 公开 API）：一次拿到条目 + 热度。"""
    spec = [s for s in SOURCES if s[4] == "hn"]
    if not spec:
        return []
    try:
        d = json.loads(http_get(spec[0][1], timeout=timeout, retries=1))
    except Exception:  # noqa: BLE001
        return []
    out = []
    for h in (d.get("hits") or [])[:limit]:
        title = _clean(h.get("title") or "")
        if not title:
            continue
        url = h.get("url") or "https://news.ycombinator.com/item?id={0}".format(
            h.get("objectID"))
        ts = float(h.get("created_at_i") or 0)
        pts, cmt = int(h.get("points") or 0), int(h.get("num_comments") or 0)
        desc = _clean_desc(h.get("story_text") or "") or \
            "HN 热议 {0} 分 · {1} 条评论".format(pts, cmt)
        it = _mk_item("Hacker News", "B", "en", "tech", title, _norm_url(url),
                      desc, ts,
                      (datetime.fromtimestamp(ts, timezone.utc)
                       .strftime("%Y-%m-%d %H:%M") if ts else ""))
        it["hn_points"], it["hn_comments"] = pts, cmt
        out.append(it)
    return out


def fetch_juejin(limit=20, timeout=15):
    spec = [s for s in SOURCES if s[4] == "juejin"]
    if not spec:
        return []
    api = spec[0][1]
    try:
        d = http_post_json(api, {"id_type": 2, "sort_type": 3, "cursor": "0",
                                 "limit": 20}, timeout=timeout)
    except Exception:  # noqa: BLE001
        return []
    out = []
    for it in (d.get("data") or []):
        art = ((it.get("item_info") or {}).get("article_info")) or {}
        title = (art.get("title") or "").strip()
        if not title:
            continue
        ts = 0.0
        try:
            ct = int(art.get("ctime") or 0)
            ts = ct / 1000.0 if ct > 1e11 else float(ct)
        except Exception:  # noqa: BLE001
            ts = 0.0
        out.append(_mk_item("掘金", "B", "zh", "tech", title,
                            _norm_url("https://juejin.cn/post/{0}".format(
                                art.get("article_id", ""))),
                            _clean_desc(art.get("brief_content") or ""), ts,
                            (datetime.fromtimestamp(ts, timezone.utc)
                             .strftime("%Y-%m-%d %H:%M") if ts else "")))
        if len(out) >= limit:
            break
    return out


LAST_FETCH_COUNTS = {}


def fetch_all(timeout=12, days=5):
    now = time.time()
    out = []
    LAST_FETCH_COUNTS.clear()
    for name, url, level, lang, kind, hint in SOURCES:
        if kind == "arxiv":
            got, how = _fetch_arxiv_source(name, timeout=max(timeout, 20))
            LAST_FETCH_COUNTS[name] = "{0}({1})".format(len(got), how)
        elif kind in ("biorxiv", "medrxiv"):
            got = fetch_biorxiv(url, name, level, hint, days=2,
                                timeout=max(timeout, 20))
            LAST_FETCH_COUNTS[name] = len(got)
        elif kind == "juejin":
            got = fetch_juejin(timeout=max(timeout, 15))
            LAST_FETCH_COUNTS[name] = len(got)
        elif kind == "hn":
            got = fetch_hn(timeout=max(timeout, 12))
            LAST_FETCH_COUNTS[name] = len(got)
        elif kind == "jqzx":
            got = fetch_jqzx(timeout=max(timeout, 15))
            LAST_FETCH_COUNTS[name] = len(got)
        else:
            got = fetch_source(name, url, level, lang, kind, hint,
                               timeout=timeout, retries=1)
            LAST_FETCH_COUNTS[name] = len(got)
        out.extend([x for x in got
                    if not x["ts"] or (now - x["ts"]) <= days * 86400])
    return out


# ---------------------------------------------------------------- 领域判定
def classify_domain(it):
    title = it.get("title", "")
    desc = it.get("desc", "")
    scores = {}
    for dom, words in DOMAIN_WORDS.items():
        s = _hits(title, words) * 2 + _hits(desc, words)
        scores[dom] = s
    hint = it.get("group_hint")
    # 源先验只在"该领域确有词命中"或"全无命中"时生效，避免压过真实证据
    if hint in scores and (scores[hint] > 0 or max(scores.values()) == 0):
        scores[hint] += 1.2
    best = max(scores, key=lambda k: (scores[k], k == "ai"))
    if scores[best] <= 0:
        best = hint if hint in DOMAINS else "tech"
    it["domain_scores"] = scores
    it["domain"] = best
    it["domain_strength"] = scores[best]
    return best


# ---------------------------------------------------------------- 新颖性（SimHash）
def _simhash(text, bits=64):
    text = re.sub(r"[\s\W_]+", "", str(text or "").lower())
    if not text:
        return 0
    grams = [text[i:i + 3] for i in range(max(1, len(text) - 2))]
    vec = [0] * bits
    for g in grams:
        h = int(hashlib.md5(g.encode("utf-8")).hexdigest()[:16], 16)
        for i in range(bits):
            vec[i] += 1 if (h >> i) & 1 else -1
    out = 0
    for i in range(bits):
        if vec[i] > 0:
            out |= (1 << i)
    return out


def _hamming(a, b):
    return bin(a ^ b).count("1")


def sim(a, b):
    return 1.0 - _hamming(a, b) / 64.0


def load_history():
    return _load_json(CACHE_HISTORY, [])


def save_history(entries):
    _save_json(CACHE_HISTORY, entries[-1500:])


# ---------------------------------------------------------------- 影响力
def _openalex_citations(doi=None, title=None, timeout=12):
    try:
        if doi:
            q = "https://api.openalex.org/works/doi:" + urllib.parse.quote(doi)
            d = json.loads(http_get(q, timeout=timeout, retries=0))
            return int((d or {}).get("cited_by_count") or 0)
        q = ("https://api.openalex.org/works?filter=title.search:" +
             urllib.parse.quote((title or "")[:120]) +
             "&per_page=1&select=id,cited_by_count")
        d = json.loads(http_get(q, timeout=timeout, retries=0))
        res = (d or {}).get("results") or []
        return int(res[0].get("cited_by_count") or 0) if res else 0
    except Exception:  # noqa: BLE001
        return None


def _hn_engagement(title, timeout=12):
    try:
        q = ("https://hn.algolia.com/api/v1/search?tags=story&hitsPerPage=1&query=" +
             urllib.parse.quote((title or "")[:120]))
        d = json.loads(http_get(q, timeout=timeout, retries=0))
        hits = (d or {}).get("hits") or []
        if not hits:
            return None
        return int(hits[0].get("points") or 0), int(hits[0].get("num_comments") or 0)
    except Exception:  # noqa: BLE001
        return None


def attach_influence(items, top_n=INFLUENCE_TOP_N):
    """给分数最高的若干条查真实影响力（论文引用 / HN 热度），结果缓存 6 小时。"""
    cache = _load_json(CACHE_INFLUENCE, {})
    now = time.time()
    for it in sorted(items, key=lambda x: -(x.get("score_pre") or 0))[:top_n]:
        key = it.get("doi") or it.get("url")
        rec = cache.get(key)
        if rec and (now - rec.get("ts", 0)) < 6 * 3600:
            it["cites"] = rec.get("cites")
            it["hn_points"] = rec.get("hn_points")
            it["hn_comments"] = rec.get("hn_comments")
            continue
        cites = hn = hnc = None
        if it.get("doi") or it.get("paper"):
            cites = _openalex_citations(doi=it.get("doi"), title=it.get("title"))
        if it.get("lang") == "en" and it.get("source") in (
                "MIT Tech Review", "DeepMind", "Nature", "Science",
                "Simons Foundation", "Quanta"):
            got = _hn_engagement(it.get("title"))
            if got:
                hn, hnc = got
        it["cites"], it["hn_points"], it["hn_comments"] = cites, hn, hnc
        cache[key] = {"ts": now, "cites": cites, "hn_points": hn, "hn_comments": hnc}
    _save_json(CACHE_INFLUENCE, cache)
    return items


# ---------------------------------------------------------------- 六维打分
def score_v2(it, now=None, history_hashes=None, cluster_hashes=None):
    now = now or time.time()
    text = it.get("title", "") + " " + (it.get("desc") or "")
    dom = it.get("domain") or classify_domain(it)
    dims, detail = {}, []

    # 1) 时效 30：按领域 τ 指数衰减
    tau = TAU_DAYS.get(dom, 2.0)
    if it.get("date_unknown"):
        dt_days = 1.0
    else:
        dt_days = max(0.0, (now - (it.get("ts") or now)) / 86400.0)
    dims["time"] = round(30.0 * math.exp(-dt_days / tau), 2)

    # 2) 权威 20
    dims["authority"] = AUTHORITY.get(it.get("auth_level", "B"), 8.0)

    # 3) 含金量 20：证据/方法/结果/原创性信号（按"证据强度"分级，避免摘要套话虚高）
    heft = 3.0
    code = _hits(text, HEFT_SIGNALS["code"])
    exp = _hits(text, HEFT_SIGNALS["experiment"])
    method = _hits(text, HEFT_SIGNALS["method"])
    result = _hits(text, HEFT_SIGNALS["result"])
    orig = _hits(text, HEFT_SIGNALS["original"])
    if code:
        heft += min(4.0, 2.5 + code)
    if exp:
        heft += min(4.0, 2.5 + exp)
    if method:
        heft += min(2.0, 1.0 + method * 0.5)
    if result:
        heft += min(2.0, 1.0 + result * 0.5)
    if orig:
        heft += min(3.0, 1.5 + orig)
    if it.get("paper"):
        heft += 2.0
    if len(it.get("desc") or "") >= 120:
        heft += 2.0
    if len(it.get("desc") or "") < 40:
        heft -= 3.0
    cites = it.get("cites") or 0
    if cites:
        heft += min(3.0, math.log10(cites + 1) * 1.5)
    dims["heft"] = round(max(0.0, min(20.0, heft)), 2)

    # 4) 影响力 15：引用 / HN 热度 / 跨源共识
    infl = 1.5
    if cites:
        infl += min(9.0, math.log10(cites + 1) * 4.0)
    pts = it.get("hn_points") or 0
    if pts:
        infl += min(7.0, math.log10(pts + 1) * 3.0)
    also = len(it.get("also_in") or [])
    if also >= 2:
        infl += 6.0
    elif also == 1:
        infl += 3.5
    dims["influence"] = round(min(15.0, infl), 2)

    # 5) 新颖性 10：与近 3 天历史/本轮已选内容的相似度反向计分（用标题指纹）
    h = _simhash(it.get("title", ""))
    it["simhash"] = h
    worst = 0.0
    for ref in (history_hashes or []):
        worst = max(worst, sim(h, ref))
    for ref in (cluster_hashes or []):
        worst = max(worst, sim(h, ref))
    it["max_sim"] = round(worst, 3)
    dims["novelty"] = round(10.0 * max(0.0, 1.0 - worst), 2)

    # 6) 领域相关 5
    strength = it.get("domain_strength", 0)
    dims["relevance"] = 5.0 if strength >= 4 else (3.5 if strength >= 2 else
                                                  (1.5 if strength >= 1 else 0.0))

    total = sum(dims.values())
    strong = _hits(text, STRONG_SIGNALS)
    noise = _hits(text, NOISE_WORDS)
    pr = _hits(text, PR_WORDS)
    if noise:
        pen = min(12.0, noise * 3.0)
        total -= pen
        detail.append("噪声-{0}".format(pen))
    if pr:
        pen = min(4.0, pr * 1.5)
        total -= pen
        detail.append("会议稿-{0}".format(pen))
    if strong:
        total += min(4.0, strong * 1.0)
        detail.append("信号+{0}".format(min(4.0, strong * 1.0)))
    boost = DOMAIN_BOOST.get(dom, 0.0)
    if boost:
        total += boost
        detail.append("领域加权+{0}".format(boost))

    it["dims"] = dims
    it["score"] = round(max(0.0, min(100.0, total)), 1)
    it["score_pre"] = it["score"]
    it["score_detail"] = " ".join(
        "{0}={1}".format(k, v) for k, v in dims.items()) + (
        (" | " + ",".join(detail)) if detail else "")
    it["age_hours"] = None if it.get("date_unknown") else round(dt_days * 24, 1)
    return it


# ---------------------------------------------------------------- 中文摘要
def ai_available():
    try:
        return bool(ai_gen and ai_gen.enabled())
    except Exception:  # noqa: BLE001
        return False


def translate_items(items, limit=TRANSLATE_LIMIT, timeout=120):
    cache = _load_json(CACHE_ZH, {})
    todo = [x for x in items if x.get("lang") == "en" and x["url"] not in cache][:limit]
    if todo and ai_available():
        lines = []
        for i, x in enumerate(todo, 1):
            lines.append("{0}. 标题: {1}\n   摘要: {2}".format(
                i, x.get("title", "")[:200], (x.get("desc") or "")[:300]))
        prompt = (
            "把下面每条英文科技/科学资讯翻译成中文，输出严格 JSON 数组，"
            "元素为 {\"i\": 序号, \"t\": 中文标题(不超过 40 字，专有名词保留原文), "
            "\"s\": 一句话中文摘要(不超过 70 字，说明做了什么、为什么重要)}。"
            "只输出 JSON。\n\n" + "\n".join(lines))
        try:
            txt = ai_gen._chat(prompt, max_tokens=2000, timeout=timeout)
            m = re.search(r"\[[\s\S]*\]", txt or "")
            rows = json.loads(m.group(0)) if m else []
            for row in rows:
                try:
                    idx = int(row.get("i")) - 1
                    if 0 <= idx < len(todo):
                        cache[todo[idx]["url"]] = {
                            "t": _clean(row.get("t", ""))[:80],
                            "s": _clean(row.get("s", ""))[:160]}
                except Exception:  # noqa: BLE001
                    continue
            _save_json(CACHE_ZH, cache)
        except Exception:  # noqa: BLE001
            pass
    for x in items:
        if x.get("lang") == "en":
            zh = cache.get(x["url"])
            if zh:
                x["title_en"] = x["title"]
                x["title_zh"] = zh.get("t", "")
                x["desc_zh"] = zh.get("s", "")
    return items


def ai_pick_papers(items, n=ARXIV_PICK_N, timeout=90):
    cand = items[:ARXIV_CANDIDATES]
    if not cand:
        return []
    cache = _load_json(CACHE_ZH, {})
    cached_picks = [x for x in cand if (cache.get(x["url"]) or {}).get("t")]
    if cached_picks:
        out = []
        for x in cached_picks[:n]:
            x["title_en"], x["title_zh"] = x["title"], cache[x["url"]]["t"]
            x["desc_zh"] = cache[x["url"]].get("s", "")
            x["ai_picked"] = True
            out.append(x)
        return out
    if not ai_available():
        return cand[:n]
    lines = ["{0}. 标题: {1}\n   摘要: {2}".format(
        i, x.get("title", "")[:180], (x.get("desc") or "")[:260])
        for i, x in enumerate(cand, 1)]
    prompt = (
        "下面是 arXiv 今日新提交的论文候选。请挑出对 AI 领域最有分量、最具新颖性的 {0} 篇，"
        "标准：新方法/新范式、通用性强、结果显著、有实验或开源支撑；避免增量式小改与纯综述。"
        "输出严格 JSON 数组，元素为 {{\"i\": 序号, \"t\": 中文标题(不超过 40 字), "
        "\"s\": 一句话中文摘要(不超过 70 字)}}。只输出 JSON。\n\n").format(n) + "\n".join(lines)
    try:
        txt = ai_gen._chat(prompt, max_tokens=1500, timeout=timeout)
        m = re.search(r"\[[\s\S]*\]", txt or "")
        rows = json.loads(m.group(0)) if m else []
    except Exception:  # noqa: BLE001
        rows = []
    picked = []
    for row in rows:
        try:
            idx = int(row.get("i")) - 1
        except Exception:  # noqa: BLE001
            continue
        if not (0 <= idx < len(cand)):
            continue
        x = cand[idx]
        x["title_en"], x["title_zh"] = x["title"], _clean(row.get("t", ""))[:80]
        x["desc_zh"] = _clean(row.get("s", ""))[:160]
        x["ai_picked"] = True
        if x["title_zh"]:
            cache[x["url"]] = {"t": x["title_zh"], "s": x["desc_zh"]}
        picked.append(x)
    if picked:
        _save_json(CACHE_ZH, cache)
        return picked[:n]
    return cand[:n]


# ---------------------------------------------------------------- 去重与选条
def dedupe_events(items):
    """SimHash：>0.9 判为重复合并；0.85~0.9 视为同一事件簇（只留高分者）。"""
    items = sorted(items, key=lambda x: -(x.get("score") or 0))
    kept = []
    for it in items:
        h = it.get("simhash") or _simhash(it.get("title", ""))
        dup = None
        for k in kept:
            s = sim(h, k["simhash"])
            if s > 0.9 or s >= 0.85:
                dup = k
                break
        if dup is None:
            kept.append(it)
        else:
            dup.setdefault("also_in", []).append(it.get("source", ""))
    return kept


def select_with_quota(items, quota=None, per_source_max=PER_SOURCE_MAX,
                      paper_target=PAPER_RATIO_TARGET,
                      fresh_target=FRESH_48H_TARGET):
    """按分排序 + 贪心填入 + 配额/单源/一手占比/新鲜度约束校验。"""
    quota = dict(quota or QUOTA)
    total_target = sum(quota.values())
    items = sorted(items, key=lambda x: -(x.get("score") or 0))
    picked, src_count, dom_count = [], {}, {d: 0 for d in DOMAINS}

    def allowed(it, strict=True):
        if src_count.get(it["source"], 0) >= SOURCE_MAX.get(it["source"], per_source_max):
            return False
        d = it.get("domain")
        if strict and dom_count.get(d, 0) >= quota.get(d, 0):
            return False
        return True

    # 第一轮：严格按配额
    for it in items:
        if len(picked) >= total_target:
            break
        if it["domain"] not in DOMAINS or not allowed(it):
            continue
        picked.append(it)
        src_count[it["source"]] = src_count.get(it["source"], 0) + 1
        dom_count[it["domain"]] += 1

    # 第二轮：配额未满时按"领域优先级"补足（AI/科技优先），仍守单源上限
    if len(picked) < total_target:
        order = ["ai", "tech", "physics", "medicine", "biology", "math"]
        by_dom = {d: [x for x in items if x.get("domain") == d] for d in order}
        cursor = {d: 0 for d in order}
        progressed = True
        while len(picked) < total_target and progressed:
            progressed = False
            for d in order:
                pool = by_dom[d]
                while cursor[d] < len(pool):
                    cand = pool[cursor[d]]
                    cursor[d] += 1
                    if cand in picked or not allowed(cand, strict=False):
                        continue
                    picked.append(cand)
                    src_count[cand["source"]] = src_count.get(cand["source"], 0) + 1
                    dom_count[d] = dom_count.get(d, 0) + 1
                    progressed = True
                    break
                if len(picked) >= total_target:
                    break

    # 约束校验（不满足只记录，不强行塞低质内容）
    n = len(picked) or 1
    paper_ratio = sum(1 for x in picked if x["source"] in PAPER_SOURCES) / n
    fresh_ratio = sum(1 for x in picked
                      if (x.get("age_hours") is None or x["age_hours"] <= 48)) / n
    return picked, {
        "paper_ratio": round(paper_ratio, 2), "paper_target": paper_target,
        "fresh48_ratio": round(fresh_ratio, 2), "fresh_target": fresh_target,
        "by_domain": dom_count, "by_source": src_count,
    }


def fetch_summary(url, timeout=15):
    if not url:
        return ""
    try:
        body = http_get(url, timeout=timeout, retries=0)
    except Exception:  # noqa: BLE001
        return ""
    head = body[:300000]
    for tag in re.findall(r"<meta\b[^>]*>", head, re.I):
        low = tag.lower()
        if ("og:description" in low or "name=\"description\"" in low
                or "name='description'" in low):
            m = re.search(r"content=[\"']([^\"']+)[\"']", tag, re.I)
            if m:
                s = _clean_desc(m.group(1))
                if s:
                    return s[:300]
    m = re.search(r"<p[^>]*>([\s\S]{40,600}?)</p>", head, re.I)
    return _clean_desc(m.group(1))[:300] if m else ""


# ---------------------------------------------------------------- 读懂它
# 面向非专业读者降低阅读门槛：人话版 + 关键概念解释 + 为什么值得关注。
# 关键概念优先用 MorningBoard 现成的术语词典（383 条，免费离线），AI 只补词典里没有的。
CACHE_EXPLAIN = os.path.join(CACHE_DIR, "frontier_explain.json")
CACHE_VOCAB = os.path.join(CACHE_DIR, "frontier_vocab.json")
CACHE_VOCAB_DIR = os.path.join(CACHE_DIR, "vocab")   # 按天存档：vocab/<日期>.json
VOCAB_CAP = 5000                                   # 滚动总表上限（按天存档不受限）
EXPLAIN_VERSION = 2
EXPLAIN_LIMIT = 25
_TERM_INDEX = None


def term_index():
    """本地术语词典索引：术语名（含括号/顿号别名）-> {t, d, domain}。"""
    global _TERM_INDEX
    if _TERM_INDEX is not None:
        return _TERM_INDEX
    idx = {}
    lib = []
    try:
        from . import knowledge as _k
        lib = _k.load_term_library() or []
    except Exception:  # noqa: BLE001
        lib = []
    for t in lib:
        name = _clean(t.get("t") or "")
        if len(name) < 2:
            continue
        defn = _clean(t.get("s") or "")
        if not defn:
            body = t.get("b") or []
            defn = _clean(body[0]) if body else ""
        if not defn:
            continue
        rec = {"t": name, "d": defn[:70], "domain": t.get("domain", "")}
        keys = {name}
        for part in re.split(r"[（(）、/,，;；]", name):
            part = part.strip()
            if len(part) >= 2:
                keys.add(part)
        for k in keys:
            idx.setdefault(k, rec)
    _TERM_INDEX = idx
    return idx


def match_local_terms(it, limit=3):
    """在标题/摘要里找词典里已有的术语（长词优先、不重叠）。"""
    idx = term_index()
    if not idx:
        return []
    text = " ".join([it.get("title", ""), it.get("desc") or "",
                     it.get("title_zh") or "", it.get("desc_zh") or ""])
    found, spans = [], []
    for key in sorted(idx, key=len, reverse=True):
        pos = text.find(key)
        if pos < 0:
            continue
        if any(a <= pos < b for a, b in spans):
            continue
        spans.append((pos, pos + len(key)))
        found.append(dict(idx[key], src="dict"))
        if len(found) >= limit:
            break
    return found


def _difficulty(it, n_terms):
    """阅读难度粗判：通俗 / 中等 / 专业。"""
    score = 0
    if it.get("domain") in ("physics", "math"):
        score += 2
    elif it.get("domain") in ("medicine", "biology"):
        score += 1
    if n_terms >= 3:
        score += 1
    if it.get("source") in PAPER_SOURCES:
        score += 1
    return "专业" if score >= 3 else ("中等" if score >= 1 else "通俗")


def _tolerant_rows(text):
    """容错解析模型返回的 JSON 数组：整体失败时逐个对象抢救。"""
    if not text:
        return []
    m = re.search(r"\[[\s\S]*\]", text)
    if m:
        try:
            rows = json.loads(m.group(0))
            if isinstance(rows, list):
                return rows
        except Exception:  # noqa: BLE001
            pass
    out = []
    for obj in re.finditer(r"\{[^{}]*\}", text):
        try:
            rows = json.loads(obj.group(0))
            if isinstance(rows, dict) and "i" in rows:
                out.append(rows)
        except Exception:  # noqa: BLE001
            continue
    return out


def explain_items(items, limit=EXPLAIN_LIMIT, timeout=120, chunk=6):
    """补"读懂它"：人话版 / 关键概念（词典优先 + AI 补足） / 先修知识 / 为什么值得关注。

    - 结果按 URL 缓存，同一篇文章不重复花钱
    - AI 分批（默认每批 6 条）调用并容错解析，避免一次输出过长被截断
    """
    cache = _load_json(CACHE_EXPLAIN, {})
    todo = []
    for it in items[:limit]:
        key = it.get("url") or it.get("title") or ""
        if key and (cache.get(key) or {}).get("v") != EXPLAIN_VERSION:
            todo.append(it)
    if todo and ai_available():
        for start in range(0, len(todo), chunk):
            batch = todo[start:start + chunk]
            lines = []
            for i, x in enumerate(batch, 1):
                known = [t["t"] for t in match_local_terms(x)]
                lines.append(
                    "{0}. 标题: {1}\n   摘要: {2}\n   词典已有的词(不要重复): {3}".format(
                        i, (x.get("title_zh") or x.get("title", ""))[:120],
                        (x.get("desc_zh") or x.get("desc") or "")[:240],
                        "、".join(known) or "无"))
            prompt = (
                "你是科普编辑，任务是把科技/科学资讯讲给**非专业读者**听，降低阅读门槛。"
                "对下面每条输出严格 JSON 数组，元素为 {{\"i\": 序号, "
                "\"eli5\": \"用一句人话说清这条讲了什么（≤45 字，尽量不用术语）\", "
                "\"why\": \"为什么值得关注（≤30 字）\", "
                "\"terms\": [{{\"t\": \"生僻概念/方法名/缩写\", \"d\": \"一句话解释（≤30 字，可用打比方）\"}}], "
                "\"pre\": [{{\"t\": \"读懂它需要先知道的概念\", \"d\": \"一句话解释（≤30 字）\"}}]}}。"
                "terms 只挑读者可能看不懂的词，给 0-3 个；pre 给 0-2 个（很专业的题目才给，通俗题给空数组）；"
                "已在\"词典已有的词\"里的不要重复。只输出 JSON，不要解释。\n\n" + "\n".join(lines))
            try:
                txt = ai_gen._chat(prompt, max_tokens=2000, timeout=timeout)
                rows = _tolerant_rows(txt)
            except Exception:  # noqa: BLE001
                rows = []
            for row in rows:
                try:
                    i = int(row.get("i")) - 1
                except Exception:  # noqa: BLE001
                    continue
                if not (0 <= i < len(batch)):
                    continue
                target = batch[i]
                key = target.get("url") or target.get("title")

                def _pairs(key_name, cap):
                    out = []
                    for t in (row.get(key_name) or [])[:cap]:
                        name = _clean(t.get("t", ""))[:30]
                        desc = _clean(t.get("d", ""))[:60]
                        if name and desc:
                            out.append({"t": name, "d": desc})
                    return out

                cache[key] = {"v": EXPLAIN_VERSION,
                              "eli5": _clean(row.get("eli5", ""))[:80],
                              "why": _clean(row.get("why", ""))[:60],
                              "terms": _pairs("terms", 3),
                              "pre": _pairs("pre", 2)}
            _save_json(CACHE_EXPLAIN, cache)     # 每批都落盘，失败不影响已完成批次
    for it in items[:limit]:
        key = it.get("url") or it.get("title") or ""
        rec = cache.get(key) or {}
        merged, seen = [], set()
        for t in [dict(x, src="ai") for x in (rec.get("terms") or [])] + match_local_terms(it):
            n = t.get("t", "")
            if not n or n in seen:
                continue
            seen.add(n)
            merged.append(t)
        it["explain"] = {"eli5": rec.get("eli5", ""), "why": rec.get("why", ""),
                         "terms": merged[:4],
                         "prereq": [dict(x, src="ai") for x in (rec.get("pre") or [])][:2],
                         "difficulty": _difficulty(it, len(merged))}
    return items


def reload_terms():
    """清空术语索引缓存（新增术语后调用）。"""
    global _TERM_INDEX
    _TERM_INDEX = None


# 生词领域 -> 术语词典领域名（词典里没有的会自动新建文件）
VOCAB_TERM_DOMAIN = {"ai": "AI 科技", "tech": "科技", "physics": "物理",
                     "biology": "生物", "medicine": "医学/健康",
                     "math": "数学", "其他": "前沿速报"}


def all_known_terms():
    """界面可能点到的全部概念：生词总表 + "读懂它"缓存（含已不在当日 25 条里的）。"""
    rows = list(load_vocab().get("items") or [])
    seen = {r.get("t") for r in rows}
    cache = _load_json(CACHE_EXPLAIN, {}) or {}
    by_url = {x.get("url"): x for x in ((load_cached() or {}).get("items") or [])}
    for url, rec in cache.items():
        it = by_url.get(url) or {}
        for t in list(rec.get("terms") or []) + list(rec.get("pre") or []):
            name = (t.get("t") or "").strip()
            if not name or name in seen:
                continue
            seen.add(name)
            rows.append({"t": name, "d": t.get("d", ""),
                         "domain": it.get("domain") or "其他",
                         "item": (it.get("title") or "")[:60], "url": url})
    return rows


def sync_vocab_to_terms(rows=None, per_domain=120):
    """把"界面能点到的概念"里词典还没有的追加进术语词典，确保点击跳转必有内容。

    已有领域走 terms_updater.append_terms；没有的领域（如"数学"）自动建词典文件。
    返回新增条数。
    """
    try:
        from . import config as _cfg
        from . import knowledge as _k
        from . import terms_updater as _tu
    except Exception:  # noqa: BLE001
        return 0
    rows = rows if rows is not None else all_known_terms()
    try:
        lib = _k.load_term_library() or []
    except Exception:  # noqa: BLE001
        lib = []
    existing_titles = {t.get("t") for t in lib}
    existing_domains = {t.get("domain") for t in lib}

    groups = {}
    for r in rows:
        name = (r.get("t") or "").strip()
        if not name or name in existing_titles:
            continue
        dom = VOCAB_TERM_DOMAIN.get(r.get("domain") or "", "前沿速报")
        desc = (r.get("d") or "").strip()
        src = (r.get("item") or "").strip()
        groups.setdefault(dom, []).append({
            "t": name,
            "s": desc[:40] if desc else name,
            "b": [p for p in [desc,
                              ("出自《{0}》".format(src) if src else "")] if p],
            "links": [],
        })

    added = 0
    for dom, items in groups.items():
        items = items[:per_domain]
        if dom in existing_domains:
            try:
                added += _tu.append_terms(dom, items) or 0
            except Exception:  # noqa: BLE001
                continue
            continue
        path = os.path.join(_cfg.TERMS_DIR, "terms_frontier_{0}.json".format(
            abs(hash(dom)) % 100000))
        data = _load_json(path, {"domain": dom, "items": []}) or {"domain": dom, "items": []}
        have = {it.get("t") for it in (data.get("items") or [])}
        fresh = [it for it in items if it.get("t") not in have]
        if not fresh:
            continue
        data.setdefault("items", []).extend(fresh)
        _save_json(path, data)
        added += len(fresh)
    if added:
        reload_terms()
    return added


def update_vocab(items, cap=VOCAB_CAP):
    """每日生词本：汇总当天概念。

    - `cache/vocab/<日期>.json`：**按天独立存档**（幂等，同日多次构建合并累加）
    - `cache/frontier_vocab.json`：滚动总表（跨天累积去重，上限 cap）
    返回今天首次收录的词（供界面/邮件显示"今日新增"）。
    """
    today = datetime.now().strftime("%Y-%m-%d")
    store = _load_json(CACHE_VOCAB, {"items": []})
    known = {x.get("t"): x for x in (store.get("items") or [])}

    day_path = os.path.join(CACHE_VOCAB_DIR, today + ".json")
    day_rec = _load_json(day_path, {"date": today, "items": {}})
    day_items = day_rec.get("items") or {}

    # 先并入"当天已收集过"的词（同一天多次构建/多个批次都能累计进当天存档）
    for name, rec in known.items():
        if rec.get("first_seen") == today or rec.get("last_seen") == today:
            day_items.setdefault(name, {
                "t": name, "d": rec.get("d", ""), "src": rec.get("src", "ai"),
                "domain": rec.get("domain", ""), "item": rec.get("item", ""),
                "url": rec.get("url", ""),
                "first_seen": rec.get("first_seen", today),
                "last_seen": today,
                "hits_today": int(rec.get("hits") or 1),
                "new_today": rec.get("first_seen") == today,
            })

    fresh = []
    for it in items:
        ex = it.get("explain") or {}
        for t in (ex.get("terms") or []) + (ex.get("prereq") or []):
            name = (t.get("t") or "").strip()
            if not name:
                continue
            # 每日存档（记录当天所有出现的词，含历史复现）
            d = day_items.get(name)
            if d:
                d["hits_today"] = int(d.get("hits_today") or 1) + 1
                d["last_seen"] = today
            else:
                day_items[name] = {"t": name, "d": t.get("d", ""),
                                   "src": t.get("src", "ai"),
                                   "domain": it.get("domain", ""),
                                   "item": (it.get("title_zh")
                                            or it.get("title", ""))[:60],
                                   "url": it.get("url", ""),
                                   "first_seen": today, "last_seen": today,
                                   "hits_today": 1,
                                   "new_today": name not in known}
            # 滚动总表
            rec = known.get(name)
            if rec:
                rec["last_seen"] = today
                rec["hits"] = int(rec.get("hits") or 1) + 1
                continue
            rec = {"t": name, "d": t.get("d", ""), "src": t.get("src", "ai"),
                   "domain": it.get("domain", ""), "first_seen": today,
                   "last_seen": today, "hits": 1,
                   "item": (it.get("title_zh") or it.get("title", ""))[:60],
                   "url": it.get("url", "")}
            known[name] = rec
            fresh.append(rec)

    day_rec["items"] = day_items
    day_rec["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    day_rec["new_count"] = sum(1 for x in day_items.values() if x.get("new_today"))
    day_rec["total_count"] = len(day_items)
    _save_json(day_path, day_rec)

    store["items"] = sorted(known.values(),
                            key=lambda x: (x.get("last_seen") or "", x.get("t") or ""),
                            reverse=True)[:cap]
    store["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    _save_json(CACHE_VOCAB, store)
    return [x for x in store["items"] if x.get("first_seen") == today]


def list_vocab_days(limit=90):
    """列出已存档的生词日期：[(日期, 当天词数, 当天新增数)]，按日期倒序。"""
    out = []
    try:
        for fn in sorted(os.listdir(CACHE_VOCAB_DIR), reverse=True):
            if not fn.endswith(".json"):
                continue
            day = fn[:-5]
            rec = _load_json(os.path.join(CACHE_VOCAB_DIR, fn), {})
            items = (rec.get("items") or {})
            out.append((day, rec.get("total_count", len(items)),
                        rec.get("new_count", sum(1 for x in items.values()
                                                 if x.get("new_today")))))
            if len(out) >= limit:
                break
    except OSError:
        pass
    return out


def load_vocab_day(day):
    rec = _load_json(os.path.join(CACHE_VOCAB_DIR, day + ".json"), {"items": {}})
    items = list((rec.get("items") or {}).values())
    items.sort(key=lambda x: (0 if x.get("new_today") else 1, -(x.get("hits_today") or 1)))
    return items


def vocab_by_domain(rows):
    """按领域分组（供界面"按领域"视图）。"""
    groups = {}
    for r in rows:
        groups.setdefault(r.get("domain") or "其他", []).append(r)
    order = ["ai", "tech", "physics", "medicine", "biology", "math", "其他"]
    cn = {"ai": "前沿 AI", "tech": "科技产业", "physics": "物理",
          "medicine": "医学", "biology": "生物", "math": "数学", "其他": "其他"}
    return [(cn.get(k, k), groups[k]) for k in order if k in groups]


def monthly_rollup(month=None):
    """某月生词汇总：天数 / 新增数 / 领域分布 / 高频词。"""
    month = month or datetime.now().strftime("%Y-%m")
    days, rows = [], []
    for day, cnt, new in list_vocab_days(limit=400):
        if day.startswith(month):
            days.append((day, cnt, new))
            rows.extend(load_vocab_day(day))
    by_dom = {}
    for r in rows:
        by_dom.setdefault(r.get("domain") or "其他", set()).add(r.get("t"))
    top = sorted(rows, key=lambda x: -(x.get("hits_today") or 1))[:20]
    return {"month": month, "days": days, "total": len(rows),
            "new": sum(n for _, _, n in days),
            "by_domain": {k: len(v) for k, v in by_dom.items()},
            "top": top}


def export_month_markdown(month=None, out_dir=None):
    """导出月度汇总 Markdown（默认到桌面\\每日播报生词本）。返回文件路径。"""
    data = monthly_rollup(month)
    out_dir = out_dir or os.path.join(os.path.expanduser("~"), "Desktop",
                                      "每日播报生词本")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "生词本_{0}_月度汇总.md".format(data["month"]))
    with open(path, "w", encoding="utf-8") as f:
        f.write("# 生词本 · {0} 月度汇总\n\n".format(data["month"]))
        f.write("> 覆盖 {0} 天，累计 {1} 条词条记录，新增 {2} 个概念\n\n".format(
            len(data["days"]), data["total"], data["new"]))
        f.write("## 领域分布\n\n")
        cn = {"ai": "前沿 AI", "tech": "科技产业", "physics": "物理",
              "medicine": "医学", "biology": "生物", "math": "数学",
              "其他": "其他"}
        for k, v in sorted(data["by_domain"].items(), key=lambda kv: -kv[1]):
            f.write("- {0}：{1} 个\n".format(cn.get(k, k), v))
        f.write("\n## 高频概念 TOP {0}\n\n".format(min(20, len(data["top"]))))
        for r in data["top"]:
            f.write("- **{0}**：{1}（出现 {2} 次）\n".format(
                r.get("t", ""), r.get("d", ""), r.get("hits_today") or 1))
        f.write("\n## 每日明细\n\n")
        for day, cnt, new in data["days"]:
            f.write("### {0}（{1} 条，新增 {2}）\n\n".format(day, cnt, new))
            for r in load_vocab_day(day):
                f.write("- **{0}**：{1}{2}\n".format(
                    r.get("t", ""), r.get("d", ""),
                    " ｜出自：" + r["item"] if r.get("item") else ""))
            f.write("\n")
    return path


def previous_day_vocab(today=None, limit=12):
    """最近一个有存档且早于今天的日期及其"当天新增"生词（供次日复习推送）。"""
    today = today or datetime.now().strftime("%Y-%m-%d")
    days = [d for d, _, _ in list_vocab_days(limit=60) if d < today]
    if not days:
        return "", []
    day = days[0]
    rows = load_vocab_day(day)
    new_rows = [r for r in rows if r.get("new_today")]
    return day, (new_rows or rows)[:limit]


def review_vocab(today=None, same_day=True, limit=8):
    """复习内容：默认取"当天新增"（晚上复习当天所学）；无当天存档则回退到最近有存档的一天。

    same_day=False 时退回"前一天"语义。
    """
    today = today or datetime.now().strftime("%Y-%m-%d")
    if same_day and any(d == today for d, _, _ in list_vocab_days(limit=60)):
        rows = load_vocab_day(today)
        new_rows = [r for r in rows if r.get("new_today")]
        return today, (new_rows or rows)[:limit]
    day, rows = previous_day_vocab(today=today, limit=limit)
    return day, rows


def load_vocab():
    return _load_json(CACHE_VOCAB, {"items": []})


# ---------------------------------------------------------------- 组装
def build_frontier(force=False, days=4, timeout=12, max_age_min=30,
                   translate=True, dump=False):
    cached = _load_json(CACHE_FRONTIER, None)
    if cached and not force:
        try:
            age = time.time() - datetime.strptime(
                cached["updated_at"], "%Y-%m-%d %H:%M:%S").timestamp()
            if age <= max_age_min * 60:
                cached["sites"] = SITES      # 信源入口以代码为准，避免沿用缓存里的旧地址
                return cached
        except Exception:  # noqa: BLE001
            pass

    raw = fetch_all(timeout=timeout, days=days)
    papers = [x for x in raw if x.get("paper") and x["source"] == "arXiv cs.AI"]
    if papers:
        raw = [x for x in raw
               if not (x.get("paper") and x["source"] == "arXiv cs.AI")] + \
              ai_pick_papers(papers)

    # arXiv 论文补 DOI 用于引用查询
    for x in raw:
        if x.get("paper") and not x.get("doi"):
            m = re.search(r"arxiv\.org/abs/([\d.]+)", x.get("url", ""))
            if m:
                x["arxiv_id"] = m.group(1)

    now = time.time()
    for it in raw:
        classify_domain(it)
        score_v2(it, now=now)                    # 先算不含影响力的初分

    hist = load_history()
    cutoff = (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d")
    today_str = datetime.now().strftime("%Y-%m-%d")
    # 只与"更早日期"的历史比对：同一天重复构建时，条目会命中自己刚写入历史的
    # 指纹（sim=1.0）导致新颖性归零、分数持续下滑（实测 71.8 -> 70.0 -> 68.3，
    # 使弹窗阈值永远无法达到）。跨天去重的本意不变。
    hist_hashes = [h.get("h") for h in hist
                   if h.get("h") and cutoff <= (h.get("date") or "") < today_str]
    raw = [x for x in raw if x["score"] >= MIN_SCORE * 0.75]   # 初筛，减少影响力查询量
    attach_influence(raw)                        # 真实引用/热度
    cluster_hashes = []
    for it in sorted(raw, key=lambda x: -(x.get("score_pre") or 0)):
        score_v2(it, now=now, history_hashes=hist_hashes, cluster_hashes=cluster_hashes)
        if it["score"] >= MIN_SCORE:
            cluster_hashes.append(it["simhash"])

    kept = dedupe_events([x for x in raw if x["score"] >= MIN_SCORE])
    picked, constraints = select_with_quota(kept)

    if translate:
        translate_items([x for x in picked if x.get("lang") == "en"],
                        limit=TRANSLATE_LIMIT, timeout=150)

    enriched = 0
    for x in picked:
        if enriched >= ENRICH_LIMIT:
            break
        if len(x.get("desc") or "") < 40 and x.get("url"):
            s = fetch_summary(x["url"], timeout=15)
            if s:
                x["desc"] = s
                x["desc_enriched"] = True
                enriched += 1

    explain_items(picked)          # 读懂它：人话版 + 关键概念 + 先修知识 + 为什么值得关注
    fresh_vocab = update_vocab(picked)   # 每日生词本（跨天累积）
    try:
        added_terms = sync_vocab_to_terms()   # 生词同步进术语词典（供点击跳转）
    except Exception:  # noqa: BLE001
        added_terms = 0

    groups = {d: [x for x in picked if x.get("domain") == d] for d in DOMAINS}
    picked.sort(key=lambda x: -(x.get("score") or 0))

    # 记录历史（供新颖性判定）
    hist.extend({"date": datetime.now().strftime("%Y-%m-%d"),
                 "h": x["simhash"], "t": x.get("title", "")[:80]}
                for x in picked if x.get("simhash"))
    save_history(hist)

    data = {
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "fetched": len(raw), "kept": len(picked),
        "by_source": {}, "fetch_counts": dict(LAST_FETCH_COUNTS),
        "ai_available": ai_available(), "groups": groups, "items": picked,
        "sites": SITES, "constraints": constraints, "quota": QUOTA,
        "constraints": constraints, "quota": QUOTA,
        "vocab_today": fresh_vocab,
        "vocab_total": len((load_vocab().get("items") or [])),
        "terms_added": added_terms,
        "scoring": "v2 六维百分制（时效30/权威20/含金量20/影响力15/新颖性10/领域相关5）",
    }
    for x in raw:
        data["by_source"][x["source"]] = data["by_source"].get(x["source"], 0) + 1
    _save_json(CACHE_FRONTIER, data)
    if dump:
        for d in DOMAINS:
            gs = groups[d]
            print("\n===== {0} ({1}) {2} 条 =====".format(DOMAIN_CN[d], d, len(gs)))
            for x in gs:
                print("  {0:>5}分 {1:<15} {2}h  {3}".format(
                    x.get("score"), x.get("source", "")[:15], x.get("age_hours"),
                    (x.get("title_zh") or x.get("title", ""))[:60]))
                print("        " + (x.get("desc_zh") or x.get("desc", ""))[:100])
                print("        " + (x.get("score_detail") or "")[:120])
        print("\n约束: " + json.dumps(constraints, ensure_ascii=False))
    return data


def load_cached():
    return _load_json(CACHE_FRONTIER, None)


def to_tech_payload(frontier):
    if not frontier:
        return {"items": [], "sites": [], "updated_at": "", "groups": {}}
    out = []
    for x in frontier.get("items", []):
        out.append({
            "source": x.get("source", ""),
            "title": x.get("title_zh") or x.get("title", ""),
            "title_en": x.get("title_en", ""),
            "url": x.get("url", ""),
            "desc": x.get("desc_zh") or _clean(x.get("desc", "")),
            "date": x.get("date", ""),
            "score": x.get("score"), "group": x.get("domain"),
            "domain": x.get("domain"), "dims": x.get("dims"),
            "age_hours": x.get("age_hours"), "also_in": x.get("also_in", []),
            "cites": x.get("cites"), "hn_points": x.get("hn_points"),
            "explain": x.get("explain") or {},
        })
    return {"items": out, "sites": SITES,
            "updated_at": frontier.get("updated_at", ""),
            "constraints": frontier.get("constraints") or {},
            "vocab_today": frontier.get("vocab_today") or [],
            "vocab_total": frontier.get("vocab_total") or 0,
            "groups": {d: [x["url"] for x in v]
                       for d, v in (frontier.get("groups") or {}).items()}}


def check_new_for_push(min_score=PUSH_MIN_SCORE, force=True):
    data = build_frontier(force=force)
    state = _load_json(CACHE_PUSH_STATE, {"seen": [], "last_check": ""})
    seen = set(state.get("seen") or [])
    fresh = []
    for x in data.get("items", []):
        if x["url"] in seen:
            continue
        seen.add(x["url"])
        if (x.get("score") or 0) >= min_score:
            fresh.append(x)
    state["seen"] = list(seen)[-800:]
    state["last_check"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    _save_json(CACHE_PUSH_STATE, state)
    fresh.sort(key=lambda x: -(x.get("score") or 0))
    return fresh


def main():
    import sys
    args = sys.argv[1:]
    if "--check" in args:
        print(json.dumps(check_new_for_push(), ensure_ascii=False, indent=1))
        return 0
    if "--sync-terms" in args:
        n = sync_vocab_to_terms()
        print("术语词典新增 {0} 条（生词 -> 词典）".format(n))
        return 0
    data = build_frontier(force=("--refresh" in args), dump=("--dump" in args))
    if "--json" in args:
        print(json.dumps(data, ensure_ascii=False, indent=1))
        return 0
    print("更新于 {0} | 入选 {1} 条 | 评分: {2}".format(
        data["updated_at"], data["kept"], data.get("scoring")))
    print("抓取层: " + json.dumps(data.get("fetch_counts"), ensure_ascii=False))
    print("约束: " + json.dumps(data.get("constraints"), ensure_ascii=False))
    for d in DOMAINS:
        gs = data["groups"][d]
        print("\n[{0}] {1} 条".format(DOMAIN_CN[d], len(gs)))
        for x in gs:
            print("  {0:>5}分 {1:<15} {2}h  {3}".format(
                x.get("score"), x.get("source", "")[:15], x.get("age_hours"),
                (x.get("title_zh") or x.get("title", ""))[:62]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
