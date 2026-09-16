# -*- coding: utf-8 -*-
"""MorningBoard 界面模块：思辨训练（含 15 分钟限时训练 / 类型识别 / 论据库 / 复盘 / 变式）。"""
import datetime as dt
import math
import os
import random
import threading
import tkinter as tk
import tkinter.font as tkfont
import urllib.parse
import webbrowser
from tkinter import simpledialog, ttk
from app import ai_gen, config, fetch, generate, knowledge, thinking_coach as coach
from app.ui.theme import *
from app.ui.widgets import *


class ThinkingTabMixin:
    # ---- thinking ----
    def _thinking_pick(self, n=2):
        # 优先用当日 AI 生成的思辨题（有则用之；点过"换一组"后回到静态库）
        ai = (self.data or {}).get("thinking") or {}
        ai_items = ai.get("items") or []
        if ai_items and not getattr(self, "_thinking_random", False):
            return ai_items[:n]
        arr = knowledge.load_thinking()
        if not arr:
            return []
        m = len(arr)
        if getattr(self, "_thinking_random", False):
            return random.sample(arr, min(n, m))
        doy = dt.date.today().timetuple().tm_yday
        return [arr[(doy - 1 + k) % m] for k in range(min(n, m))]

    def _tool_pick(self):
        arr = knowledge.load_thinking_tools()
        if not arr:
            return None
        if getattr(self, "_thinking_random", False):
            return random.choice(arr)
        return arr[(dt.date.today().timetuple().tm_yday - 1) % len(arr)]

    def _fallacy_pick(self):
        arr = knowledge.load_fallacies()
        if not arr:
            return None
        if getattr(self, "_thinking_random", False):
            return random.choice(arr)
        return arr[(dt.date.today().timetuple().tm_yday - 1) % len(arr)]

    def _thinking_shuffle(self):
        self._thinking_random = True
        self.render_thinking()

    # ---------------------------------------------------------------- 通用弹窗
    def _think_dialog(self, title, lines, width=780, height=560):
        win = tk.Toplevel(self.root)
        win.title(title)
        win.configure(bg=C.BG)
        win.geometry("{0}x{1}".format(width, height))
        win.transient(self.root)
        head = tk.Frame(win, bg=C.CARD)
        head.pack(fill="x")
        tk.Label(head, text=title, font=F_H, bg=C.CARD, fg=section("think")[0]).pack(
            side="left", padx=14, pady=10)
        self._btn(head, "关闭", win.destroy).pack(side="right", padx=10, pady=8)
        txt = tk.Text(win, wrap="word", font=F_SMALL, bg=C.CARD, fg=C.INK,
                      relief="flat", padx=16, pady=12, spacing1=2, spacing3=6)
        sb = ttk.Scrollbar(win, command=txt.yview)
        txt.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        txt.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        for ln in lines:
            txt.insert("end", ln + "\n")
        txt.configure(state="disabled")
        return win

    # ---------------------------------------------------------------- 今日训练
    def _think_drill_card(self, inner):
        d = coach.today_drill()
        t = d.get("topic") or {}
        done = any(r.get("topic") == t.get("t") and r.get("date") == d["date"]
                   for r in (coach.load_state().get("done_topics") or []))
        card = Card(inner, 1000, self._h(320), radius=14)
        card.pack(fill="x", pady=6)
        body = card.body
        head = tk.Frame(body, bg=C.CARD)
        head.pack(fill="x", padx=18, pady=(12, 2))
        self._chip(head, " 🎯 今日思辨训练 · 15 分钟 ", section("think")[0]).pack(side="left")
        self._btn(head, "🎤 用它练口述", self._think_to_express).pack(side="right")
        self._btn(head, "✅ 已练完" if done else "⬜ 标记已练完",
                  self._think_mark_done).pack(side="right", padx=4)
        tk.Label(body, text="议题：{0}".format(t.get("t", "")),
                 font=("Microsoft YaHei UI", 13, "bold"), bg=C.CARD, fg=C.INK,
                 anchor="w", justify="left", wraplength=940).pack(fill="x", padx=18)
        if t.get("s"):
            tk.Label(body, text=t.get("s"), font=F_SMALL, bg=C.CARD, fg=C.SUB,
                     anchor="w", justify="left", wraplength=940).pack(fill="x", padx=18)
        tags = tk.Frame(body, bg=C.CARD)
        tags.pack(fill="x", padx=18, pady=(4, 2))
        tk.Label(tags, text=" 类型：{0} ".format(t.get("type_name", "")), font=F_TINY,
                 bg=C.SOFT, fg=section("terms")[2], padx=6, pady=2).pack(side="left", padx=(0, 6))
        tk.Label(tags, text=" 骨架：{0} ".format(t.get("skeleton_name", "")), font=F_TINY,
                 bg=C.SOFT, fg=section("terms")[2], padx=6, pady=2).pack(side="left")
        if t.get("type_action"):
            tk.Label(body, text="答题动作：" + " → ".join(t["type_action"]), font=F_SMALL,
                     bg=C.CARD, fg=C.INK, anchor="w", justify="left",
                     wraplength=940).pack(fill="x", padx=18, pady=(2, 0))
        if t.get("skeleton_variables"):
            tk.Label(body, text="关键变量：" + "、".join(t["skeleton_variables"]),
                     font=F_TINY, bg=C.CARD, fg=C.SUB, anchor="w", justify="left",
                     wraplength=940).pack(fill="x", padx=18)
        for b in d.get("blocks") or []:
            row = tk.Frame(body, bg=C.CARD)
            row.pack(fill="x", padx=18, pady=(4, 0))
            tk.Label(row, text="[{0} 分钟] {1}".format(b.get("minutes"), b.get("name")),
                     font=F_SMALL, bg=C.CARD, fg=section("think")[0], anchor="w").pack(anchor="w")
            tk.Label(body, text="　" + (b.get("prompt") or b.get("how", "")), font=F_TINY,
                     bg=C.CARD, fg=C.SUB, anchor="w", justify="left",
                     wraplength=920).pack(fill="x", padx=30)
        ct = d.get("conditional_template") or {}
        tk.Label(body, text="🧩 条件化：{0}".format(ct.get("how", "")), font=F_TINY,
                 bg=C.SOFT, fg=section("lesson")[2], anchor="w", justify="left",
                 wraplength=940).pack(fill="x", padx=18, pady=(6, 2))
        self._fit(card, 300)

    def _think_mark_done(self):
        coach.mark_done(None)
        self.render_thinking()

    def _think_to_express(self):
        """跳到「表达能力」页做 2 分钟口述（综合训练卡在那里）。"""
        try:
            self.nb.select(self.tab_express)
            self.render_expression()
        except Exception:  # noqa: BLE001
            pass

    # ---------------------------------------------------------------- 类型识别小测
    def _think_quiz_card(self, inner):
        doy = dt.date.today().timetuple().tm_yday
        q = (coach.type_quiz(1, seed=doy) or [None])[0]
        if not q:
            return
        card = Card(inner, 1000, self._h(170), radius=14)
        card.pack(fill="x", pady=6)
        body = card.body
        self._chip(body, " 🧭 类型识别小测 ", section("think")[0]).pack(
            anchor="w", padx=18, pady=(12, 2))
        tk.Label(body, text=q["q"], font=F_SMALL, bg=C.CARD, fg=C.INK, anchor="w",
                 justify="left", wraplength=940).pack(fill="x", padx=18, pady=(2, 4))
        st = coach.load_state().get("quiz") or {}
        tk.Label(body, text="历史正确 {0} / 错误 {1}　（类型一认出来，框架自动带出来）".format(
            st.get("right", 0), st.get("wrong", 0)),
            font=F_TINY, bg=C.CARD, fg=C.SUB, anchor="w").pack(fill="x", padx=18)

        answer_row = tk.Frame(body, bg=C.CARD)
        answer_row.pack(fill="x", padx=18, pady=6)

        def answer(key):
            right = (key == q["a"])
            coach.quiz_record(right)
            for w in answer_row.winfo_children():
                w.destroy()
            tk.Label(answer_row,
                     text=("{0} 答对了：{1}｜{2}" if right else "{0} 答错了：正确答案是「{1}」｜{2}").format(
                         "✅" if right else "❌", coach.type_name(q["a"]), q["why"]),
                     font=F_SMALL, bg=C.SOFT, fg=(section("lesson")[2] if right else C.UP),
                     anchor="w", justify="left", wraplength=900).pack(fill="x")

        for k in ("balance", "attribution", "solution", "impact"):
            self._btn(answer_row, coach.type_name(k), lambda kk=k: answer(kk)).pack(
                side="left", padx=(0, 6))
        self._fit(card, 150)

    # ---------------------------------------------------------------- 变式训练
    def _think_variant_card(self, inner):
        card = Card(inner, 1000, self._h(150), radius=14)
        card.pack(fill="x", pady=6)
        body = card.body
        head = tk.Frame(body, bg=C.CARD)
        head.pack(fill="x", padx=18, pady=(12, 2))
        self._chip(head, " 🛠 三连变式（进阶） ", section("think")[0]).pack(side="left")
        self._btn(head, "开始变式训练", lambda: self._think_dialog(
            "三连变式", [v["prompt"] for v in coach.variant_prompts()])).pack(side="right")
        self._btn(head, "🤖 AI 写变式", self._think_ai_variants).pack(side="right", padx=4)
        tk.Label(body, text="同一道题练三遍：换立场 → 换角色 → 换前提。前提一改，结论就翻转——这就是条件化训练的核心。",
                 font=F_TINY, bg=C.CARD, fg=C.SUB, anchor="w", justify="left",
                 wraplength=940).pack(fill="x", padx=18)
        for v in coach.variant_prompts():
            tk.Label(body, text="· {0}：{1}".format(v["name"], v["how"]), font=F_SMALL,
                     bg=C.CARD, fg=C.INK, anchor="w", justify="left",
                     wraplength=940).pack(fill="x", padx=18, pady=1)
        self._fit(card, 130)

    # ---------------------------------------------------------------- AI 变式
    def _think_ai_variants(self):
        """用 AI 生成三个变式（换立场/换角色/换前提），后台线程避免卡界面。"""
        t = coach.today_drill().get("topic") or {}
        title = t.get("t") or ""
        if not title:
            return
        win = self._think_dialog("AI 变式训练", ["正在生成三个变式（约 20–40 秒），请稍候…"])

        def work():
            out = []
            for mode in ("stance", "role", "premise"):
                try:
                    r = ai_gen.generate_thinking_variant(
                        title, mode=mode, pro=t.get("pro"), con=t.get("con"))
                except Exception as e:  # noqa: BLE001
                    r = {"mode_name": mode, "t": "生成失败：{0}".format(e)}
                if not r:
                    continue
                out.append("【{0}】{1}".format(r.get("mode_name", mode), r.get("t", "")))
                if r.get("s"):
                    out.append("  说明：" + r["s"])
                for i, p in enumerate(r.get("points") or [], 1):
                    out.append("  论点{0}：{1}".format(i, p))
                if r.get("conditional"):
                    out.append("  条件化：" + r["conditional"])
                if r.get("twist"):
                    out.append("  分歧点：" + r["twist"])
                out.append("")
            text = "\n".join(out) or "生成失败（检查 DEEPSEEK_API_KEY 与网络）"
            self.root.after(0, lambda: self._think_fill_variants(win, title, text))

        threading.Thread(target=work, daemon=True).start()

    def _think_fill_variants(self, win, title, text):
        try:
            win.destroy()
        except Exception:  # noqa: BLE001
            pass
        self._think_dialog("AI 变式 · " + title[:20], text.split("\n"))

    # ---------------------------------------------------------------- 论据库
    def _think_evidence_card(self, inner):
        d = coach.evidence()
        filled = {k: len(v) for k, v in d.items() if v}
        card = Card(inner, 1000, self._h(160), radius=14)
        card.pack(fill="x", pady=6)
        body = card.body
        head = tk.Frame(body, bg=C.CARD)
        head.pack(fill="x", padx=18, pady=(12, 2))
        self._chip(head, " 📚 论据库（按议题分类） ", section("think")[0]).pack(side="left")
        self._btn(head, "➕ 添加论据", self._think_add_evidence).pack(side="right")
        self._btn(head, "查看全部", lambda: self._think_dialog(
            "论据库", coach.evidence_text().split("\n"))).pack(side="right", padx=4)
        tk.Label(body, text="复盘时把「我没想到的论据」抄进来；攒够一类 5 条，这类题就不用从零起步。",
                 font=F_TINY, bg=C.CARD, fg=C.SUB, anchor="w", justify="left",
                 wraplength=940).pack(fill="x", padx=18)
        line = tk.Frame(body, bg=C.CARD)
        line.pack(fill="x", padx=18, pady=4)
        if filled:
            for k, n in sorted(filled.items(), key=lambda x: -x[1]):
                tk.Label(line, text=" {0} {1} ".format(k, n), font=F_TINY, bg=C.SOFT,
                         fg=section("terms")[2], padx=6, pady=2).pack(side="left", padx=3)
        else:
            tk.Label(line, text="（还空着）", font=F_TINY, bg=C.CARD, fg=C.SUB).pack(side="left")
        self._fit(card, 140)

    def _think_add_evidence(self):
        txt = simpledialog.askstring("添加论据", "论据内容（事实/数据/机制）：", parent=self.root)
        if not txt:
            return
        cats = (coach.load_system().get("evidence_bank") or {}).get("categories") or []
        cat = simpledialog.askstring(
            "论据分类", "分类（{0}）".format("/".join(cats)), parent=self.root,
            initialvalue=cats[0] if cats else "")
        coach.add_evidence(cat or "", txt)
        self.render_thinking()

    # ---------------------------------------------------------------- 复盘
    def _think_review_card(self, inner):
        st = coach.stats()
        last = coach.last_review()
        card = Card(inner, 1000, self._h(170), radius=14)
        card.pack(fill="x", pady=6)
        body = card.body
        head = tk.Frame(body, bg=C.CARD)
        head.pack(fill="x", padx=18, pady=(12, 2))
        self._chip(head, " 📅 训练统计与复盘 ", section("think")[0]).pack(side="left")
        self._btn(head, "填写复盘", self._think_review_dialog).pack(side="right")
        self._btn(head, "查看统计", lambda: self._think_dialog(
            "思辨训练统计",
            ["累计议题：{0} 道｜本周：{1} 道｜连续：{2} 天".format(
                st["total_topics"], st["week_topics"], st["streak"]),
             "类型分布：" + ("、".join("{0} {1}".format(coach.type_name(k), v)
                                     for k, v in (st.get("by_type") or {}).items()) or "（暂无）"),
             "骨架分布：" + ("、".join("{0} {1}".format(coach.skeleton_name(k), v)
                                     for k, v in (st.get("by_skeleton") or {}).items()) or "（暂无）"),
             "类型小测：正确 {0} / 错误 {1}".format(
                 (st.get("quiz") or {}).get("right", 0), (st.get("quiz") or {}).get("wrong", 0)),
             "论据库：" + ("、".join("{0} {1}".format(k, v)
                                   for k, v in (st.get("evidence") or {}).items() if v) or "（空）"),
             "",
             "训练节奏：一周 2–3 道，每道严格 15 分钟。少而深，远胜一天刷十道。"])).pack(
            side="right", padx=4)
        tk.Label(body, text="累计 {0} 道　|　本周 {1} 道　|　连续 {2} 天".format(
            st["total_topics"], st["week_topics"], st["streak"]),
            font=F_SMALL, bg=C.CARD, fg=C.INK, anchor="w").pack(fill="x", padx=18)
        if last.get("two_gaps"):
            tk.Label(body, text="🎯 上次复盘记录的差距：{0}".format(last["two_gaps"]),
                     font=F_SMALL, bg=C.SOFT, fg=section("lesson")[2], anchor="w",
                     justify="left", wraplength=940).pack(fill="x", padx=18, pady=(4, 2))
        else:
            tk.Label(body, text="复盘四步：自我反驳 → 对照参考 → 抄论据进库 → 只记两个差距。",
                     font=F_TINY, bg=C.SOFT, fg=section("lesson")[2], anchor="w",
                     justify="left", wraplength=940).pack(fill="x", padx=18, pady=(4, 2))
        self._fit(card, 150)

    def _think_review_dialog(self):
        d = coach.today_drill()
        t = d.get("topic") or {}
        last = coach.last_review()
        win = tk.Toplevel(self.root)
        win.title("思辨复盘")
        win.configure(bg=C.BG)
        win.geometry("800x640")
        win.transient(self.root)
        tk.Label(win, text="📅 复盘：{0}".format(t.get("t", "")), font=F_H, bg=C.BG,
                 fg=section("think")[0], anchor="w", justify="left",
                 wraplength=740).pack(anchor="w", padx=16, pady=(12, 4))
        boxes = {}
        fields = (("self_rebut", "① 自我反驳：写出三个能打自己结论的反例/反论据"),
                  ("compare", "② 对照参考：我没想到的论据 / 我说错的地方"),
                  ("harvest", "③ 抄进论据库：最值得留存的那条论据"),
                  ("two_gaps", "④ 两个差距：是否按类型套框架？结论是否已条件化？"))
        for key, label in fields:
            tk.Label(win, text=label, font=F_SMALL, bg=C.BG, fg=C.INK, anchor="w",
                     justify="left", wraplength=740).pack(anchor="w", padx=16, pady=(6, 0))
            txt = tk.Text(win, height=3, font=F_SMALL, wrap="word", bg=C.CARD, fg=C.INK,
                          relief="flat", padx=8, pady=6)
            txt.insert("1.0", (last.get(key) or "") if key == "two_gaps" else "")
            txt.pack(fill="x", padx=16)
            boxes[key] = txt
        cats = (coach.load_system().get("evidence_bank") or {}).get("categories") or []
        cat_var = tk.StringVar(value=(cats[0] if cats else "其他"))
        row = tk.Frame(win, bg=C.BG)
        row.pack(fill="x", padx=16, pady=(8, 0))
        tk.Label(row, text="论据分类：", font=F_SMALL, bg=C.BG, fg=C.INK).pack(side="left")
        ttk.Combobox(row, textvariable=cat_var, values=cats, width=18,
                     state="readonly").pack(side="left")

        def save():
            payload = {k: v.get("1.0", "end").strip() for k, v in boxes.items()}
            payload["category"] = cat_var.get()
            coach.save_review(payload)
            win.destroy()
            self.render_thinking()

        bar = tk.Frame(win, bg=C.BG)
        bar.pack(fill="x", padx=16, pady=10)
        self._btn(bar, "💾 保存复盘（论据自动入库）", save).pack(side="left")
        self._btn(bar, "取消", win.destroy).pack(side="left", padx=6)

    # ---------------------------------------------------------------- 主渲染
    def render_thinking(self):
        inner = self.scroll_think.inner
        for w in inner.winfo_children():
            w.destroy()

        _tc = section("think")[0]  # 板块强调色随主题（深色下自动提亮）
        head = tk.Frame(inner, bg=C.CARD)
        head.pack(fill="x", pady=(2, 4))
        tk.Label(head, text="🧠 思辨训练", font=F_H, bg=C.CARD, fg=_tc).pack(side="left")
        tk.Label(head, text="15 分钟限时 · 类型框架 · 条件化结论 · 论据库", font=F_SMALL,
                 bg=C.CARD, fg=C.SUB, wraplength=540, justify="left").pack(
            side="left", padx=10, pady=(4, 0)
        )
        th = (self.data or {}).get("thinking") or {}
        ai_ok = bool(th.get("items")) and not getattr(self, "_thinking_random", False)
        self._ai_badge(head, th.get("source") if ai_ok else None)
        self._btn(head, "🎲 换一组", self._thinking_shuffle).pack(side="right")
        self._btn(head, "✨ AI 换新", lambda: self._start_ai_regen(("thinking",))).pack(
            side="right", padx=4
        )
        self._btn(
            head, "🌐 网上找", lambda: self._start_ai_regen(("thinking",), source="web")
        ).pack(side="right", padx=4)
        tk.Label(
            inner,
            text="用法：按「今日思辨训练」的 15 分钟流程走完（压缩材料→识别类型→套框架→检查条件化）→ 打类型小测 → "
                 "复盘时把新论据抄进论据库。题目给的正反观点是弹药，不是答案。",
            font=F_TINY, bg=C.CARD, fg=C.SUB, justify="left", wraplength=1000,
        ).pack(anchor="w", pady=(0, 6))
        self._ai_hint(inner, ai_ok)

        self._think_drill_card(inner)
        self._think_quiz_card(inner)

        # 思辨题：论证对垒
        for i, it in enumerate(self._thinking_pick(2), 1):
            card, body = self._lesson_card(inner, " ⚖️ 思辨题 {0} ".format(i), C.MUTED_BLUE, it)
            _acc, _tint, _ink = section("think")
            ann = coach.annotate(it)
            tk.Label(body, text=" 类型：{0}　骨架：{1} ".format(
                ann.get("type_name", ""), ann.get("skeleton_name", "")),
                font=F_TINY, bg=_tint, fg=_ink, padx=6, pady=2).pack(anchor="w", padx=18, pady=(2, 2))
            for p in it.get("pro", []):
                tk.Label(
                    body, text="✅ 正方：" + p, font=F_SMALL, bg=C.CARD, fg=C.DOWN,
                    anchor="w", justify="left", wraplength=950,
                ).pack(fill="x", padx=18, pady=3)
            for p in it.get("con", []):
                tk.Label(
                    body, text="🔻 反方：" + p, font=F_SMALL, bg=C.CARD, fg=C.UP,
                    anchor="w", justify="left", wraplength=950,
                ).pack(fill="x", padx=18, pady=3)
            if it.get("clash"):
                tk.Label(
                    body, text="💥 对撞点：" + it["clash"], font=F_SMALL, bg=C.CARD,
                    fg=C.MUTED_BLUE, anchor="w", justify="left", wraplength=950,
                ).pack(fill="x", padx=18, pady=(4, 2))
            if it.get("variables"):
                tk.Label(
                    body, text="🎚 关键变量：" + "、".join(it["variables"]), font=F_TINY,
                    bg=C.CARD, fg=C.SUB, anchor="w", justify="left", wraplength=950,
                ).pack(fill="x", padx=18)
            if it.get("conditional"):
                tk.Label(
                    body, text="🧩 条件化结论：" + it["conditional"], font=F_SMALL,
                    bg=_tint, fg=_ink, anchor="w", justify="left", wraplength=950,
                ).pack(fill="x", padx=18, pady=(2, 2))
            for p in it.get("ask", []):
                tk.Label(
                    body, text="❓ " + p, font=F_SMALL, bg=_tint, fg=_ink,
                    anchor="w", justify="left", wraplength=950,
                ).pack(fill="x", padx=18, pady=4)
            self._link_chips(body, it.get("links", []), "延伸思考：", _acc, _tint, _ink)
            # 溯源：标明这道题依据的当日热点，并给出原文链接
            if it.get("ref"):
                _iacc, _itint, _iink = section("info")
                tk.Label(
                    body, text="📎 依据热点：" + it["ref"], font=F_TINY, bg=_itint, fg=_iink,
                    anchor="w", justify="left", wraplength=950,
                ).pack(fill="x", padx=18, pady=(4, 0))
            self._source_link(body, it)
            self._fit(card, 120)

        self._think_variant_card(inner)
        self._think_evidence_card(inner)
        self._think_review_card(inner)

        # 今日思维工具
        tool = self._tool_pick()
        if tool:
            card, body = self._lesson_card(inner, " 🧰 今日思维工具 ", _tc, tool)
            for p in tool.get("b", []):
                tk.Label(
                    body, text=p, font=F_SMALL, bg=C.CARD, fg=C.INK,
                    anchor="w", justify="left", wraplength=950,
                ).pack(fill="x", padx=18, pady=4)
            _acc, _tint, _ink = section("think")
            self._link_chips(body, tool.get("links", []), "延伸工具：", _acc, _tint, _ink)
            self._fit(card, 120)

        # 今日谬误
        fal = self._fallacy_pick()
        if fal:
            _facc, _ftint, _fink = section("fallacy")
            card, body = self._lesson_card(inner, " 🚨 今日谬误雷达 ", _facc, fal)
            for p in fal.get("b", []):
                tk.Label(
                    body, text=p, font=F_SMALL, bg=C.CARD, fg=C.INK,
                    anchor="w", justify="left", wraplength=950,
                ).pack(fill="x", padx=18, pady=4)
            self._link_chips(body, fal.get("links", []), "延伸学习：", _facc, _ftint, _fink)
            self._fit(card, 120)

    # ------------------------------------------------------------ 表达能力
