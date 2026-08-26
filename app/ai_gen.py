# -*- coding: utf-8 -*-
"""AI 生成层（C 方案·做法一）：MorningBoard 直接调用 DeepSeek API。

每日一课 / 思辨题 / 表达课 动态生成，内容每天全新；
未配置 API Key 或调用失败时返回 None，由调用方降级到静态知识库。
"""
import json
import os
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
    """从模型输出中提取 JSON（容忍 ```json 围栏、前后杂文、字符串内裸换行）。"""
    if not text:
        return None
    t = text.strip()
    if t.startswith("```"):
        t = t.strip("`").strip()
        if t.startswith("json"):
            t = t[4:].strip()

    def _load(s):
        try:
            return json.loads(s)
        except Exception:  # noqa: BLE001
            # 容错：模型可能在字符串内部输出裸换行/制表符（JSON 不允许），替换为空格
            s2 = re.sub(r"[\r\n\t]+", " ", s)
            try:
                return json.loads(s2)
            except Exception:  # noqa: BLE001
                return None

    r = _load(t)
    if r is not None:
        return r
    a, b = t.find("{"), t.rfind("}")
    if a >= 0 and b > a:
        r = _load(t[a : b + 1])
        if r is not None:
            return r
    a, b = t.find("["), t.rfind("]")
    if a >= 0 and b > a:
        return _load(t[a : b + 1])
    return None


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
        "b 至少 4 段，每段都是完整句子；links 给 3 个可继续深入学习的名词。"
    )
    return _extract_json(_chat(prompt, max_tokens=1500))


def generate_thinking():
    """生成思辨训练题。返回 [{t,s,pro,con,ask,links}]（1-2 题）或 None。"""
    prompt = (
        "你是思辨训练教练。请设计 1 道与中国当下科技/社会热点相关的思辨题，"
        "要求能引发真实争论、双方都有强论据。\n"
        "严格只输出一个 JSON 数组（不要任何其他文字、不要 markdown 围栏）：\n"
        '[{"t":"辩题标题（要抓人）","s":"一句话悬念引入（30字内）",'
        '"pro":["正方观点1（具体有论据）","正方观点2","正方观点3"],'
        '"con":["反方观点1（具体有论据）","反方观点2","反方观点3"],'
        '"ask":["深度追问1","深度追问2","深度追问3"],'
        '"links":["延伸名词1","延伸名词2","延伸名词3"]}]\n'
        "pro/con 各 3 条、每条一句完整论证；ask 3 条追问；避免空话套话。"
    )
    return _extract_json(_chat(prompt, max_tokens=1700))


def generate_expression():
    """生成表达能力课。返回 {t,s,b:[...],links:[...]} 或 None。"""
    prompt = (
        "你是表达力教练。请写一节 5 分钟的表达技巧课，主题取自沟通、演讲、写作或职场表达，"
        "要有可立即模仿的方法。\n"
        "严格只输出一个 JSON 对象（不要任何其他文字、不要 markdown 围栏）：\n"
        '{"t":"技巧名：副标题","s":"一句话说明这个技巧解决什么问题（25字内）",'
        '"b":["第1段：核心方法/步骤（约80字）","第2段：为什么有效（约80字）",'
        '"第3段：一个具体可模仿的示例（约120字）","第4段：今天可立即练习的一句话行动（约40字）"],'
        '"links":["延伸名词1","延伸名词2","延伸名词3"]}\n'
        "b 至少 4 段；示例必须具体（给出场景和原话模板）；links 给 3 个延伸名词。"
    )
    return _extract_json(_chat(prompt, max_tokens=1500))


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
