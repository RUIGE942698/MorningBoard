# -*- coding: utf-8 -*-
"""MorningBoard 界面模块：expression。"""
import datetime as dt
import math
import os
import random
import threading
import tkinter as tk
import tkinter.font as tkfont
import urllib.parse
import webbrowser
from tkinter import ttk
from app import config, fetch, generate, knowledge
from app.ui.theme import *
from app.ui.widgets import *
class ExpressionTabMixin:
    # ---- expression ----
    EXPR_COLOR = "#2F6B5A"

    def _expression_pick(self):
        # 优先用当日 AI 生成的表达课（有则用之；点过"换一课"后回到静态库）
        ai = (self.data or {}).get("expression")
        if ai and not getattr(self, "_expression_random", False):
            return ai
        arr = knowledge.load_expression()
        if not arr:
            return None
        if getattr(self, "_expression_random", False):
            return random.choice(arr)
        return arr[(dt.date.today().timetuple().tm_yday - 1) % len(arr)]

    def _expression_shuffle(self):
        self._expression_random = True
        self.render_expression()

    def render_expression(self):
        inner = self.scroll_express.inner
        for w in inner.winfo_children():
            w.destroy()

        head = tk.Frame(inner, bg=CARD)
        head.pack(fill="x", pady=(2, 4))
        tk.Label(head, text="📣 表达能力", font=F_H, bg=CARD, fg=self.EXPR_COLOR).pack(side="left")
        tk.Label(head, text="结构化表达 · 即兴发言 · 演讲辩论 · 每天一课", font=F_SMALL, bg=CARD, fg=SUB).pack(
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
            inner, text="每天一课，学完立即用今天的一个场景练一遍——表达是练出来的，不是看会的。",
            font=F_TINY, bg=CARD, fg=SUB,
        ).pack(anchor="w", pady=(0, 6))
        self._ai_hint(inner, ai_ok)

        it = self._expression_pick()
        if not it:
            return
        card, body = self._lesson_card(inner, " 📣 今日表达课 ", self.EXPR_COLOR, it)
        for p in it.get("b", []):
            if p.startswith("今天的启发"):
                tk.Label(
                    body, text="💡 " + p, font=F_SMALL, bg="#FBF5E7", fg="#6B5B2E",
                    anchor="w", justify="left", wraplength=950,
                ).pack(fill="x", padx=18, pady=3)
            else:
                tk.Label(
                    body, text=p, font=F_SMALL, bg=CARD, fg=INK,
                    anchor="w", justify="left", wraplength=950,
                ).pack(fill="x", padx=18, pady=4)
        self._link_chips(body, it.get("links", []), "延伸学习：", self.EXPR_COLOR, "#E4EFEA", "#2E6B5A")
        self._fit(card, 140)

    # ------------------------------------------------------------ 每周总结
