# -*- coding: utf-8 -*-
"""思辨教练：把「题型框架 + 条件化答法 + 15 分钟限时训练 + 论据库 + 复盘」变成可执行逻辑。

设计要点
  - 今日训练：抽一道议题（AI 当日题优先，否则静态库按骨架轮换），配好类型、答题动作、骨架变量、15 分钟流程
  - 类型识别：四类延伸题（权衡界定/归因判断/对策/影响）各有固定答题动作；另带「类型识别小测」
  - 条件化：给出「如果前提是…那么…」模板与自检清单，把对错之争变成变量之争
  - 论据库：按议题分类（教育/医疗/住房/科技伦理…）存论据，可添加与查看
  - 复盘：自我反驳 → 对照参考 → 抄进论据库 → 只记两个差距
  - 三连变式：换立场 / 换角色 / 换前提
用法
  python -m app.thinking_coach --plan        今日 15 分钟训练
  python -m app.thinking_coach --quiz        类型识别小测
  python -m app.thinking_coach --stats       训练统计
  python -m app.thinking_coach --evidence    论据库概况
"""
import argparse
import datetime as dt
import io
import json
import os
import random
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app import config  # noqa: E402

SYSTEM_PATH = os.path.join(config.KNOWLEDGE_DIR, "thinking_system.json")
TOPICS_PATH = os.path.join(config.KNOWLEDGE_DIR, "thinking.json")
STATE_PATH = os.path.join(config.CACHE_DIR, "thinking_state.json")
EVIDENCE_PATH = os.path.join(config.CACHE_DIR, "thinking_evidence.json")

TYPE_KEYS = ("balance", "attribution", "solution", "impact")
SKELETON_KEYS = ("resource", "efficiency", "generation", "regulation", "rights",
                 "externality", "information", "incentive", "moral", "culture")

_TYPE_HINTS = (
    ("solution", ("如何", "怎样", "怎么", "防止", "重建", "对策", "办法", "应该做", "治理", "解决")),
    ("impact", ("会不会", "是否会", "加剧", "影响", "后果", "带来", "透支", "长期看", "利空", "利好")),
    ("attribution", ("是理性还是", "是…还是", "还是被", "到底", "归因", "为什么", "该干预", "本质")),
    ("balance", ("该不该", "是否应该", "边界", "划在", "平衡", "保护期", "到什么程度", "多少合适", "红线")),
)

_SKELETON_HINTS = {
    "resource": ("学位", "学区", "名额", "病床", "预算", "分配", "配额", "牌照", "指标分配", "挂号"),
    "efficiency": ("公平", "效率", "差距", "内卷", "竞争", "均等", "贫富"),
    "generation": ("退休", "养老", "后代", "代际", "气候", "子孙", "延迟", "老龄化"),
    "regulation": ("监管", "平台", "政府", "准入", "牌照", "备案", "审核", "一刀切", "干预"),
    "rights": ("隐私", "权利", "自由", "安全", "知情", "言论", "自主权", "肖像"),
    "externality": ("污染", "碳排放", "噪音", "拥堵", "成瘾", "二手烟", "垃圾", "能耗"),
    "information": ("信息", "知情", "医患", "招聘", "二手", "打假", "虚假", "透明度"),
    "incentive": ("考核", "绩效", "补贴", "造假", "骗补", "激励", "运动式", "形式主义"),
    "moral": ("电车", "道德", "伦理", "生命", "牺牲", "良心", "义务", "实验"),
    "culture": ("传统", "文化", "习俗", "集体", "个人", "本土", "全球化", "代沟", "彩礼"),
}


def _read_json(path, default):
    try:
        with io.open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:  # noqa: BLE001
        return default


def _write_json(path, data):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with io.open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        return True
    except Exception:  # noqa: BLE001
        return False


# ------------------------------------------------------------------ 基础数据
def load_system():
    return _read_json(SYSTEM_PATH, {}) or {}


def load_topics():
    items = _read_json(TOPICS_PATH, []) or []
    return items if isinstance(items, list) else (items.get("items") or [])


