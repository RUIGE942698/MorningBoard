# -*- coding: utf-8 -*-
"""每日晨报生成：抓取 -> 汇总 -> 写缓存 cache/today.json。"""
import datetime as dt
import hashlib
import json
import os

from . import ai_gen, config, dedup, fetch, knowledge, webgen


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

# 每周总结的主题（按优先级匹配；「国内」是兜底，务必放最后）
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
        "时政",
        [
            # 领导人/中央机构（注意：本类排在国际局势之后，外国地名优先判国际）
            "习近平", "李强", "赵乐际", "王沪宁", "蔡奇", "丁薛祥", "李希", "韩正",
            "总书记", "总理", "委员长", "国务院", "人大常委会", "全国政协",
            "政治局", "中央", "中央党校", "常委", "全会", "代表大会",
            # 政务动作
            "会见", "出席", "讲话", "主持", "考察", "慰问", "指示", "批示",
            "署名文章", "访问", "出访", "会谈", "峰会", "致辞", "贺信",
            "座谈会", "会议强调", "研究部署", "印发", "意见", "通知",
            # 政策/党建
            "政策", "部署", "规划", "条例", "法治", "党建", "巡视", "学习教育",
            "主题教育", "廉政", "作风", "机构改革", "十五五",
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
        # 科技前沿（用户明确要保留：每周总结里的科技板块）
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
    (
        # 兜底主题：放在最后，让剩下没匹配到的新闻也能进总结（此前近半新闻被丢弃）
        "国内",
        [
            "我国", "全国", "各地", "国内", "地方", "基层", "社区", "群众",
            "省", "市", "县", "乡村", "城市", "区域", "地区",
            "建设", "发展", "推进", "开展", "实施", "加强", "提升", "服务",
            "管理", "物流", "交通", "运输", "文化", "体育", "旅游", "节目",
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


def _remember_current_ai():
    """把当前缓存里已有的 AI 内容标题登记进查重池。

    generate_today 会用新内容覆盖 cache/today.json 和当日归档，
    不先登记的话，同一天内重跑时上一版内容从没进过池子，查重形同虚设
    （实测踩过：20:00 重跑把 19:53 那版主课覆盖后，新主课与它 75% 相似却没被拦下）。
    """
    c = _load_cache()
    if not c:
        return
    try:
        for it in ((c.get("thinking") or {}).get("items") or []):
            if isinstance(it, dict) and it.get("t"):
                dedup.record("thinking", [it["t"]])
        ex = c.get("expression")
        if isinstance(ex, dict) and ex.get("t"):
            dedup.record("expression", [ex["t"]])
        lesson = c.get("lesson") or {}
        main = lesson.get("main")
        if isinstance(main, dict) and main.get("title") and lesson.get("ai_generated"):
            dedup.record("lesson", [main["title"]])
    except Exception:  # noqa: BLE001
        pass


def _ai_dedup_gen(kind, fn, tries=3, retry=2, extra_avoid=None):
    """带查重的 AI 生成：撞题就重出，最多 tries 轮。

    kind: "lesson" / "thinking" / "expression"
    fn:   ai_gen.generate_xxx，需接受 recent_topics 关键字
    返回 (结果, 轮数, 查重备注)；备注为 None 表示一次通过、无撞题。
    """
    try:
        dedup.sync_from_history()
    except Exception:  # noqa: BLE001
        pass
    avoid = dedup.used_titles(kind) + [t for t in (extra_avoid or []) if t]
    # 兜底分用 inf 起步：否则完全相同的标题相似度恰好 1.0，
    # 会被 "score < best_score" 挡掉，导致三轮全撞题时一版都没留下、直接返回 None。
    best, best_who, best_score = None, None, float("inf")
    for i in range(max(1, tries)):
        r, _n = ai_gen.generate_with_retry(lambda: fn(recent_topics=avoid), tries=retry)
        if not r:
            continue
        items = r if isinstance(r, list) else [r]
        titles = [x.get("t", "") for x in items if isinstance(x, dict)]
        conflict, who, score = dedup.batch_conflict(kind, titles)
        if not conflict:
            dedup.record(kind, titles)
            return r, i + 1, None
        # 撞题：把这批标题加进 avoid 再试一次；同时留下最不相似的一版兜底
        avoid = avoid + [t for t in titles if t]
        log_run("dedup {0} 第 {1} 轮撞题「{2}」相似度 {3:.0%}".format(kind, i + 1, who, score))
        if score < best_score:
            best, best_who, best_score = r, who, score
    if best is not None:
        dedup.record(kind, [x.get("t", "") for x in (best if isinstance(best, list) else [best])])
        return best, tries, "与「{0}」相似度 {1:.0%}（已尽力去重）".format(best_who, best_score)
    return None, tries, None


def _thinking_from_web():
    """用网络热点做思辨内容。返回 (items, source, note)。

    source="ai"   ：抓到热点，交给 DeepSeek 加工成完整论证题（最优）
    source="web"  ：AI 不可用，退化成"热点议题卡"（标题 + 追问 + 原文链接）
    失败返回 (None, None, 错误说明)。
    """
    try:
        topics = webgen.fetch_hot_topics(limit=20)
    except Exception as e:  # noqa: BLE001
        return None, None, "热点抓取失败：{0}".format(e)
    if not topics:
        return None, None, "没有抓到任何热点"

    if ai_gen.enabled():
        r, _rounds, _note = _ai_dedup_gen(
            "thinking",
            lambda recent_topics=None: ai_gen.generate_thinking_from_topics(
                topics, recent_topics=recent_topics
            ),
            tries=3,
        )
        if r:
            return r, "web_ai", "基于 {0} 条当日网络热点生成".format(len(topics))

    # 退化：议题卡。网页上抓不到现成的正方/反方，这里不编造论证，
    # 只给真实议题 + 可自查的追问 + 原文链接。
    items = []
    for tp in topics:
        hit, _who, _s = dedup.find_conflict("thinking", tp.get("t", ""))
        if hit:
            continue
        items.append(
            {
                "t": tp.get("t", ""),
                "s": "🔥 今日真实议题 · 来自{0}".format(tp.get("src", "")),
                "pro": [],
                "con": [],
                "ask": [
                    "这件事最有力的支持理由是什么？先自己说 30 秒，再点开原文核对。",
                    "反对者最强的一条论据会是什么？",
                    "要让结论反过来成立，需要满足什么条件？",
                ],
                "links": [],
                "url": tp.get("url", ""),
                "src": tp.get("src", ""),
            }
        )
        if len(items) >= 2:
            break
    if not items:
        return None, None, "抓到的热点都与近期内容重复"
    dedup.record("thinking", [x["t"] for x in items])
    return items, "web", "AI 不可用，已退化成热点议题卡（{0}）".format(items[0].get("src", ""))


def _gen_thinking(prefer="web"):
    """思辨内容的获取链：网络热点 与 AI 命题 两条路，按质量择优并互相兜底。

    prefer="web"：先抓当日热点（0.5s）→ 有 AI 就加工成完整论证题（web_ai）直接用；
                  没加工成（议题卡/抓取失败）再退到 AI 自由命题。
    prefer="ai" ：先 AI 自由命题，失败再走网络热点。

    返回 (items, source, note)：
      web_ai —— 抓热点 + AI 加工，有完整正方反方，且每道题可溯源到当日真实事件（最优）
      ai     —— AI 自由命题
      web    —— AI 不可用，只有热点议题卡（标题 + 追问 + 原文链接）
    """
    web_items = web_src = web_note = None
    ai_items = ai_note = None
    ai_tries = 0

    def try_web():
        nonlocal web_items, web_src, web_note
        try:
            web_items, web_src, web_note = _thinking_from_web()
        except Exception as e:  # noqa: BLE001
            web_items, web_src, web_note = None, None, "网络热点异常：{0}".format(e)

    def try_ai():
        nonlocal ai_items, ai_note, ai_tries
        if not ai_gen.enabled():
            return
        try:
            ai_items, ai_tries, ai_note = _ai_dedup_gen(
                "thinking", ai_gen.generate_thinking, tries=3,
                extra_avoid=_recent_ai_titles("thinking"),
            )
        except Exception:  # noqa: BLE001
            ai_items = None

    if prefer == "web":
        try_web()
        # web_ai 已经是"有完整论证 + 可溯源"的最优解，不必再花一次 AI 调用
        if not (web_items and web_src == "web_ai"):
            try_ai()
    else:
        try_ai()
        if not ai_items:
            try_web()

    if web_items and web_src == "web_ai":
        return web_items, "web_ai", web_note
    if ai_items:
        return ai_items, "ai", ai_note
    if web_items:
        return web_items, "web", web_note
    return None, None, (web_note or ai_note or "网络抓取与 AI 生成都失败")


def _static_thinking_for(day):
    """静态库当日轮换的思辨题（与界面 _thinking_pick 静态路径算法一致）。

    用途：AI / 网络都没产出时，归档里也要有当天实际显示的内容，
    保证「历史回顾」的思辨训练每天不空。
    """
    arr = knowledge.load_thinking()
    if not arr:
        return []
    m = len(arr)
    doy = day.timetuple().tm_yday
    return [dict(arr[(doy - 1 + k) % m]) for k in range(min(2, m))]


def _static_expression_for(day):
    """静态库当日轮换的表达课（与界面 _expression_pick 静态路径算法一致）。"""
    arr = knowledge.load_expression()
    if not arr:
        return None
    return dict(arr[(day.timetuple().tm_yday - 1) % len(arr)])


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


def _week_titles(day):
    """取某天联播的标题列表：优先读本地归档，读不到再联网。

    本地归档（cache/history/<date>.json 的 news_headlines）比重新联网可靠得多——
    央视网接口偶发不可达时，基于本地数据照样能汇总出每周总结。
    """
    p = os.path.join(config.CACHE_DIR, "history", day.isoformat() + ".json")
    try:
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
        titles = [
            t if isinstance(t, str) else ((t or {}).get("title") or "")
            for t in (d.get("news_headlines") or [])
        ]
        titles = [t for t in titles if t]
        if titles:
            return titles
    except Exception:  # noqa: BLE001
        pass
    news = fetch.fetch_news(day)
    return [it.get("title", "") for it in news.get("items", [])]


def generate_weekly(today):
    """每周总结（仅周日调用）：本周 7 天联播按六主题归档 + 8 指数周涨跌。"""
    cats = {}
    news_count = 0
    for i in range(7):
        day = today - dt.timedelta(days=i)
        for title in _week_titles(day):
            news_count += 1
            c = _classify_weekly(title)
            if c:
                cats.setdefault(c, []).append(title)

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

    # 本周科技/商业要闻：量子位 RSS + 科技资讯
    # 兜底：抓取失败（网络抽风）时用上次成功的缓存，科技前沿板块不会消失
    media_cache = os.path.join(config.CACHE_DIR, "raw", "weekly_media.json")
    qbit = fetch.fetch_qbitai_week(days=7, limit=10)
    tech = fetch.fetch_tech_feeds(limit_each=5)
    if qbit or tech:
        try:
            with open(media_cache, "w", encoding="utf-8") as f:
                json.dump({"qbitai": qbit, "tech": tech}, f, ensure_ascii=False)
        except Exception:  # noqa: BLE001
            pass
    else:
        try:
            with open(media_cache, encoding="utf-8") as f:
                old = json.load(f)
            qbit = old.get("qbitai") or []
            tech = old.get("tech") or []
        except Exception:  # noqa: BLE001
            pass
    return {
        "range": "本周（{0:%m-%d} ~ {1:%m-%d}）".format(today - dt.timedelta(days=6), today),
        "news_count": news_count,
        "indices": idx_week,
        "cats": ordered,
        "media": {
            "qbitai": qbit,
            "tech": tech,
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
    thinking_source = None
    ai_status = _ai_status_base(ai_gen.enabled())
    if ai_gen.enabled():
        _remember_current_ai()
        try:
            ai_main, tries, note = _ai_dedup_gen(
                "lesson",
                lambda recent_topics=None: ai_gen.generate_lesson(
                    main_cat=lesson.get("main_cat"), recent_topics=recent_topics
                ),
                tries=2,
                extra_avoid=_recent_lesson_topics(days=7),
            )
            ai_status["lesson"] = bool(ai_main and isinstance(ai_main, dict) and ai_main.get("t"))
            ai_status["lesson_tries"] = tries
            if note:
                ai_status["dedup_lesson"] = note
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
            prefer = (cfg.get("ai") or {}).get("thinking_source") or "web"
            ai_thinking, thinking_source, note = _gen_thinking(prefer=prefer)
            ai_status["thinking"] = bool(ai_thinking)
            if ai_thinking:
                ai_status["thinking_source"] = thinking_source
            if note:
                ai_status["dedup_thinking"] = note
        except Exception as e:  # noqa: BLE001
            ai_status["error"] = (ai_status.get("error") or "") + " thinking: {0}".format(e)
        try:
            ai_expression, tries, note = _ai_dedup_gen(
                "expression", ai_gen.generate_expression, tries=3,
                extra_avoid=_recent_ai_titles("expression"),
            )
            ai_status["expression"] = bool(ai_expression)
            ai_status["expression_tries"] = tries
            if note:
                ai_status["dedup_expression"] = note
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
    # 只有"周日且当天联播已播出"才生成每周总结：周日凌晨/白天（今天联播未播，
    # 新闻会回退到昨天）提前生成的话，总结缺今天，用户看到会困惑"新闻还没出怎么就有总结"。
    if today.weekday() == 6 and (news or {}).get("date") == today_iso:
        try:
            weekly = generate_weekly(today)
        except Exception:  # noqa: BLE001
            weekly = None
        if weekly and weekly.get("news_count", 0) == 0:
            # 一条都没汇总到（接口不可达等）→ 不写空壳，让界面走占位卡片
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
        "thinking": {
            "items": ai_thinking or [],
            "ai": bool(ai_thinking),
            "source": thinking_source or ("static" if not ai_thinking else "ai"),
        },
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
        _th = payload.get("thinking") or {}
        _ex = payload.get("expression")
        th_items = _th.get("items") or []
        # 归档兜底：AI/网络没产出时，把静态库当天实际轮换的内容也归档，
        # 让思辨/表达这两个板块每天都留档（历史回顾不空）
        archive_thinking = th_items or _static_thinking_for(today)
        archive_expression = _ex or _static_expression_for(today)
        th_source = _th.get("source") or ("static" if not th_items else "ai")
        archive = {
            "date": today_iso,
            "weekday": payload["weekday"],
            "generated_at": payload["generated_at"],
            "ai_generated": bool(_lesson.get("ai_generated")),
            "lesson_cat": _lesson.get("main_cat"),
            "lesson": _lesson.get("main"),
            "lesson_cards": _lesson.get("cards", []),
            "quote": _lesson.get("quote"),
            "thinking": archive_thinking,
            "thinking_source": th_source,
            "expression": archive_expression,
            "expression_source": "ai" if _ex else "static",
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
        _th = payload.get("thinking") or {}
        a["thinking"] = _th.get("items", [])
        a["thinking_source"] = _th.get("source") or "ai"
        a["expression"] = payload.get("expression")
        a["expression_source"] = "ai" if payload.get("expression") else "static"
        with open(p, "w", encoding="utf-8") as f:
            json.dump(a, f, ensure_ascii=False, indent=1)
    except Exception:  # noqa: BLE001
        pass


def regenerate_ai_modules(modules=("thinking", "expression"), source="ai"):
    """只重算内容模块（思辨训练 / 表达能力），不重抓新闻和基金。

    source="ai"  ：由 AI 命题（表达模块只支持这一种）
    source="web" ：思辨模块改从网络抓当日热点再做内容
                   —— 有 AI 就基于真实热点加工成完整论证题，
                      没有 AI 则退化成热点议题卡（标题 + 追问 + 原文链接）

    返回 (payload, changed, error)；changed 为成功更新的模块名列表。
    """
    payload = _load_cache()
    if not payload:
        return None, [], "没有今日缓存，请先点「刷新数据」"
    if not ai_gen.enabled():
        return payload, [], "未检测到 DEEPSEEK_API_KEY，AI 模块不可用（当前为静态库内容）"

    # 先把当前显示的内容登记进查重池，保证"换新"一定换出不一样的内容
    _remember_current_ai()
    changed = []
    errs = []
    st = payload.get("ai_status") or _ai_status_base(True)
    st["enabled"] = True

    if "thinking" in modules:
        th, t_src, tries, note = None, source, 0, None
        if source == "web":
            th, t_src, web_note = _thinking_from_web()
            if th:
                note = web_note
                changed.append("思辨训练（网络热点）")
        else:
            th, tries, note = _ai_dedup_gen(
                "thinking", ai_gen.generate_thinking, tries=3,
                extra_avoid=_recent_ai_titles("thinking"),
            )
        st["thinking_tries"] = tries
        if note:
            st["dedup_thinking"] = note
        if th:
            payload["thinking"] = {"items": th, "ai": True, "source": t_src or "ai"}
            st["thinking"] = True
            st["thinking_source"] = t_src or "ai"
            if source != "web":
                changed.append("思辨训练")
        elif source == "web":
            st["thinking"] = False
            errs.append(web_note or "网络热点抓取失败")
        else:
            st["thinking"] = False
            errs.append("思辨题生成失败（已重试 {0} 次）".format(tries))

    if "expression" in modules:
        ex, tries, note = _ai_dedup_gen(
            "expression", ai_gen.generate_expression, tries=3,
            extra_avoid=_recent_ai_titles("expression"),
        )
        st["expression_tries"] = tries
        if note:
            st["dedup_expression"] = note
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
