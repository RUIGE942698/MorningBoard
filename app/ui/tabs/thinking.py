# -*- coding: utf-8 -*-
"""MorningBoard 界面模块：thinking。"""
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
class ThinkingTabMixin:
    # ---- thinking ----
    THINK_COLOR = "#B5651D"
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

    def render_thinking(self):
        inner = self.scroll_think.inner
        for w in inner.winfo_children():
            w.destroy()

        head = tk.Frame(inner, bg=CARD)
        head.pack(fill="x", pady=(2, 4))
        tk.Label(head, text="🧠 思辨训练", font=F_H, bg=CARD, fg=self.THINK_COLOR).pack(side="left")
        tk.Label(head, text="思维工具 · 论证对垒 · 谬误识别", font=F_SMALL, bg=CARD, fg=SUB).pack(
            side="left", padx=10, pady=(4, 0)
        )
        ai_ok = bool(((self.data or {}).get("thinking") or {}).get("items")) and not getattr(
            self, "_thinking_random", False
        )
        self._ai_badge(head, ai_ok)
        self._btn(head, "🎲 换一组", self._thinking_shuffle).pack(side="right")
        self._btn(head, "✨ AI 换新", lambda: self._start_ai_regen(("thinking",))).pack(
            side="right", padx=4
        )
        tk.Label(
            inner, text="训练方法：先读今日工具 → 用它拆解两道思辨题 → 再识别今日逻辑谬误。答案没有标准，论证过程即收获。",
            font=F_TINY, bg=CARD, fg=SUB,
        ).pack(anchor="w", pady=(0, 6))
        self._ai_hint(inner, ai_ok)

        # 1) 今日思维工具
        tool = self._tool_pick()
        if tool:
            card, body = self._lesson_card(inner, " 🧰 今日思维工具 ", self.THINK_COLOR, tool)
            for p in tool.get("b", []):
                tk.Label(
                    body, text=p, font=F_SMALL, bg=CARD, fg=INK,
                    anchor="w", justify="left", wraplength=950,
                ).pack(fill="x", padx=18, pady=4)
            self._link_chips(body, tool.get("links", []), "延伸工具：", self.THINK_COLOR, "#F5EBDD", "#8A5A20")
            self._fit(card, 120)

        # 2) 思辨题：论证对垒
        for i, it in enumerate(self._thinking_pick(2), 1):
            card, body = self._lesson_card(inner, " ⚖️ 思辨题 {0} ".format(i), "#4A6B8A", it)
            for p in it.get("pro", []):
                tk.Label(
                    body, text="✅ 正方：" + p, font=F_SMALL, bg=CARD, fg="#1E7A5A",
                    anchor="w", justify="left", wraplength=950,
                ).pack(fill="x", padx=18, pady=3)
            for p in it.get("con", []):
                tk.Label(
                    body, text="🔻 反方：" + p, font=F_SMALL, bg=CARD, fg="#B03A2E",
                    anchor="w", justify="left", wraplength=950,
                ).pack(fill="x", padx=18, pady=3)
            for p in it.get("ask", []):
                tk.Label(
                    body, text="❓ " + p, font=F_SMALL, bg="#F4F0E6", fg="#7A6530",
                    anchor="w", justify="left", wraplength=950,
                ).pack(fill="x", padx=18, pady=4)
            self._link_chips(body, it.get("links", []), "延伸思考：", self.THINK_COLOR, "#F5EBDD", "#8A5A20")
            self._fit(card, 120)

        # 3) 今日谬误
        fal = self._fallacy_pick()
        if fal:
            card, body = self._lesson_card(inner, " 🚨 今日谬误雷达 ", "#8E3B3B", fal)
            for p in fal.get("b", []):
                tk.Label(
                    body, text=p, font=F_SMALL, bg=CARD, fg=INK,
                    anchor="w", justify="left", wraplength=950,
                ).pack(fill="x", padx=18, pady=4)
            self._link_chips(body, fal.get("links", []), "延伸学习：", "#8E3B3B", "#F5E5E5", "#7A3030")
            self._fit(card, 120)

    # ------------------------------------------------------------ 表达能力
