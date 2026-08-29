# -*- coding: utf-8 -*-
"""AI 生成层（C 方案·做法一）：MorningBoard 直接调用 DeepSeek API。

每日一课 / 思辨题 / 表达课 动态生成，内容每天全新；
未配置 API Key 或调用失败时返回 None，由调用方降级到静态知识库。
"""
import json
import os
import re
import time
import urllib.request

# DeepSeek 官方兼容端点（国内可达，无需代理）
API_BASE = "https://api.deepseek.com/chat/completions"
DEFAULT_MODEL = "deepseek-chat"


def api_key():
    """API Key 来源：环境变量 DEEPSEEK_API_KEY（config.json 的 ai.api_key_env 可覆盖）。"""
    env_name = "DEEPSEEK_API_KEY"
    try:
        from . import config
        cfg = config.load_config()
        env_name = (cfg.get("ai") or {}).get("api_key_env") or env_name
    except Exception:  # noqa: BLE001
        pass
    return os.environ.get(env_name, "").strip()


def enabled():
    return bool(api_key())


def _chat(prompt, max_tokens=1400, timeout=60):
    """调用 DeepSeek chat API，返回文本；无 key / 失败返回 None。"""
    key = api_key()
    if not key:
        return None
    try:
        from . import config
        cfg = config.load_config()
        model = (cfg.get("ai") or {}).get("model") or DEFAULT_MODEL
        base_url = (cfg.get("ai") or {}).get("base_url") or API_BASE
        # 容错：配置里可能是根域名（https://api.deepseek.com），补全 /chat/completions
        if not base_url.rstrip("/").endswith("/chat/completions"):
            base_url = base_url.rstrip("/") + "/chat/completions"
    except Exception:  # noqa: BLE001
        model, base_url = DEFAULT_MODEL, API_BASE
    payload = json.dumps(
        {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": 0.8,
            "stream": False,
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        base_url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + key,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            d = json.loads(r.read().decode("utf-8", "ignore"))
        return d["choices"][0]["message"]["content"].strip()
    except Exception:  # noqa: BLE001
        return None


def _extract_json(text):
    """从模型输出中提取 JSON（容忍 ```json 围栏、前后杂文、字符串内裸换行/控制字符）。"""
    if not text:
        return None
    t = text.strip()
    if t.startswith("```"):
        t = t.strip("`").strip()
        if t.startswith("json"):
            t = t[4:].strip()

    def _load(s):
        if not s:
            return None
        try:
            return json.loads(s)
        except Exception:  # noqa: BLE001
            pass
        # 容错1：字符串内部的裸换行/制表符（JSON 不允许）→ 替换为空格
        try:
            return json.loads(re.sub(r"[\r\n\t]+", " ", s))
        except Exception:  # noqa: BLE001
            pass
        # 容错2：去掉字符串外多余的控制字符后再试
        try:
            return json.loads("".join(ch for ch in s if ch >= " " or ch == " "))
        except Exception:  # noqa: BLE001
            return None

    r = _load(t)
    if r is not None:
        return r
    # 找不到整体时，按最外层 {..} / [..] 截取
    a, b = t.find("{"), t.rfind("}")
    if a >= 0 and b > a:
        r = _load(t[a : b + 1])
        if r is not None:
            return r
    a, b = t.find("["), t.rfind("]")
    if a >= 0 and b > a:
        return _load(t[a : b + 1])
    return None


def generate_with_retry(fn, tries=2, delay=1.5):
    """带重试地调用某个 generate_* 函数。

    返回 (结果, 尝试次数)。结果仍可能为 None（AI 失败时由调用方降级）。
    单次网络抖动 / 模型输出畸形不再直接判死整个模块。
    """
    n = max(1, int(tries or 1))
    for i in range(n):
        try:
            r = fn()
        except Exception:  # noqa: BLE001
            r = None
        if r:
            return r, i + 1
        if i < n - 1:
            try:
                time.sleep(delay)
            except Exception:  # noqa: BLE001
                pass
    return None, n


def generate_lesson(main_cat=None, recent_topics=None):
    """生成每日一课主课。返回 {t,s,b:[...],links:[...]} 或 None。

    recent_topics：最近已生成过的主题列表（用于防重复）。
    """
    cat_hint = ("，主题结合「{0}」分类" if main_cat else "，主题从中国科技与社会热点中选取").format(main_cat or "")
    avoid = ""
    if recent_topics:
        avoid = "以下主题最近已经生成过，请务必不要重复（可同类但换全新角度）：{0}\n".format("、".join(recent_topics[:20]))
    prompt = (
        "你是 MorningBoard 每日学习栏目的资深内容编辑。请写一节 5 分钟能读完的「每日一课」"
        + cat_hint
        + "。要求：内容有真实深度、观点新颖、避免陈词滥调，适合普通读者。\n"
        + avoid
        + "严格只输出一个 JSON 对象（不要任何其他文字、不要 markdown 围栏）：\n"
        '{"t":"标题（含冒号副标题更佳）","s":"一句话概括（25字内）",'
        '"b":["第1段：核心概念解释（约80字）","第2段：为什么重要/背景（约80字）",'
        '"第3段：深度展开或独特视角（约100字）","第4段：今日可实践的一句话行动（约40字）"],'
        '"links":["延伸名词1","延伸名词2","延伸名词3"]}\n'
        "b 至少 4 段，每段都是完整句子；links 给 3 个可继续深入学习的名词。\n"
        "重要：t 字段直接写真实标题，禁止出现「标题」「副标题」这类占位词。"
    )
    r = _extract_json(_chat(prompt, max_tokens=1500))
    return _strip_placeholders(r) if isinstance(r, dict) else None


def generate_thinking(recent_topics=None):
    """生成思辨训练题。返回 [{t,s,pro,con,ask,links}]（2 题）或 None。

    recent_topics：最近已出过的辩题（用于防重复）。
    """
    avoid = ""
    if recent_topics:
        avoid = "以下辩题最近已经出过，请务必换全新的议题（可同类但角度要新）：{0}\n".format(
            "、".join(recent_topics[:20])
        )
    prompt = (
        "你是思辨训练教练。请设计 2 道与中国当下科技/社会热点相关的思辨题，"
        "要求能引发真实争论、双方都有强论据，两题领域要不同。\n"
        + avoid
        + "严格只输出一个 JSON 数组，包含 2 个对象（不要任何其他文字、不要 markdown 围栏）：\n"
        '[{"t":"辩题标题（要抓人）","s":"一句话悬念引入（30字内）",'
        '"pro":["正方观点1（具体有论据）","正方观点2","正方观点3"],'
        '"con":["反方观点1（具体有论据）","反方观点2","反方观点3"],'
        '"ask":["深度追问1","深度追问2","深度追问3"],'
        '"links":["延伸名词1","延伸名词2","延伸名词3"]}]\n'
        "pro/con 各 3 条、每条一句完整论证；ask 3 条追问；避免空话套话。"
    )
    r = _extract_json(_chat(prompt, max_tokens=2600))
    if isinstance(r, dict):
        r = [r]
    if not isinstance(r, list):
        return None
    return [_strip_placeholders(x) for x in r if isinstance(x, dict)] or None


def generate_expression(recent_topics=None):
    """生成表达能力课。返回 {t,s,b:[...],links:[...]} 或 None。

    recent_topics：最近已讲过的技巧（用于防重复）。
    """
    avoid = ""
    if recent_topics:
        avoid = "以下技巧最近已经讲过，请务必换全新的技巧：{0}\n".format("、".join(recent_topics[:20]))
    prompt = (
        "你是表达力教练。请写一节 5 分钟的表达技巧课，主题取自沟通、演讲、写作或职场表达，"
        "要有可立即模仿的方法。\n"
        + avoid
        + "严格只输出一个 JSON 对象（不要任何其他文字、不要 markdown 围栏）：\n"
        '{"t":"<真实技巧名>：<副标题>","s":"一句话说明这个技巧解决什么问题（25字内）",'
        '"b":["第1段：核心方法/步骤（约80字）","第2段：为什么有效（约80字）",'
        '"第3段：一个具体可模仿的示例（约120字）","第4段：今天可立即练习的一句话行动（约40字）"],'
        '"links":["延伸名词1","延伸名词2","延伸名词3"]}\n'
        "b 至少 4 段；示例必须具体（给出场景和原话模板）；links 给 3 个延伸名词。\n"
        "重要：t 字段直接写真实内容，禁止出现「技巧名」「副标题」「延伸名词」这类占位词。"
    )
    r = _extract_json(_chat(prompt, max_tokens=1500))
    if isinstance(r, list) and r:
        r = r[0]
    if not isinstance(r, dict):
        return None
    return _strip_placeholders(r)


# 模型偶尔会把提示词里的占位词原样写进标题/正文，这里统一擦掉
_PLACEHOLDER_WORDS = ("技巧名", "副标题", "延伸名词", "标题", "辩题标题", "术语名", "标签")
_PLACEHOLDER_RE = re.compile(
    r"^\s*[<\uff1c\[\(【]?\s*({0})\s*[>\uff1e\]\)】]?\s*[:：\-—]?\s*".format(
        "|".join(_PLACEHOLDER_WORDS)
    )
)


def _clean_field(v):
    """去掉开头的提示词占位词，若整段只剩占位词则返回空串。"""
    if not isinstance(v, str):
        return v
    s = v.strip()
    prev = None
    while prev != s:
        prev = s
        s = _PLACEHOLDER_RE.sub("", s).strip()
    core = re.sub(r"[\d\s<>\[\]()（）【】{}:：\-—·、,，.。]+", "", s)
    if not core or core in _PLACEHOLDER_WORDS:
        return ""
    return s


# 模型有时会把"第1段：""正方观点2："这类编号标签也写进正文
_ITEM_PREFIX_RE = re.compile(
    r"^\s*(?:第[0-9０-９一二三四五六七八九十]+[段条点步项篇]"
    r"|(?:正方|反方|深度|核心|关键)?(?:观点|追问|论据)[0-9０-９一二三四五六七八九十]+"
    r"|(?:正方|反方|深度追问)|追问)\s*[:：、]\s*"
)


def _clean_item(v):
    """逐条清洗数组元素（去占位词 + 去编号标签）。"""
    if not isinstance(v, str):
        return v
    s = _clean_field(v)
    prev = None
    while prev != s:
        prev = s
        s = _ITEM_PREFIX_RE.sub("", s).strip()
    return s


def _strip_placeholders(obj):
    """清掉模型把提示词占位词当正文输出的情况（如 t="技巧名：三明治反馈法"）。"""
    if not isinstance(obj, dict):
        return obj
    out = dict(obj)
    for k in ("t", "s"):
        if k in out:
            out[k] = _clean_field(out.get(k))
    for k in ("b", "pro", "con", "ask"):
        v = out.get(k)
        if isinstance(v, list):
            out[k] = [x for x in (_clean_item(i) for i in v) if isinstance(x, str) and x]
    links = out.get("links")
    if isinstance(links, list):
        out["links"] = [
            x for x in (_clean_field(i) for i in links) if isinstance(x, str) and x
        ]
    return out


def generate_terms(domain, count=3, exclude=None):
    """生成某领域的新术语（术语词典扩充）。返回 [{t,s,b,links}] 或 None。

    exclude：词典中已存在的术语标题（用于防重复，减少生成浪费）。
    """
    avoid = ""
    if exclude:
        avoid = "以下术语已存在于词典，请务必不要重复（可同类但换全新表述）：{0}\n".format("、".join(exclude[:40]))
    header = (
        "你是专业术语编辑。请为领域「{0}」编写 {1} 个该领域重要且实用的专业术语"
        "（普通人值得知道、但词典里可能还没有的），要求真实、准确、有实质内容，避免过于浅显。\n"
        + avoid
        + "严格只输出一个 JSON 数组（不要任何其他文字、不要 markdown 围栏）：\n"
    ).format(domain, count)
    json_tpl = (
        '[{"t":"术语名","s":"一句话定义（25字内）",'
        '"b":["第1段：是什么（约80字）","第2段：为什么重要（约80字）","第3段：常见误区或要点（约60字）"],'
        '"links":["延伸名词1","延伸名词2","延伸名词3"]}]'
    )
    tail = "共 {0} 个对象；b 每段都是完整句子；links 给 3 个延伸名词。".format(count)
    return _extract_json(_chat(header + json_tpl + "\n" + tail, max_tokens=2400))