def load_state():
    st = _read_json(STATE_PATH, {}) or {}
    st.setdefault("done_topics", [])      # [{"topic","date","type","skeleton"}]
    st.setdefault("quiz", {"right": 0, "wrong": 0})
    st.setdefault("reviews", {})
    return st


def save_state(st):
    return _write_json(STATE_PATH, st)


def _type_def(key):
    for t in (load_system().get("question_types") or []):
        if t.get("key") == key:
            return t
    return {}


def _skeleton_def(key):
    for s in (load_system().get("skeletons") or []):
        if s.get("key") == key:
            return s
    return {}


# ------------------------------------------------------------------ 题型/骨架识别
def classify_type(text):
    t = str(text or "")
    for key, words in _TYPE_HINTS:
        for w in words:
            if w in t:
                return key
    return "balance"


def classify_skeleton(text):
    t = str(text or "")
    scores = {}
    for key, words in _SKELETON_HINTS.items():
        scores[key] = sum(1 for w in words if w in t)
    best = max(scores, key=lambda k: scores[k])
    return best if scores[best] > 0 else "regulation"


def type_name(key):
    return _type_def(key).get("name") or key


def skeleton_name(key):
    return _skeleton_def(key).get("name") or key


# ------------------------------------------------------------------ 今日训练编排
def pick_topic(day=None, offset=0):
    """选今日议题：优先未练过的，按日期轮换；可 offset 换一题。"""
    day = day or dt.date.today()
    topics = load_topics()
    if not topics:
        return None
    st = load_state()
    done = {d.get("topic") for d in (st.get("done_topics") or [])}
    fresh = [x for x in topics if x.get("t") not in done] or topics
    idx = (day.timetuple().tm_yday - 1 + offset * 7) % len(fresh)
    return fresh[idx]


def annotate(topic):
    """给议题补上类型、骨架与对应框架。"""
    if not topic:
        return {}
    text = " ".join([str(topic.get("t", "")), str(topic.get("s", "")),
                     " ".join(topic.get("ask") or []) if isinstance(topic.get("ask"), list)
                     else str(topic.get("ask") or "")])
    tkey = topic.get("type") if topic.get("type") in TYPE_KEYS else classify_type(text)
    skey = topic.get("skeleton") if topic.get("skeleton") in SKELETON_KEYS else classify_skeleton(text)
    out = dict(topic)
    out["type"] = tkey
    out["type_name"] = type_name(tkey)
    out["type_action"] = _type_def(tkey).get("action") or []
    out["type_template"] = _type_def(tkey).get("template") or ""
    out["skeleton"] = skey
    out["skeleton_name"] = skeleton_name(skey)
    out["skeleton_variables"] = _skeleton_def(skey).get("variables") or []
    out["skeleton_claim_dir"] = _skeleton_def(skey).get("claim_dir") or ""
    return out


def today_drill(day=None, offset=0):
    """今日 15 分钟训练：议题 + 类型 + 骨架 + 四段流程（含当日具体动作）。"""
    day = day or dt.date.today()
    sysd = load_system()
    routine = sysd.get("routine") or {}
    topic = annotate(pick_topic(day, offset))
    ct = sysd.get("conditional_template") or {}
    blocks = []
    for b in (routine.get("blocks") or []):
        b = dict(b)
        key = b.get("key")
        if key == "compress" and topic:
            pro = topic.get("pro") or []
            con = topic.get("con") or []
            b["prompt"] = ("把正方 {0} 条压成一句核心论点、反方 {1} 条压成一句，"
                           "再写出对撞点（哪条正方正好被哪条反方打）").format(len(pro), len(con))
        elif key == "classify" and topic:
            b["prompt"] = "先别看答案：猜这道题属于哪一类？（正确答案在下方「类型」标签里）"
        elif key == "answer" and topic:
            b["prompt"] = "按「{0}」的动作展开：{1}".format(
                topic.get("type_name"), " → ".join(topic.get("type_action") or []))
        elif key == "check":
            b["prompt"] = "自检：" + "；".join(ct.get("checklist") or [])
        blocks.append(b)
    return {
        "date": day.isoformat(),
        "weekday": "周" + "一二三四五六日"[day.weekday()],
        "cadence": routine.get("cadence", ""),
        "rule": routine.get("rule", ""),
        "topic": topic,
        "conditional_template": ct,
        "blocks": blocks,
        "variants": sysd.get("variants") or [],
        "review_steps": (sysd.get("review") or {}).get("steps") or [],
    }


