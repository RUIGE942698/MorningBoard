# -*- coding: utf-8 -*-
"""每日晨报生成：抓取 -> 汇总 -> 写缓存 cache/today.json。"""
import datetime as dt
import hashlib
import json
import os

from . import ai_gen, config, fetch, knowledge


def _content_hash(lesson):
    """主课内容指纹（标题+正文）。"""
    if not lesson:
        return ""
    body = "".join(lesson.get("body") or [])
    return hashlib.md5(((lesson.get("title") or "") + body).encode("utf-8")).hexdigest()


def _recent_lesson_topics(days=7):
    """最近 N 天归档的主课标题（用于 AI 生成防重复）。"""
    out = []
    try:
        hist_dir = os.path.join(config.CACHE_DIR, "history")
        files = sorted(os.listdir(hist_dir), reverse=True)[:days] if os.path.isdir(hist_dir) else []
        for f in files:
            if not f.endswith(".json"):
                continue
            try:
                with open(os.path.join(hist_dir, f), encoding="utf-8") as fp:
                    data = json.load(fp)
                title = ((data.get("lesson") or {}).get("title") or "").strip()
                if title:
                    out.append(title)
            except Exception:  # noqa: BLE001
                pass
    except OSError:
        pass
    return out

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


def log_run(msg):
    """把每次生成的关键结果追加到 cache/run.log（排障用：AI 是否生效一目了然）。"""
    try:
        config.ensure_dirs()
        p = os.path.join(config.CACHE_DIR, "run.log")
        line = "[{0}] {1}\n".format(dt.datetime.now().isoformat(timespec="seconds"), msg)
        with open(p, "a", encoding="utf-8") as f:
            f.write(line)
        # 只保留最近 200 行，避免无限增长
        with open(p, encoding="utf-8") as f:
            lines = f.readlines()
        if len(lines) > 200:
            with open(p, "w", encoding="utf-8") as f:
                f.writelines(lines[-200:])
    except Exception:  # noqa: BLE001
        pass


def _ai_status_base(enabled):
    """AI 各模块成败记录（写进 payload.ai_status，供界面显示"是否当日 AI 生成"）。"""
    return {
        "enabled": bool(enabled),
        "lesson": False,
        "thinking": False,
        "expression": False,
        "error": None,
    }


def _recent_ai_titles(kind, days=14):
    """最近 N 天归档里某模块已用过的标题（用于 AI 防重复）。

    kind: "thinking"（归档里是数组） / "expression"（归档里是单个对象）
    """
    out = []
    try:
        hist_dir = os.path.join(config.CACHE_DIR, "history")
        files = sorted(
            (f for f in os.listdir(hist_dir) if f.endswith(".json")), reverse=True
        )[:days] if os.path.isdir(hist_dir) else []
        for f in files:
            try:
                with open(os.path.join(hist_dir, f), encoding="utf-8") as fp:
                    data = json.load(fp)
            except Exception:  # noqa: BLE001
                continue
            if kind == "thinking":
                for it in (data.get("thinking") or []):
                    t = ((it or {}).get("t") or "").strip()
                    if t:
                        out.append(t)
            else:
                t = ((data.get("expression") or {}).get("t") or "").strip()
                if t:
                    out.append(t)
    except OSError:
        pass
    return out


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
    ai_status = _ai_status_base(ai_gen.enabled())
    if ai_gen.enabled():
        try:
            ai_main, tries = ai_gen.generate_with_retry(
                lambda: ai_gen.generate_lesson(
                    main_cat=lesson.get("main_cat"),
                    recent_topics=_recent_lesson_topics(days=7),
                ),
                tries=2,
            )
            ai_status["lesson"] = bool(ai_main and isinstance(ai_main, dict) and ai_main.get("t"))
            ai_status["lesson_tries"] = tries
            if ai_status["lesson"]:
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
        except Exception as e:  # noqa: BLE001
            ai_status["error"] = "lesson: {0}".format(e)
        # 思辨 / 表达各自独立重试，互不牵连（以前一次失败会连坐两个模块）
        try:
            ai_thinking, tries = ai_gen.generate_with_retry(
                lambda: ai_gen.generate_thinking(recent_topics=_recent_ai_titles("thinking")),
                tries=3,
            )
            ai_status["thinking"] = bool(ai_thinking)
            ai_status["thinking_tries"] = tries
        except Exception as e:  # noqa: BLE001
            ai_status["error"] = (ai_status.get("error") or "") + " thinking: {0}".format(e)
        try:
            ai_expression, tries = ai_gen.generate_with_retry(
                lambda: ai_gen.generate_expression(recent_topics=_recent_ai_titles("expression")),
                tries=3,
            )
            ai_status["expression"] = bool(ai_expression)
            ai_status["expression_tries"] = tries
        except Exception as e:  # noqa: BLE001
            ai_status["error"] = (ai_status.get("error") or "") + " expression: {0}".format(e)
    elif ai_status.get("error") is None:
        ai_status["error"] = "未配置 DEEPSEEK_API_KEY（当前使用静态知识库轮换内容）"
    log_run(
        "generate_today AI enabled={0} lesson={1} thinking={2} expression={3} err={4}".format(
            ai_status["enabled"],
            ai_status["lesson"],
            ai_status["thinking"],
            ai_status["expression"],
            ai_status["error"] or "-",
        )
    )

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
        "thinking": {"items": ai_thinking or [], "ai": bool(ai_thinking)},
        "expression": ai_expression,
        "ai_status": ai_status,
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
            "dedup": None,
        }
        # 归档去重：与最近 7 天历史对比主课指纹，重复则标注来源（档案照常保存，不丢内容）
        try:
            new_hash = _content_hash(_lesson.get("main"))
            if new_hash:
                recent_files = sorted(
                    (f for f in os.listdir(hist_dir) if f.endswith(".json") and f != today_iso + ".json"),
                    reverse=True,
                )[:7]
                for f in recent_files:
                    try:
                        with open(os.path.join(hist_dir, f), encoding="utf-8") as fp:
                            old = json.load(fp)
                    except Exception:  # noqa: BLE001
                        continue
                    if _content_hash(old.get("lesson")) == new_hash:
                        archive["dedup"] = "内容与 {0} 重复".format(f[:10])
                        break
        except Exception:  # noqa: BLE001
            pass
        with open(os.path.join(hist_dir, today_iso + ".json"), "w", encoding="utf-8") as f:
            json.dump(archive, f, ensure_ascii=False, indent=1)
    except Exception:  # noqa: BLE001
        pass

    return payload, True


