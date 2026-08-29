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

        _tc = section("think")[0]  # 板块强调色随主题（深色下自动提亮）
        head = tk.Frame(inner, bg=C.CARD)
        head.pack(fill="x", pady=(2, 4))
        tk.Label(head, text="🧠 思辨训练", font=F_H, bg=C.CARD, fg=_tc).pack(side="left")
        tk.Label(head, text="思维工具 · 论证对垒 · 谬误识别", font=F_SMALL, bg=C.CARD, fg=C.SUB, wraplength=540, justify="left").pack(
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
            inner, text="训练方法：先读今日工具 → 用它拆解两道思辨题 → 再识别今日逻辑谬误。答案没有标准，论证过程即收获。",
            font=F_TINY, bg=C.CARD, fg=C.SUB,
        ).pack(anchor="w", pady=(0, 6))
        self._ai_hint(inner, ai_ok)

        # 1) 今日思维工具
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

        # 2) 思辨题：论证对垒
        for i, it in enumerate(self._thinking_pick(2), 1):
            card, body = self._lesson_card(inner, " ⚖️ 思辨题 {0} ".format(i), C.MUTED_BLUE, it)
            _acc, _tint, _ink = section("think")
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

        # 3) 今日谬误
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
