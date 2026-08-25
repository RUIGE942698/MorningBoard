# -*- coding: utf-8 -*-
"""每日晨报生成：抓取 -> 汇总 -> 写缓存 cache/today.json。"""
import datetime as dt
import json
import os

from . import ai_gen, config, fetch, knowledge

# 每周总结的六个主题（按优先级匹配）
WEEKLY_CATS = [
    (
        "国际局势",
        [
            "俄", "美国", "美方", "俄罗斯", "法国", "英国", "德国", "日本", "韩国",
            "伊朗", "以色列", "巴以", "乌克兰", "欧盟", "欧洲", "联合国", "北约",
            "国际", "全球", "世卫", "中东", "印度", "沙特", "土耳其", "巴西",
            "澳大利亚", "西班牙", "意大利", "波兰", "朝鲜", "叙利亚", "黎巴嫩",
            "巴基斯坦", "阿富汗", "非洲", "拉美", "加拿大", "墨西哥", "阿根廷",
            "埃及", "利比亚", "苏丹", "尼日利亚", "南非", "越南", "泰国", "印尼",
            "马来西亚", "新加坡", "菲律宾", "缅甸", "哈萨克斯坦", "匈牙利", "希腊",
            "阿联酋", "卡塔尔", "伊拉克", "摩洛哥", "突尼斯",
        ],
    ),
    (
        "医学",
        [
            "医疗", "医学", "药品", "疫苗", "健康", "卫生", "疾病", "医院", "医保",
            "疫情", "患者", "手术", "医生", "护士", "诊疗", "药物", "防治", "公共卫生",
        ],
    ),
    (
        "科学",
        [
            "科学", "研究", "发现", "实验", "考古", "天文", "物理", "生物", "化学",
            "地质", "海洋", "气候", "环境", "生态", "化石", "基因", "古生物",
        ],
    ),
    (
        "AI科技",
        [
            "AI", "人工智能", "科技", "芯片", "半导体", "机器人", "大模型", "算力",
            "数字", "互联网", "卫星", "航天", "通信", "软件", "无人机", "量子",
            "智能", "5G", "6G", "云计算", "数据要素",
        ],
    ),
    (
        "金融",
        [
            "经济", "金融", "央行", "财政", "市场", "股市", "基金", "税收", "出口",
            "投资", "消费", "贸易", "货币", "利率", "房地产", "企业", "工业",
            "物价", "增长", "GDP", "产业", "制造业", "就业形势", "经济指标", "宏观",
        ],
    ),
    (
        "民生",
        [
            "民生", "教育", "养老", "住房", "交通", "就业", "工资", "社保", "救助",
            "救灾", "台风", "暴雨", "灾害", "粮食", "菜篮子", "补贴", "防汛",
        ],
    ),
]


def _classify_weekly(title):
    for cat, keys in WEEKLY_CATS:
        if any(k in title for k in keys):
            return cat
    return None