# ------------------------------------------------------------------ 类型识别小测
def type_quiz(n=1, seed=None):
    """随机抽类型识别小题（返回题目与答案）。"""
    quiz = load_system().get("type_quiz") or []
    if not quiz:
        return []
    rnd = random.Random(seed) if seed is not None else random
    return rnd.sample(quiz, min(n, len(quiz)))


def quiz_record(right=True):
    st = load_state()
    q = st.setdefault("quiz", {"right": 0, "wrong": 0})
    q["right" if right else "wrong"] = int(q.get("right" if right else "wrong") or 0) + 1
    save_state(st)
    return q


# ------------------------------------------------------------------ 训练打卡与统计
def mark_done(topic_title, day=None, offset=0):
    """标记今日议题已练完（记入 done_topics，供统计与去重）。"""
    day = day or dt.date.today()
    topic = annotate(pick_topic(day, offset))
    st = load_state()
    rows = st.setdefault("done_topics", [])
    title = topic_title or topic.get("t")
    if not any(r.get("topic") == title and r.get("date") == day.isoformat() for r in rows):
        rows.append({"topic": title, "date": day.isoformat(),
                     "type": topic.get("type"), "skeleton": topic.get("skeleton")})
    st["done_topics"] = rows[-500:]
    save_state(st)
    return rows


def streak(day=None, st=None):
    st = st or load_state()
    days = sorted({r.get("date") for r in (st.get("done_topics") or []) if r.get("date")})
    if not days:
        return 0
    day = day or dt.date.today()
    have = set(days)
    n = 0
    cur = day
    if cur.isoformat() not in have:
        cur = cur - dt.timedelta(days=1)
    while cur.isoformat() in have:
        n += 1
        cur = cur - dt.timedelta(days=1)
    return n


def stats(day=None):
    day = day or dt.date.today()
    st = load_state()
    rows = st.get("done_topics") or []
    mon = day - dt.timedelta(days=day.weekday())
    week = [r for r in rows
            if mon.isoformat() <= str(r.get("date")) <= (mon + dt.timedelta(days=6)).isoformat()]
    from collections import Counter
    return {
        "total_topics": len(rows),
        "week_topics": len(week),
        "streak": streak(day, st),
        "by_type": dict(Counter(r.get("type") for r in rows)),
        "by_skeleton": dict(Counter(r.get("skeleton") for r in rows)),
        "quiz": st.get("quiz") or {},
        "reviews": len(st.get("reviews") or {}),
        "evidence": {k: len(v) for k, v in evidence().items()},
    }


# ------------------------------------------------------------------ 论据库
def evidence():
    d = _read_json(EVIDENCE_PATH, {}) or {}
    for c in (load_system().get("evidence_bank") or {}).get("categories") or []:
        d.setdefault(c, [])
    return d


def add_evidence(category, text, source=""):
    text = (text or "").strip()
    if not text:
        return False
    d = evidence()
    cat = category if category in d else (list(d.keys())[0] if d else "其他")
    d.setdefault(cat, [])
    if not any((x.get("t") if isinstance(x, dict) else x) == text for x in d[cat]):
        d[cat].append({"t": text, "src": (source or "").strip(),
                       "at": dt.date.today().isoformat()})
    return _write_json(EVIDENCE_PATH, d)


