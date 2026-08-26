# -*- coding: utf-8 -*-
"""MorningBoard 界面模块：news。"""
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
class NewsTabMixin:
    # ---- news ----
    def render_news(self):
        inner = self.scroll_news.inner
        for w in inner.winfo_children():
            w.destroy()

        news = (self.data or {}).get("news") or {}
        items = news.get("items") or []
        if not items:
            card = Card(inner, 900, 90)
            card.pack(pady=10)
            tk.Label(
                card.body, text="今日联播内容暂未获取到：{0}".format(news.get("error", "未知原因")),
                font=F_BASE, bg=CARD, fg=UP,
            ).pack(padx=20, pady=8)
            tk.Label(
                card.body, text="新闻联播每天 19:00 播出，早间开机自动回退显示前一晚节目单。",
                font=F_SMALL, bg=CARD, fg=SUB,
            ).pack(padx=20)
            return

        groups = {}
        for it in items:
            g = classify_news(it.get("title", ""))
            groups.setdefault(g, []).append(it)

        # 统计条
        stat = Card(inner, 1000, self._h(44), radius=12, fill="#FBF7EE", outline=LINE)
        stat.pack(fill="x", pady=(2, 8))
        parts = ["共 {0} 条".format(len(items))]
        order = ["时政", "国内", "国际", "财经科技", "快讯"]
        for g in order:
            if g in groups:
                parts.append("{0} {1}".format(g, len(groups[g])))
        tk.Label(
            stat.body, text="  ·  ".join(parts), font=F_SMALL, bg="#FBF7EE", fg=SUB,
        ).pack(pady=10)

        # 头条
        head = items[0]
        hc = Card(inner, 1000, self._h(92), radius=14, fill="#FBF2EC", outline="#E4C9BE")
        hc.pack(fill="x", pady=(0, 10))
        row = tk.Frame(hc.body, bg="#FBF2EC")
        row.pack(fill="x", padx=18, pady=10)
        tk.Label(row, text="头条", font=F_TINY, bg=ACCENT, fg="#FFFFFF", padx=8, pady=2).pack(side="left")
        head_lb = tk.Label(
            row, text=head.get("title", ""), font=("Microsoft YaHei UI", 12, "bold"),
            bg="#FBF2EC", fg="#1F5FA8", wraplength=880, justify="left", cursor="hand2",
        )
        head_lb.pack(side="left", padx=10)
        head_lb.bind(
            "<Button-1>",
            lambda e, t=head.get("title", ""), u=head.get("url", ""): self._news_menu(e, t, u),
        )
        tk.Label(inner, text="🖱 点击任意新闻标题：看央视原视频或搜索详情", font=F_TINY, bg=CARD, fg=SUB).pack(
            anchor="w", pady=(0, 4)
        )

        # 分组
        for g in order:
            if g not in groups:
                continue
            gh = tk.Frame(inner, bg=CARD)
            gh.pack(fill="x", pady=(10, 4))
            self._chip(gh, " " + g + "要闻 ", GROUP_COLORS[g], fg="#FFFFFF").pack(side="left")
            tk.Label(
                gh, text="  {0} 条".format(len(groups[g])), font=F_SMALL, bg=CARD, fg=SUB,
            ).pack(side="left", pady=(1, 0))

            for i, it in enumerate(groups[g]):
                rc = Card(inner, 1000, self._h(44), radius=10, fill=CARD)
                rc.pack(fill="x", pady=2)
                row = tk.Frame(rc.body, bg=CARD)
                row.pack(fill="both", expand=True, padx=(10, 12), pady=4)
                row.grid_columnconfigure(0, minsize=40)   # 编号列固定宽，保证对齐
                row.grid_columnconfigure(1, weight=1)     # 标题列占满剩余宽度
                num = tk.Label(
                    row, text="{0:02d}".format(i + 1), font=("Consolas", 9, "bold"),
                    bg=GROUP_COLORS[g], fg="#FFFFFF", width=3, anchor="center",
                )
                num.grid(row=0, column=0, sticky="w", pady=6)
                title_lb = tk.Label(
                    row, text=it.get("title", ""), font=F_BASE, bg=CARD, fg="#1F5FA8",
                    anchor="w", justify="left", cursor="hand2",
                )
                title_lb.grid(row=0, column=1, sticky="we", padx=(12, 0), pady=6)
                title_lb.bind(
                    "<Button-1>",
                    lambda e, t=it.get("title", ""), u=it.get("url", ""): self._news_menu(e, t, u),
                )

        # 科技前沿（InfoQ / IT之家 / 量子位 / 掘金 多源聚合）
        tech = news.get("tech") or {}
        tech_items = tech.get("items") or []
        if tech_items:
            th = tk.Frame(inner, bg=CARD)
            th.pack(fill="x", pady=(14, 4))
            tk.Label(th, text="⚡ 科技前沿", font=F_MID, bg=CARD, fg="#4A6B8A").pack(side="left")
            for s in tech.get("sites") or []:
                self._btn(th, "前往 {0} ↗".format(s.get("name", "")),
                          lambda u=s.get("url", ""): webbrowser.open(u)).pack(side="right", padx=4)
            tk.Label(
                inner, text="来源：InfoQ / IT 之家 / 量子位 / 掘金 · 点击标题打开原文或搜索详情",
                font=F_TINY, bg=CARD, fg=SUB,
            ).pack(anchor="w", pady=(0, 4))
            for it in tech_items:
                rc = Card(inner, 1000, 40, radius=10)
                rc.pack(fill="x", pady=2)
                row = tk.Frame(rc.body, bg=CARD)
                row.pack(fill="both", expand=True, padx=(14, 12), pady=3)
                row.grid_columnconfigure(0, weight=1)
                src = it.get("source", "")
                title_text = ("▍[" + src + "] " if src else "▍") + it.get("title", "")
                tl = tk.Label(
                    row, text=title_text, font=F_SMALL, bg=CARD, fg="#1F5FA8",
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
                        font=F_TINY, bg=CARD, fg=SUB, anchor="w", justify="left", wraplength=920,
                    ).grid(row=1, column=0, sticky="we", pady=(1, 0))
                self._fit(rc, 44)

    # ============ 基金 ============