def _load_cache():
    try:
        with open(config.TODAY_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:  # noqa: BLE001
        return None


def _load_raw_fund(code, today):
    """基金净值按天缓存，避免每次开机都重下 400KB 数据。"""
    raw_path = os.path.join(config.RAW_DIR, "fund_{0}.json".format(code))
    if os.path.exists(raw_path):
        try:
            with open(raw_path, encoding="utf-8") as f:
                raw = json.load(f)
            # 只复用成功且带走势数据的缓存；错误/旧格式当天也允许重试
            data = raw.get("data") or {}
            if raw.get("date") == today and not data.get("error") and data.get("trend") is not None:
                return data
        except Exception:  # noqa: BLE001
            pass
    data = fetch.fetch_fund(code)
    config.ensure_dirs()
    try:
        with open(raw_path, "w", encoding="utf-8") as f:
            json.dump({"date": today, "data": data}, f, ensure_ascii=False)
    except Exception:  # noqa: BLE001
        pass
    return data


def _market_tone(pcts):
    """根据涨跌家数给出市场强弱结论。"""
    ups = sum(1 for p in pcts if p > 0)
    downs = sum(1 for p in pcts if p < 0)
    n = len(pcts)
    if n == 0:
        return "数据不足"
    if ups >= max(1, n * 2 // 3):
        return "普涨"
    if downs >= max(1, n * 2 // 3):
        return "普跌"
    return "涨跌互现"


def generate_weekly(today):
    """每周总结（仅周日调用）：本周 7 天联播按六主题归档 + 8 指数周涨跌。"""
    cats = {}
    news_count = 0
    for i in range(7):
        day = today - dt.timedelta(days=i)
        news = fetch.fetch_news(day)
        for it in news.get("items", []):
            news_count += 1
            c = _classify_weekly(it.get("title", ""))
            if c:
                cats.setdefault(c, []).append(it.get("title", ""))

    # 指数周涨跌
    idx_week = []
    for it in config.load_config()["indices"]:
        code = fetch._to_tencent_code(it["secid"])
        row = fetch.fetch_week_kline(code)
        if row:
            row["name"] = it["name"]
            idx_week.append(row)

    ordered = [
        {"cat": c, "items": cats[c][:12]} for c, _ in WEEKLY_CATS if cats.get(c)
    ]

    # 本周科技/商业要闻：量子位 RSS（36氪/机器之心接口有签名保护，暂以官网入口提供）
    qbit = fetch.fetch_qbitai_week(days=7, limit=10)
    return {
        "range": "本周（{0:%m-%d} ~ {1:%m-%d}）".format(today - dt.timedelta(days=6), today),
        "news_count": news_count,
        "indices": idx_week,
        "cats": ordered,
        "media": {
            "qbitai": qbit,
            "tech": fetch.fetch_tech_feeds(limit_each=5),
            "sites": [
                {"name": "InfoQ 中文", "url": "https://www.infoq.cn/"},
                {"name": "IT 之家", "url": "https://www.ithome.com/"},
                {"name": "量子位", "url": "https://www.qbitai.com/"},
                {"name": "掘金", "url": "https://juejin.cn/"},
            ],
        },
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
    }


def generate_today(force=False):
    """生成今日晨报。返回 (payload, is_new)。

    force=False 且当天缓存已存在时直接复用（开机零网络开销）。
    """
    today = dt.date.today()
    today_iso = today.isoformat()
    if not force:
        c = _load_cache()
        if c and c.get("date") == today_iso:
            return c, False

    cfg = config.load_config()
    news = fetch.fetch_news()
    # 科技前沿信源（InfoQ / IT之家 / 量子位 / 掘金 多源聚合，按内容深度优先级）
    news["tech"] = {
        "items": fetch.fetch_tech_feeds(limit_each=4),
        "sites": [
            {"name": "InfoQ 中文", "url": "https://www.infoq.cn/"},
            {"name": "IT 之家", "url": "https://www.ithome.com/"},
            {"name": "量子位", "url": "https://www.qbitai.com/"},
            {"name": "掘金", "url": "https://juejin.cn/"},
        ],
    }
    idx = fetch.fetch_indices(cfg["indices"])
    funds = [_load_raw_fund(code, today_iso) for code in cfg["funds"]]
    gainers = fetch.fetch_top_gainers(5)
    lesson = knowledge.daily_plan(today)

    # AI 动态生成（C 方案·做法一：MorningBoard 直接调 DeepSeek API）
    # 有 key 且成功 -> 用 AI 当日新课；无 key / 失败 -> 保留静态轮换内容
    ai_thinking = None
    ai_expression = None
    if ai_gen.enabled():
        try:
            ai_main = ai_gen.generate_lesson(main_cat=lesson.get("main_cat"))
            if ai_main and isinstance(ai_main, dict) and ai_main.get("t"):
                # AI 返回 t/s/b/links，映射为 GUI 主课渲染结构 title/sub/body
                lesson["main"] = {
                    "cat": lesson.get("main_cat", "AI 新知"),
                    "idx": 0,
                    "total": 1,
                    "title": ai_main.get("t", ""),
                    "sub": ai_main.get("s", ""),
                    "body": ai_main.get("b", []),
                    "links": ai_main.get("links", []),
                }
                lesson["ai_generated"] = True
            ai_thinking = ai_gen.generate_thinking()
            ai_expression = ai_gen.generate_expression()
        except Exception:  # noqa: BLE001
            ai_thinking = None
            ai_expression = None

    # 每周日附加每周总结（联播后生成，覆盖本周 7 天）
    weekly = None
    if today.weekday() == 6:
        try:
            weekly = generate_weekly(today)
        except Exception:  # noqa: BLE001
            weekly = None
        # 每周日自动扩充术语词典（已有领域 +3 条 ×2，并新增 1 个全新领域；失败不影响主流程）
        try:
            import random
            from . import terms_updater
            doms = terms_updater.list_domains()
            picks = random.sample(doms, min(2, len(doms))) if doms else []
            terms_updater.expand_domains(picks, count=3)
            terms_updater.generate_new_domain(count=10)
        except Exception:  # noqa: BLE001
            pass

    pcts = []
    for it in idx["indices"]:
        v = it.get("pct")
        if isinstance(v, (int, float)):
            pcts.append(v)
    tone = _market_tone(pcts)

    payload = {
        "date": today_iso,
        "weekday": "星期" + "一二三四五六日"[today.weekday()],
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "news": news,
        "funds": {
            "indices": idx["indices"],
            "watchlist": funds,
            "top_gainers": gainers["top"],
            "market_tone": tone,
            "index_error": idx["error"],
        },
        "weekly": weekly,
        "lesson": lesson,
        "thinking": {"items": ai_thinking or [], "ai": ai_thinking is not None},
        "expression": ai_expression,
    }
    config.ensure_dirs()
    with open(config.TODAY_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)

    # 历史归档：每天自动保存一份当日课程/思辨/表达（供"历史回顾"查看）
    try:
        hist_dir = os.path.join(config.CACHE_DIR, "history")
        os.makedirs(hist_dir, exist_ok=True)
        _lesson = payload.get("lesson") or {}
        _news = payload.get("news") or {}
        _funds = payload.get("funds") or {}
        archive = {
            "date": today_iso,
            "weekday": payload["weekday"],
            "generated_at": payload["generated_at"],
            "ai_generated": bool(_lesson.get("ai_generated")),
            "lesson_cat": _lesson.get("main_cat"),
            "lesson": _lesson.get("main"),
            "lesson_cards": _lesson.get("cards", []),
            "quote": _lesson.get("quote"),
            "thinking": (payload.get("thinking") or {}).get("items", []),
            "expression": payload.get("expression"),
            "news_headlines": [it.get("title", "") for it in (_news.get("items") or [])[:15]],
            "tech": ((_news.get("tech") or {}).get("items") or [])[:8],
            "indices": [
                {"name": it.get("name", ""), "price": it.get("price"), "pct": it.get("pct")}
                for it in (_funds.get("indices") or [])
            ],
        }
        with open(os.path.join(hist_dir, today_iso + ".json"), "w", encoding="utf-8") as f:
            json.dump(archive, f, ensure_ascii=False, indent=1)
    except Exception:  # noqa: BLE001
        pass

    return payload, True