def evidence_text(category=None):
    d = evidence()
    cats = [category] if category else list(d.keys())
    lines = []
    for c in cats:
        rows = d.get(c) or []
        if not rows:
            continue
        lines.append("【{0}】{1} 条".format(c, len(rows)))
        for i, x in enumerate(rows, 1):
            t = x.get("t") if isinstance(x, dict) else str(x)
            src = (x.get("src") if isinstance(x, dict) else "") or ""
            lines.append("  {0}. {1}{2}".format(i, t, ("（来源：" + src + "）") if src else ""))
        lines.append("")
    return "\n".join(lines) or "（论据库还空着：复盘时把「我没想到的论据」抄进来）"


# ------------------------------------------------------------------ 复盘
def save_review(payload, day=None, offset=0):
    """保存一次复盘（自我反驳/对照/抄论据/两个差距）。"""
    day = day or dt.date.today()
    topic = annotate(pick_topic(day, offset))
    st = load_state()
    revs = st.setdefault("reviews", {})
    key = "{0}|{1}".format(day.isoformat(), topic.get("t", "")[:24])
    rec = dict(revs.get(key) or {})
    rec.update({k: (v or "").strip() for k, v in (payload or {}).items() if isinstance(v, str)})
    rec["topic"] = topic.get("t")
    rec["date"] = day.isoformat()
    rec["saved_at"] = dt.datetime.now().isoformat(timespec="seconds")
    revs[key] = rec
    if rec.get("harvest"):
        add_evidence(rec.get("category") or "", rec["harvest"], source=rec.get("source") or "")
    save_state(st)
    return rec


def last_review(day=None):
    st = load_state()
    revs = st.get("reviews") or {}
    if not revs:
        return {}
    rows = sorted(revs.values(), key=lambda r: str(r.get("saved_at") or ""))
    return rows[-1]


# ------------------------------------------------------------------ 变式训练
def variant_prompts(day=None, offset=0):
    """三连变式的具体引导语（结合今日议题）。"""
    topic = annotate(pick_topic(day, offset))
    title = topic.get("t", "")
    sk = topic.get("skeleton_name", "")
    out = []
    for v in (load_system().get("variants") or []):
        out.append({
            "key": v.get("key"), "name": v.get("name"),
            "how": v.get("how"),
            "prompt": "{0}：以「{1}」为题（{2}）——{3}".format(
                v.get("name"), title, sk, v.get("how")),
        })
    return out


def main():
    ap = argparse.ArgumentParser(description="思辨教练")
    ap.add_argument("--plan", action="store_true", help="今日 15 分钟训练")
    ap.add_argument("--quiz", action="store_true", help="类型识别小测")
    ap.add_argument("--stats", action="store_true", help="训练统计")
    ap.add_argument("--evidence", action="store_true", help="论据库概况")
    ap.add_argument("--variant", action="store_true", help="三连变式引导")
    a = ap.parse_args()

    if a.quiz:
        for i, q in enumerate(type_quiz(3), 1):
            print("{0}. {1}\n   答案：{2}｜{3}".format(i, q["q"], type_name(q["a"]), q["why"]))
        return 0
    if a.stats:
        print(json.dumps(stats(), ensure_ascii=False, indent=1))
        return 0
    if a.evidence:
        print(evidence_text())
        return 0
    if a.variant:
        for v in variant_prompts():
            print("·", v["prompt"])
        return 0
    d = today_drill()
    t = d.get("topic") or {}
    print("今日思辨训练（{0} {1}）｜{2}".format(d["date"], d["weekday"], d["cadence"]))
    print("议题：{0}".format(t.get("t")))
    print("  类型：{0}　骨架：{1}".format(t.get("type_name"), t.get("skeleton_name")))
    print("  答题动作：{0}".format(" → ".join(t.get("type_action") or [])))
    print("  关键变量：{0}".format("、".join(t.get("skeleton_variables") or [])))
    print()
    for b in d.get("blocks") or []:
        print("[{0} 分钟] {1}：{2}".format(b.get("minutes"), b.get("name"),
                                            b.get("prompt") or b.get("how", "")[:44]))
    ct = d.get("conditional_template") or {}
    print("\n条件化模板：{0}".format(ct.get("how", "")))
    print("自检：" + "；".join(ct.get("checklist") or []))
    return 0


if __name__ == "__main__":
    sys.exit(main())
