# -*- coding: utf-8 -*-
"""MorningBoard 界面模块：weekly。"""
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
class WeeklyTabMixin:
    # ---- weekly ----
    def render_weekly(self):
        inner = self.scroll_weekly.inner
        for w in inner.winfo_children():
            w.destroy()
        weekly = (self.data or {}).get("weekly")
        if not weekly:
            card = Card(inner, 1000, self._h(190), radius=14)
            card.pack(fill="x", pady=24)
            tk.Label(card.body, text="🗓 每周总结", font=F_H, bg=C.CARD, fg=C.GOLD).pack(padx=22, pady=(20, 6))
            tk.Label(
                card.body, text="每周日《新闻联播》播完后自动生成，汇总本周八大主题：\n国际局势 · 时政 · 医学 · 科学 · AI科技 · 金融 · 民生 · 国内",
                font=F_BASE, bg=C.CARD, fg=C.INK, justify="left",
            ).pack(padx=22, pady=4)
            tk.Label(
                card.body, text="今晚 20:00 新闻播出后自动生成", font=F_SMALL, bg=C.CARD, fg=C.SUB,
            ).pack(padx=22, pady=(4, 20))
            return

        tk.Label(
            inner, text="🗓 每周总结  {0}".format(weekly.get("range", "")),
            font=F_H, bg=C.CARD, fg=C.GOLD,
        ).pack(anchor="w", pady=(2, 2))
        tk.Label(
            inner, text="梳理本周联播 {0} 条 · 生成于 {1}".format(
                weekly.get("news_count", 0), (weekly.get("generated_at") or "")[11:16]
            ),
            font=F_SMALL, bg=C.CARD, fg=C.SUB,
        ).pack(anchor="w", pady=(0, 8))

        idxw = weekly.get("indices") or []
        if idxw:
            tk.Label(inner, text="本周大盘", font=F_MID, bg=C.CARD, fg=C.TEAL).pack(anchor="w", pady=(0, 4))
            grid = tk.Frame(inner, bg=C.CARD)
            grid.pack(fill="x")
            for i in range(4):
                grid.grid_columnconfigure(i, weight=1, uniform="wk")
            for i, it in enumerate(idxw[:8]):
                card = Card(grid, 1000, self._h(80), radius=12)
                card.grid(row=i // 4, column=i % 4, sticky="we", padx=4, pady=4)
                bw = card.body
                tk.Label(bw, text=it.get("name", ""), font=F_SMALL, bg=C.CARD, fg=C.SUB).pack(anchor="w", padx=14, pady=(7, 0))
                try:
                    close_s = "{0:,.2f}".format(float(it.get("close", 0)))
                except (TypeError, ValueError):
                    close_s = "--"
                tk.Label(bw, text=close_s, font=F_NUM, bg=C.CARD, fg=C.INK).pack(anchor="w", padx=14)
                pct = it.get("week_pct")
                tk.Label(
                    bw, text="周涨跌 {0}".format(self._fmt_pct(pct)),
                    font=F_MID, bg=C.CARD, fg=self._pct_color(pct),
                ).pack(anchor="w", padx=14, pady=(0, 7))

        # 本周科技要闻（量子位 RSS + 官网入口）
        media = weekly.get("media") or {}
        qbit = media.get("qbitai") or []
        sites = media.get("sites") or []
        if qbit:
            mh = tk.Frame(inner, bg=C.CARD)
            mh.pack(fill="x", pady=(14, 4))
            tk.Label(mh, text="⚡ 本周科技要闻", font=F_MID, bg=C.CARD, fg=C.MUTED_BLUE).pack(side="left")
            for s in sites:
                self._btn(mh, "前往 {0} ↗".format(s.get("name", "")),
                          lambda u=s.get("url", ""): webbrowser.open(u)).pack(side="right", padx=4)
            tk.Label(
                inner, text="来源：量子位（AI/科技前沿）· 点击标题打开原文或搜索详情",
                font=F_TINY, bg=C.CARD, fg=C.SUB,
            ).pack(anchor="w", pady=(0, 4))
            for it in qbit:
                rc = Card(inner, 1000, self._h(40), radius=10)
                rc.pack(fill="x", pady=2)
                row = tk.Frame(rc.body, bg=C.CARD)
                row.pack(fill="both", expand=True, padx=(14, 12), pady=3)
                row.grid_columnconfigure(0, weight=1)
                tl = tk.Label(
                    row, text="▍" + it.get("title", ""), font=F_SMALL, bg=C.CARD, fg=C.LINK,
                    anchor="w", justify="left", cursor="hand2", wraplength=900,
                )
                tl.grid(row=0, column=0, sticky="we")
                tl.bind(
                    "<Button-1>",
                    lambda e, t=it.get("title", ""), u=it.get("url", ""): self._article_menu(e, t, u),
                )
                if it.get("desc"):
                    tk.Label(
                        row, text="📅 {0}  {1}".format(it.get("date", ""), it.get("desc", "")),
                        font=F_TINY, bg=C.CARD, fg=C.SUB, anchor="w", justify="left", wraplength=920,
                    ).grid(row=1, column=0, sticky="we", pady=(1, 0))
                self._fit(rc, 44)

        for sec in weekly.get("cats") or []:
            cat = sec.get("cat", "")
            color = WEEKLY_COLORS.get(cat, C.TEAL)
            ch = tk.Frame(inner, bg=C.CARD)
            ch.pack(fill="x", pady=(12, 4))
            self._chip(ch, " " + cat + " ", color, fg=C.ON_ACCENT).pack(side="left")
            tk.Label(ch, text="  {0} 条".format(len(sec.get("items", []))), font=F_SMALL, bg=C.CARD, fg=C.SUB).pack(
                side="left", pady=(1, 0)
            )
            for t in sec.get("items", []):
                rc = Card(inner, 1000, self._h(38), radius=10)
                rc.pack(fill="x", pady=2)
                row = tk.Frame(rc.body, bg=C.CARD)
                row.pack(fill="both", expand=True, padx=(14, 12), pady=4)
                row.grid_columnconfigure(0, weight=1)
                tk.Label(
                    row, text="•  " + t, font=F_SMALL, bg=C.CARD, fg=C.INK, anchor="w", justify="left",
                ).grid(row=0, column=0, sticky="we")

    # ------------------------------------------------------------ 术语词典