def _patch_archive_ai(payload):
    """把重新生成的 AI 内容同步进当日历史归档（保持"历史回顾"与实际一致）。"""
    try:
        hist_dir = os.path.join(config.CACHE_DIR, "history")
        p = os.path.join(
            hist_dir, (payload.get("date") or dt.date.today().isoformat()) + ".json"
        )
        if not os.path.exists(p):
            return
        with open(p, encoding="utf-8") as f:
            a = json.load(f)
        a["thinking"] = (payload.get("thinking") or {}).get("items", [])
        a["expression"] = payload.get("expression")
        with open(p, "w", encoding="utf-8") as f:
            json.dump(a, f, ensure_ascii=False, indent=1)
    except Exception:  # noqa: BLE001
        pass


def regenerate_ai_modules(modules=("thinking", "expression")):
    """只重算 AI 模块（思辨训练 / 表达能力），不重抓新闻和基金。

    用途：当天缓存里这两个模块是空的、或想立刻换一批新题时，界面上一键重生成。
    返回 (payload, changed, error)；changed 为成功更新的模块名列表。
    """
    payload = _load_cache()
    if not payload:
        return None, [], "没有今日缓存，请先点「刷新数据」"
    if not ai_gen.enabled():
        return payload, [], "未检测到 DEEPSEEK_API_KEY，AI 模块不可用（当前为静态库内容）"

    changed = []
    errs = []
    st = payload.get("ai_status") or _ai_status_base(True)
    st["enabled"] = True

    if "thinking" in modules:
        th, tries = ai_gen.generate_with_retry(
            lambda: ai_gen.generate_thinking(recent_topics=_recent_ai_titles("thinking")),
            tries=3,
        )
        st["thinking_tries"] = tries
        if th:
            payload["thinking"] = {"items": th, "ai": True}
            st["thinking"] = True
            changed.append("思辨训练")
        else:
            st["thinking"] = False
            errs.append("思辨题生成失败（已重试 {0} 次）".format(tries))

    if "expression" in modules:
        ex, tries = ai_gen.generate_with_retry(
            lambda: ai_gen.generate_expression(recent_topics=_recent_ai_titles("expression")),
            tries=3,
        )
        st["expression_tries"] = tries
        if ex:
            payload["expression"] = ex
            st["expression"] = True
            changed.append("表达能力")
        else:
            st["expression"] = False
            errs.append("表达课生成失败（已重试 {0} 次）".format(tries))

    payload["ai_status"] = st
    log_run(
        "regenerate_ai_modules {0} -> changed={1} err={2}".format(
            "/".join(modules), changed or "无", "；".join(errs) or "-"
        )
    )
    if changed:
        config.ensure_dirs()
        with open(config.TODAY_PATH, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=1)
        _patch_archive_ai(payload)
    return payload, changed, "；".join(errs)
