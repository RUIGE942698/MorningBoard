# -*- coding: utf-8 -*-
"""MorningBoard 界面模块：表达能力（含每日练习系统 / 12 周路线 / 素材库 / 实战转化）。"""
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
from app import (ai_gen, config, expression_coach as coach, fetch, generate, knowledge,
                 practice_bridge as bridge)
from app.ui.theme import *
from app.ui.widgets import *


class ExpressionTabMixin:
    # ---- expression ----

    def _expression_pick(self):
        """优先当日 AI 课；点过「换一课」或 AI 不可用时走静态库（按模块轮换）。"""
        ai = (self.data or {}).get("expression")
        if ai and not getattr(self, "_expression_random", False):
            return ai, "ai"
        it, focus = coach.lesson_of_day(offset=1 if getattr(self, "_expression_random", False) else 0)
        return it, focus

    def _expression_shuffle(self):
        self._expression_random = True
        self.render_expression()

    # ---------------------------------------------------------------- 通用弹窗
    def _expr_dialog(self, title, lines, width=760, height=560):
        win = tk.Toplevel(self.root)
        win.title(title)
        win.configure(bg=C.BG)
        win.geometry("{0}x{1}".format(width, height))
        win.transient(self.root)
        head = tk.Frame(win, bg=C.CARD)
        head.pack(fill="x")
        tk.Label(head, text=title, font=F_H, bg=C.CARD, fg=section("express")[0]).pack(
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

    # ---------------------------------------------------------------- 卡片：四层自评
    def _expr_levels_card(self, inner):
        p = coach.load_practice()
        diag = p.get("diagnosis") or {}
        card = Card(inner, 1000, self._h(150), radius=14)
        card.pack(fill="x", pady=6)
        body = card.body
        self._chip(body, " 🧭 先诊断：你在哪一层 ", section("express")[0]).pack(
            anchor="w", padx=18, pady=(12, 2))
        tk.Label(body, text="表达能力四层金字塔 · 勾选你已经能做到的（存在本地，随时改）",
                 font=F_TINY, bg=C.CARD, fg=C.SUB, anchor="w").pack(fill="x", padx=18)
        rating = coach.get_rating()
        for lv in diag.get("levels") or []:
            row = tk.Frame(body, bg=C.CARD)
            row.pack(fill="x", padx=18, pady=1)
            var = tk.BooleanVar(value=bool(rating.get(str(lv.get("n")))))
            cb = tk.Checkbutton(
                row, text="第 {0} 层 · {1}".format(lv.get("n"), lv.get("name")),
                variable=var, font=F_SMALL, bg=C.CARD, fg=C.INK, anchor="w",
                activebackground=C.CARD, selectcolor=C.SOFT,
                command=lambda n=lv.get("n"), v=var: coach.set_rating(n, v.get()))
            cb.pack(side="left")
            tk.Label(row, text="　{0}".format(lv.get("check", "")), font=F_TINY,
                     bg=C.CARD, fg=C.SUB, anchor="w", justify="left",
                     wraplength=620).pack(side="left", fill="x", expand=True)
        if diag.get("note"):
            tk.Label(body, text="💡 " + diag["note"], font=F_TINY, bg=C.SOFT,
                     fg=section("lesson")[2], anchor="w", justify="left",
                     wraplength=940).pack(fill="x", padx=18, pady=(4, 2))
        self._fit(card, 120)

    # ---------------------------------------------------------------- 卡片：今日练习
    def _expr_practice_card(self, inner):
        plan = coach.today_plan()
        ck = coach.today_checkins()
        done = sum(1 for b in plan["blocks"] if ck.get(b.get("key")))
        st = coach.streak()
        card = Card(inner, 1000, self._h(300), radius=14)
        card.pack(fill="x", pady=6)
        body = card.body
        self._chip(body, " 🎯 今日练习 · {0} 分钟 ".format(plan["total_minutes"]),
                   section("express")[0]).pack(anchor="w", padx=18, pady=(12, 2))
        tk.Label(body,
                 text="第 {0} 周：{1}　|　今日完成 {2}/{3}　|　连续打卡 {4} 天".format(
                     plan["week"], plan["week_focus"], done, len(plan["blocks"]), st),
                 font=F_SMALL, bg=C.CARD, fg=C.INK, anchor="w").pack(fill="x", padx=18)
        if plan.get("rule"):
            tk.Label(body, text="⚠ " + plan["rule"], font=F_TINY, bg=C.SOFT,
                     fg=section("lesson")[2], anchor="w", justify="left",
                     wraplength=940).pack(fill="x", padx=18, pady=(2, 4))

        for b in plan["blocks"]:
            key = b.get("key")
            finished = bool(ck.get(key))
            row = tk.Frame(body, bg=C.CARD)
            row.pack(fill="x", padx=18, pady=2)
            self._btn(row, "✅ 已完成" if finished else "⬜ 打卡",
                      lambda k=key, f=finished: self._expr_checkin(k, not f)).pack(side="left")
            tk.Label(row, text="　{0}（{1} 分钟）".format(b.get("name"), b.get("minutes")),
                     font=F_SMALL, bg=C.CARD,
                     fg=(C.SUB if finished else C.INK), anchor="w").pack(side="left")
            sub = tk.Frame(body, bg=C.CARD)
            sub.pack(fill="x", padx=44)
            tk.Label(sub, text=b.get("prompt") or b.get("how", ""), font=F_SMALL,
                     bg=C.CARD, fg=section("express")[0], anchor="w", justify="left",
                     wraplength=900).pack(fill="x")
            tk.Label(sub, text="做法：{0}".format(b.get("how", "")), font=F_TINY,
                     bg=C.CARD, fg=C.SUB, anchor="w", justify="left",
                     wraplength=900).pack(fill="x", pady=(0, 4))

        if plan.get("week_twist"):
            tk.Label(body, text="📌 本周加练：{0}".format(plan["week_twist"]),
                     font=F_SMALL, bg=C.SOFT, fg=section("lesson")[2], anchor="w",
                     justify="left", wraplength=940).pack(fill="x", padx=18, pady=(6, 2))
        self._fit(card, 260)

    def _expr_checkin(self, block_key, value):
        coach.checkin(block_key, value=value)
        self.render_expression()

    # ---------------------------------------------------------------- 卡片：12 周路线
    def _expr_weeks_card(self, inner):
        wk, winfo = coach.week_info()
        card = Card(inner, 1000, self._h(170), radius=14)
        card.pack(fill="x", pady=6)
        body = card.body
        head = tk.Frame(body, bg=C.CARD)
        head.pack(fill="x", padx=18, pady=(12, 2))
        self._chip(head, " 🗓 12 周进阶路线 ", section("express")[0]).pack(side="left")
        self._btn(head, "查看全部 12 周", self._expr_weeks_dialog).pack(side="right")
        tk.Label(body, text="第 {0} 周 · {1}".format(wk, winfo.get("focus", "")),
                 font=("Microsoft YaHei UI", 13, "bold"), bg=C.CARD, fg=C.INK,
                 anchor="w").pack(fill="x", padx=18)
        for lab, key in (("本周目标", "goal"), ("当日加练", "daily_twist"),
                         ("通过标准", "pass")):
            if winfo.get(key):
                tk.Label(body, text="{0}：{1}".format(lab, winfo[key]), font=F_SMALL,
                         bg=C.CARD, fg=(C.INK if key == "goal" else C.SUB), anchor="w",
                         justify="left", wraplength=940).pack(fill="x", padx=18)
        self._fit(card, 140)

    def _expr_weeks_dialog(self):
        weeks = (coach.load_practice().get("weeks") or [])
        cur, _ = coach.week_info()
        lines = []
        for w in weeks:
            mark = "  ▶ 当前" if int(w.get("week") or 0) == cur else ""
            lines.append("第 {0} 周 · {1}{2}".format(w.get("week"), w.get("focus"), mark))
            lines.append("   目标：{0}".format(w.get("goal", "")))
            lines.append("   加练：{0}".format(w.get("daily_twist", "")))
            lines.append("   通过：{0}".format(w.get("pass", "")))
            lines.append("")
        self._expr_dialog("12 周进阶路线", lines)

    # ---------------------------------------------------------------- 卡片：素材库
    def _expr_materials_card(self, inner):
        mats = coach.materials()
        presets = coach.preset_quotes()
        card = Card(inner, 1000, self._h(200), radius=14)
        card.pack(fill="x", pady=6)
        body = card.body
        self._chip(body, " 🧰 素材库（治「没东西可说」） ", section("express")[0]).pack(
            anchor="w", padx=18, pady=(12, 2))
        tk.Label(body, text="攒够 20 个故事 + 30 个金句，任何场合都不会冷场。",
                 font=F_TINY, bg=C.CARD, fg=C.SUB, anchor="w").pack(fill="x", padx=18)
        kinds = (("quotes", "观点金句"), ("stories", "我的故事（30 秒版）"), ("data", "数据 / 案例"))
        for key, name in kinds:
            row = tk.Frame(body, bg=C.CARD)
            row.pack(fill="x", padx=18, pady=1)
            tk.Label(row, text="{0}（{1}）".format(name, len(mats.get(key) or [])),
                     font=F_SMALL, bg=C.CARD, fg=C.INK, width=22, anchor="w").pack(side="left")
            self._btn(row, "➕ 添加", lambda k=key, n=name: self._expr_add_material(k, n)).pack(side="left")
            self._btn(row, "查看", lambda k=key, n=name: self._expr_show_material(k, n)).pack(
                side="left", padx=4)
        if presets:
            tk.Label(body, text="今日金句：{0}".format(presets[(dt.date.today().timetuple().tm_yday - 1) % len(presets)]),
                     font=F_SMALL, bg=C.SOFT, fg=section("lesson")[2], anchor="w",
                     justify="left", wraplength=940).pack(fill="x", padx=18, pady=(6, 2))
        self._fit(card, 170)

    def _expr_add_material(self, kind, name):
        txt = simpledialog.askstring("添加素材 · " + name, "内容：", parent=self.root)
        if txt:
            coach.add_material(kind, txt)
            self.render_expression()

    def _expr_show_material(self, kind, name):
        d = coach.materials()
        rows = list(d.get(kind) or [])
        if kind == "quotes":
            rows = list(coach.preset_quotes()) + rows
        lines = ["【{0}】共 {1} 条".format(name, len(rows)), ""]
        for i, x in enumerate(rows, 1):
            lines.append("{0}. {1}".format(i, x))
        self._expr_dialog("素材库 · " + name, lines)

    # ---------------------------------------------------------------- 卡片：实战转化
    def _expr_realscene_card(self, inner):
        p = coach.load_practice()
        card = Card(inner, 1000, self._h(240), radius=14)
        card.pack(fill="x", pady=6)
        body = card.body
        self._chip(body, " 🚀 实战转化（治「学完用不出来」） ", section("express")[0]).pack(
            anchor="w", padx=18, pady=(12, 2))
        for m in (p.get("mechanisms") or []):
            row = tk.Frame(body, bg=C.CARD)
            row.pack(fill="x", padx=18, pady=1)
            self._btn(row, "看做法", lambda mm=m: self._expr_dialog(
                mm.get("name", ""), [mm.get("how", "")] + [""] + list(mm.get("body") or []))).pack(side="left")
            tk.Label(row, text="　{0}".format(m.get("name", "")), font=F_SMALL,
                     bg=C.CARD, fg=C.INK, anchor="w").pack(side="left")
        tk.Label(body, text="低风险真实场景清单（勾选你今天真的做了）：", font=F_SMALL,
                 bg=C.CARD, fg=C.SUB, anchor="w").pack(fill="x", padx=18, pady=(6, 0))
        st = coach.load_state()
        for s in coach.scenarios():
            var = tk.BooleanVar(value=s["done"])
            tk.Checkbutton(
                body, text=s["text"], variable=var, font=F_SMALL, bg=C.CARD, fg=C.INK,
                anchor="w", activebackground=C.CARD, selectcolor=C.SOFT,
                command=lambda k=s["key"]: coach.toggle_scenario(k)
            ).pack(fill="x", padx=22)
        self._fit(card, 210)

    def _expr_modules_card(self, inner):
        mods, total = coach.module_progress()
        card = Card(inner, 1000, self._h(130), radius=14)
        card.pack(fill="x", pady=6)
        body = card.body
        self._chip(body, " 📚 知识库模块进度 ", section("express")[0]).pack(
            anchor="w", padx=18, pady=(12, 2))
        tk.Label(body, text="表达知识库共 {0} 条，按 6 大模块轮换推送（每周主攻一个模块）".format(total),
                 font=F_TINY, bg=C.CARD, fg=C.SUB, anchor="w").pack(fill="x", padx=18)
        line = tk.Frame(body, bg=C.CARD)
        line.pack(fill="x", padx=18, pady=4)
        for m in mods:
            tk.Label(line, text=" {0} {1} ".format(m["name"], m["count"]), font=F_TINY,
                     bg=C.SOFT, fg=section("terms")[2], padx=6, pady=2).pack(side="left", padx=3)
        self._fit(card, 110)

    # ---------------------------------------------------------------- 卡片：综合训练（思辨 × 表达）
    def _expr_bridge_card(self, inner):
        b = bridge.bridge()
        st = bridge.stats()
        card = Card(inner, 1000, self._h(300), radius=14)
        card.pack(fill="x", pady=6)
        body = card.body
        head = tk.Frame(body, bg=C.CARD)
        head.pack(fill="x", padx=18, pady=(12, 2))
        self._chip(head, " 🔗 综合训练：思辨 × 表达 ", section("express")[0]).pack(side="left")
        self._btn(head, "🎤 AI 写说服脚本", lambda: self._expr_ai_script(b)).pack(side="right")
        self._btn(head, "✅ 一键双打卡", self._expr_bridge_mark).pack(side="right", padx=4)
        tk.Label(body, text="用今日思辨议题当你的即兴说服题——一次练完，两个模块同时记进度。",
                 font=F_TINY, bg=C.CARD, fg=C.SUB, anchor="w", justify="left",
                 wraplength=940).pack(fill="x", padx=18)
        tk.Label(body, text="议题：{0}".format(b.get("topic", "")),
                 font=("Microsoft YaHei UI", 13, "bold"), bg=C.CARD, fg=C.INK,
                 anchor="w", justify="left", wraplength=940).pack(fill="x", padx=18)
        tk.Label(body, text="类型：{0}　骨架：{1}　关键变量：{2}".format(
            b.get("type_name", ""), b.get("skeleton_name", ""),
            "、".join(b.get("variables") or []) or "—"),
            font=F_TINY, bg=C.CARD, fg=C.SUB, anchor="w", justify="left",
            wraplength=940).pack(fill="x", padx=18)
        if b.get("clash"):
            tk.Label(body, text="💥 对撞点：" + b["clash"], font=F_SMALL, bg=C.CARD,
                     fg=section("think")[0], anchor="w", justify="left",
                     wraplength=940).pack(fill="x", padx=18, pady=(2, 0))
        tk.Label(body, text="2 分钟口述计划（拍成一段视频）：", font=F_SMALL, bg=C.CARD,
                 fg=C.INK, anchor="w").pack(fill="x", padx=18, pady=(4, 0))
        for p in b.get("speak_plan") or []:
            tk.Label(body, text="　[{0}] {1}：{2}".format(p["at"], p["name"], p["how"]),
                     font=F_TINY, bg=C.CARD, fg=C.SUB, anchor="w", justify="left",
                     wraplength=920).pack(fill="x", padx=26)
        tk.Label(body, text="✅ 已完成 {0} 次（本周 {1} 次）".format(
            st.get("total", 0), st.get("this_week", 0)),
            font=F_TINY, bg=C.SOFT, fg=section("lesson")[2], anchor="w").pack(
            fill="x", padx=18, pady=(6, 2))
        self._fit(card, 280)

    def _expr_bridge_mark(self):
        bridge.mark_both()
        self.render_expression()

    def _expr_ai_script(self, b):
        win = self._expr_dialog("AI 说服脚本", ["正在生成 2 分钟说服脚本（约 20–40 秒）…"])

        def work():
            try:
                r = ai_gen.generate_speech_script(
                    b.get("topic"), points=b.get("pro"), clash=b.get("clash"),
                    conditional=b.get("conditional"))
            except Exception as e:  # noqa: BLE001
                r = {"stance": "生成失败：{0}".format(e)}
            lines = []
            if r:
                lines.append("立场：" + str(r.get("stance", "")))
                lines.append("")
                lines.append("【钩子 0–10 秒】" + str(r.get("hook", "")))
                for i, p in enumerate(r.get("body") or [], 1):
                    lines.append("")
                    lines.append("【理由 {0}】{1}".format(i, p))
                lines.append("")
                lines.append("【预判反驳】" + str(r.get("rebuttal", "")))
                lines.append("")
                lines.append("【条件化收尾 + 行动号召】" + str(r.get("close", "")))
                lines.append("")
                lines.append("【现场表达要点】")
                for d in (r.get("delivery") or []):
                    lines.append("  · " + str(d))
            else:
                lines.append("生成失败（检查 DEEPSEEK_API_KEY 与网络）")
            self.root.after(0, lambda: (win.destroy(),
                                        self._expr_dialog("AI 说服脚本 · " + b.get("topic", "")[:18],
                                                          lines)))

        threading.Thread(target=work, daemon=True).start()

    # ---------------------------------------------------------------- 卡片：本周复盘
    def _expr_review_card(self, inner):
        st = coach.weekly_stats()
        ref = coach.get_reflection()
        card = Card(inner, 1000, self._h(180), radius=14)
        card.pack(fill="x", pady=6)
        body = card.body
        head = tk.Frame(body, bg=C.CARD)
        head.pack(fill="x", padx=18, pady=(12, 2))
        self._chip(head, " 📅 本周复盘 ", section("express")[0]).pack(side="left")
        self._btn(head, "填写复盘三问", self._expr_review_dialog).pack(side="right")
        self._btn(head, "查看/复制复盘文本", self._expr_review_text).pack(side="right", padx=4)
        tk.Label(body,
                 text="本周打卡 {0}/{1} 天　|　最近 7 天 {2}/7 天　|　连续 {3} 天"
                      "（历史最长 {4} 天）".format(
                          st["practiced_days"], st["days_in_week"], st["last7_days"],
                          st["streak"], st["longest_streak"]),
                 font=F_SMALL, bg=C.CARD, fg=C.INK, anchor="w").pack(fill="x", padx=18)
        tk.Label(body,
                 text="四段完成：{0}　|　素材 {1} 条（本周 +{2}）　|　实战场景 {3} 条".format(
                     "、".join("{0} {1} 次".format(
                         {"read": "朗读", "improv": "即兴", "review": "复盘", "learn": "课+费曼"}.get(k, k), v)
                         for k, v in (st.get("per_block") or {}).items()),
                     st["materials_total"], st["materials_week"], st["scenarios_total"]),
                 font=F_TINY, bg=C.CARD, fg=C.SUB, anchor="w", justify="left",
                 wraplength=940).pack(fill="x", padx=18)
        if ref.get("q3"):
            tk.Label(body, text="🎯 你上周定的一件改动：{0}".format(ref["q3"]),
                     font=F_SMALL, bg=C.SOFT, fg=section("lesson")[2], anchor="w",
                     justify="left", wraplength=940).pack(fill="x", padx=18, pady=(4, 2))
        else:
            tk.Label(body, text="还没写过复盘。先做完今天的练习，晚上花 3 分钟回答三个问题。",
                     font=F_TINY, bg=C.SOFT, fg=section("lesson")[2], anchor="w",
                     justify="left", wraplength=940).pack(fill="x", padx=18, pady=(4, 2))
        self._fit(card, 150)

    def _expr_review_dialog(self):
        ref = coach.get_reflection()
        win = tk.Toplevel(self.root)
        win.title("本周复盘 · 三个问题")
        win.configure(bg=C.BG)
        win.geometry("760x520")
        win.transient(self.root)
        tk.Label(win, text="📅 本周复盘（每周填一次，3 分钟）", font=F_H, bg=C.BG,
                 fg=section("express")[0]).pack(anchor="w", padx=16, pady=(12, 4))
        boxes = {}
        for key, q in coach.REVIEW_QUESTIONS:
            tk.Label(win, text=q, font=F_SMALL, bg=C.BG, fg=C.INK, anchor="w",
                     justify="left", wraplength=700).pack(anchor="w", padx=16, pady=(6, 0))
            t = tk.Text(win, height=3, font=F_SMALL, wrap="word", bg=C.CARD,
                        fg=C.INK, relief="flat", padx=8, pady=6)
            t.insert("1.0", ref.get(key) or "")
            t.pack(fill="x", padx=16)
            boxes[key] = t

        def save():
            coach.save_reflection({k: v.get("1.0", "end").strip() for k, v in boxes.items()})
            win.destroy()
            self.render_expression()

        bar = tk.Frame(win, bg=C.BG)
        bar.pack(fill="x", padx=16, pady=10)
        self._btn(bar, "💾 保存复盘", save).pack(side="left")
        self._btn(bar, "取消", win.destroy).pack(side="left", padx=6)

    def _expr_review_text(self):
        txt = coach.review_text()
        win = self._expr_dialog("本周复盘文本", txt.split("\n"))

        def copy():
            self.root.clipboard_clear()
            self.root.clipboard_append(txt)
            self.root.update()

        self._btn(win, "📋 复制全文", copy).pack(side="right", padx=10, pady=(0, 10))

    # ---------------------------------------------------------------- 主渲染
    def render_expression(self):
        inner = self.scroll_express.inner
        for w in inner.winfo_children():
            w.destroy()

        head = tk.Frame(inner, bg=C.CARD)
        head.pack(fill="x", pady=(2, 4))
        tk.Label(head, text="📣 表达能力", font=F_H, bg=C.CARD, fg=section('express')[0]).pack(side="left")
        tk.Label(head, text="每日 20 分钟练习 · 12 周路线 · 说服与引领 · 学完必须用出来",
                 font=F_SMALL, bg=C.CARD, fg=C.SUB, wraplength=540, justify="left").pack(
            side="left", padx=10, pady=(4, 0)
        )
        ai_ok = bool((self.data or {}).get("expression")) and not getattr(
            self, "_expression_random", False
        )
        self._ai_badge(head, ai_ok)
        self._btn(head, "🎲 换一课", self._expression_shuffle).pack(side="right")
        self._btn(head, "✨ AI 换新", lambda: self._start_ai_regen(("expression",))).pack(
            side="right", padx=4
        )
        tk.Label(
            inner, text="顺序建议：先看今日练习 → 打卡四段 → 再看今日课 → 最后用费曼法 60 秒复述一遍。",
            font=F_TINY, bg=C.CARD, fg=C.SUB,
        ).pack(anchor="w", pady=(0, 6))
        self._ai_hint(inner, ai_ok)

        self._expr_levels_card(inner)
        self._expr_practice_card(inner)
        self._expr_bridge_card(inner)
        self._expr_review_card(inner)

        # 今日课
        it, focus = self._expression_pick()
        if it:
            mods = {m["key"]: m["name"] for m in (coach.load_practice().get("modules") or [])
                    if m.get("key")}
            mod_key = it.get("module") or focus
            tag = " 📣 今日表达课 · {0} ".format(mods.get(mod_key, "表达"))
            card, body = self._lesson_card(inner, tag, section('express')[0], it)
            for p in it.get("b", []):
                if p.startswith("今天的启发"):
                    tk.Label(
                        body, text="💡 " + p, font=F_SMALL, bg=C.SOFT, fg=section("lesson")[2],
                        anchor="w", justify="left", wraplength=950,
                    ).pack(fill="x", padx=18, pady=3)
                else:
                    tk.Label(
                        body, text=p, font=F_SMALL, bg=C.CARD, fg=C.INK,
                        anchor="w", justify="left", wraplength=950,
                    ).pack(fill="x", padx=18, pady=4)
            action = it.get("drill")
            if not action:
                for b in (coach.today_plan().get("blocks") or []):
                    if b.get("key") == "improv":
                        action = b.get("prompt")
                        break
            if action:
                tk.Label(
                    body, text="🎯 今天就用出去：{0}".format(action), font=F_SMALL,
                    bg=C.SOFT, fg=section("lesson")[2], anchor="w", justify="left",
                    wraplength=950,
                ).pack(fill="x", padx=18, pady=(4, 2))
            self._link_chips(body, it.get("links", []), "延伸学习：", section('express')[0],
                             section("terms")[1], section("terms")[2])
            self._fit(card, 140)

        self._expr_materials_card(inner)
        self._expr_realscene_card(inner)
        self._expr_weeks_card(inner)
        self._expr_modules_card(inner)

    # ------------------------------------------------------------ 每周总结
