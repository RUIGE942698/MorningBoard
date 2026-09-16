# -*- coding: utf-8 -*-
"""综合训练桥：把「今日思辨议题」变成「今日即兴说服题」，一次练习喂两个模块。

设计
  思辨侧：给出议题、题型（四类延伸题）、骨架、关键变量、对撞点、条件化结论
  表达侧：给出 2 分钟说服口述计划（钩子 → 两条理由 → 预判反驳 → 条件化收尾），
          并绑定当周表达模块的表达要点与练习动作
  打卡：一次「综合训练」= 表达能力即兴段 + 思辨今日议题 同时记为已完成
用法
  python -m app.practice_bridge --plan     今日综合训练计划
  python -m app.practice_bridge --mark     一键双打卡
  python -m app.practice_bridge --stats    综合训练统计
"""
import argparse
import datetime as dt
import io
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app import config, expression_coach as ecoach, thinking_coach as tcoach  # noqa: E402

STATE_PATH = os.path.join(config.CACHE_DIR, "practice_bridge.json")

# 2 分钟说服口述的时间分配（表达侧）
SPEAK_PLAN = [
    {"at": "0–10 秒", "name": "钩子", "how": "反常识问题 / 具体场景 / 一个数字。绝不用「大家好，我讲三点」开场。"},
    {"at": "10–30 秒", "name": "亮立场", "how": "一句话说清你站哪边、要对方做什么（先给结论，别卖关子）。"},
    {"at": "30–60 秒", "name": "理由一", "how": "机制或证据 + 一句可照说的原话模板；说完停 1 秒。"},
    {"at": "60–85 秒", "name": "理由二", "how": "换一个角度（成本承担者 / 时间尺度 / 受益受损方）。"},
    {"at": "85–105 秒", "name": "预判反驳", "how": "先复述对方最强版本（钢人原则），再化解——不许打稻草人。"},
    {"at": "105–120 秒", "name": "条件化收尾", "how": "「在……条件下我主张……；关键变量是……」，最后给对方一个具体动作。"},
]


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


def load_state():
    st = _read_json(STATE_PATH, {}) or {}
    st.setdefault("done", [])       # [{"date","topic"}]
    return st


def bridge(day=None, offset=0):
    """今日综合训练：思辨议题 + 说服口述计划 + 双模块要点。"""
    day = day or dt.date.today()
    drill = tcoach.today_drill(day, offset)
    topic = drill.get("topic") or {}
    plan = ecoach.today_plan(day)
    key, name, wk, wfocus = ecoach.focus_module(day)
    improv = next((b for b in (plan.get("blocks") or []) if b.get("key") == "improv"), {})

    stance_hint = "任选一方，能自圆其说即可；建议选你**原本不太认同**的那一方，训练更强。"
    return {
        "date": day.isoformat(),
        "weekday": drill.get("weekday", ""),
        "topic": topic.get("t", ""),
        "topic_background": topic.get("s", ""),
        "type_name": topic.get("type_name", ""),
        "type_action": topic.get("type_action") or [],
        "skeleton_name": topic.get("skeleton_name", ""),
        "variables": topic.get("skeleton_variables") or [],
        "clash": topic.get("clash") or "",
        "conditional": topic.get("conditional") or (drill.get("conditional_template") or {}).get("example", ""),
        "pro": (topic.get("pro") or [])[:3],
        "con": (topic.get("con") or [])[:3],
        "stance_hint": stance_hint,
        "speak_plan": SPEAK_PLAN,
        "expression_module": name,
        "expression_week": wk,
        "expression_focus": wfocus,
        "improv_task": improv.get("prompt") or "",
        "thinking_task": "答完四个动作（压缩材料 / 识别类型 / 套框架 / 检查条件化）",
        "checklist": [
            "开头是钩子而不是「大家好」（表达）",
            "先给结论，再给理由（表达·金字塔）",
            "两条理由都有机制或证据（思辨）",
            "预判了对方最强反驳并化解（思辨·钢人原则）",
            "结论是条件化的：在……条件下，关键变量是……（思辨·条件化）",
            "结尾给了对方一个具体动作（说服引领）",
        ],
    }


def mark_both(day=None, offset=0):
    """一键双打卡：表达能力「即兴」段 + 思辨今日议题。"""
    day = day or dt.date.today()
    b = bridge(day, offset)
    ecoach.checkin("improv", day=day, value=True)
    tcoach.mark_done(b.get("topic"), day=day, offset=offset)
    st = load_state()
    if not any(r.get("date") == day.isoformat() and r.get("topic") == b.get("topic")
               for r in st["done"]):
        st["done"].append({"date": day.isoformat(), "topic": b.get("topic")})
    st["done"] = st["done"][-500:]
    _write_json(STATE_PATH, st)
    return {"date": day.isoformat(), "topic": b.get("topic"), "ok": True}


def stats(day=None):
    day = day or dt.date.today()
    st = load_state()
    mon = day - dt.timedelta(days=day.weekday())
    week = [r for r in st["done"]
            if mon.isoformat() <= str(r.get("date")) <= (mon + dt.timedelta(days=6)).isoformat()]
    return {"total": len(st["done"]), "this_week": len(week),
            "last": (st["done"][-1] if st["done"] else {})}


def main():
    ap = argparse.ArgumentParser(description="思辨 × 表达 综合训练")
    ap.add_argument("--plan", action="store_true")
    ap.add_argument("--mark", action="store_true")
    ap.add_argument("--stats", action="store_true")
    a = ap.parse_args()

    if a.mark:
        print(json.dumps(mark_both(), ensure_ascii=False))
        return 0
    if a.stats:
        print(json.dumps(stats(), ensure_ascii=False, indent=1))
        return 0
    b = bridge()
    print("今日综合训练（{0} {1}）".format(b["date"], b["weekday"]))
    print("议题：{0}".format(b["topic"]))
    print("  类型：{0}｜骨架：{1}".format(b["type_name"], b["skeleton_name"]))
    print("  关键变量：{0}".format("、".join(b["variables"])))
    if b.get("clash"):
        print("  对撞点：{0}".format(b["clash"]))
    print("  立场建议：{0}".format(b["stance_hint"]))
    print("\n2 分钟口述计划：")
    for p in b["speak_plan"]:
        print("  [{0}] {1}：{2}".format(p["at"], p["name"], p["how"]))
    print("\n检查清单（做完打钩）：")
    for c in b["checklist"]:
        print("  ☐", c)
    print("\n打完卡：python -m app.practice_bridge --mark")
    return 0


if __name__ == "__main__":
    sys.exit(main())
