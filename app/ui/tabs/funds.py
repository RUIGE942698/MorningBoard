# -*- coding: utf-8 -*-
"""MorningBoard 界面模块：funds。"""
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
class FundsTabMixin:
    # ---- funds ----
    def render_funds(self):
        inner = self.scroll_funds.inner
        for w in inner.winfo_children():
            w.destroy()

        funds = (self.data or {}).get("funds")
        if not funds:
            return

        indices = funds.get("indices") or []
        pcts = [i["pct"] for i in indices if isinstance(i.get("pct"), (int, float))]
        ups = sum(1 for p in pcts if p > 0)
        downs = sum(1 for p in pcts if p < 0)
        tone = funds.get("market_tone", "数据不足")

        # 市场横幅
        tone_color = {"普涨": C.UP, "普跌": C.DOWN}.get(tone, C.FLAT)
        banner = Card(inner, 1000, self._h(52), radius=12, fill=C.SOFT, outline=C.LINE)
        banner.pack(fill="x", pady=(2, 10))
        self._chip(banner.body, " 今日市场 ", tone_color, fg=C.ON_ACCENT).pack(side="left", padx=(18, 10), pady=13)
        tk.Label(
            banner.body, text="{0} · {1} 个指数：{2} 涨 {3} 跌".format(tone, len(pcts), ups, downs),
            font=F_BASE, bg=C.SOFT, fg=C.INK,
        ).pack(side="left", pady=12)
        if funds.get("index_error"):
            tk.Label(banner.body, text="（" + funds["index_error"] + "）", font=F_TINY, bg=C.SOFT, fg=C.SUB).pack(
                side="left", pady=13
            )

        # 指数卡片 4x2（点击跳腾讯行情）
        cfg_indices = config.load_config().get("indices", [])
        grid = tk.Frame(inner, bg=C.CARD)
        grid.pack(fill="x")
        for i in range(4):
            grid.grid_columnconfigure(i, weight=1, uniform="idx")
        for i, it in enumerate(indices[:8]):
            card = Card(grid, 1000, self._h(94), radius=12)
            card.grid(row=i // 4, column=i % 4, sticky="we", padx=4, pady=4)
            bw = card.body
            tk.Label(bw, text=it.get("name", ""), font=F_SMALL, bg=C.CARD, fg=C.SUB).pack(anchor="w", padx=(16, 0), pady=(8, 0))
            pr = it.get("price")
            pr_s = "--" if pr in (None, "-") else "{0:,.2f}".format(float(pr))
            tk.Label(bw, text=pr_s, font=F_NUM, bg=C.CARD, fg=C.INK).pack(anchor="w", padx=(16, 0), pady=(0, 0))
            pct = it.get("pct")
            chg = it.get("chg")
            arrow = "▲" if isinstance(pct, (int, float)) and pct > 0 else ("▼" if isinstance(pct, (int, float)) and pct < 0 else "·")
            chg_s = "--" if chg in (None, "-") else "{0:+,.2f}".format(float(chg))
            tk.Label(
                bw, text=" {0} {1}  {2}".format(arrow, self._fmt_pct(pct), chg_s),
                font=F_MID, bg=C.CARD, fg=self._pct_color(pct),
            ).pack(anchor="w", padx=(16, 0))
            secid = cfg_indices[i]["secid"] if i < len(cfg_indices) else ""
            tcode = fetch._to_tencent_code(secid) if secid else ""
            self._bind_click_tree(bw, lambda t=tcode: webbrowser.open("https://gu.qq.com/" + t))
        tk.Label(inner, text="🖱 点击指数卡跳转腾讯行情", font=F_TINY, bg=C.CARD, fg=C.SUB).pack(anchor="w", pady=(2, 0))

        # 涨幅榜
        top = funds.get("top_gainers") or []
        if top:
            tg = tk.Frame(inner, bg=C.CARD)
            tg.pack(fill="x", pady=(12, 6))
            tk.Label(tg, text="🔥 今日基金涨幅榜", font=F_MID, bg=C.CARD, fg=C.ACCENT).pack(side="left")
            tk.Label(tg, text="  （近1个交易日）", font=F_TINY, bg=C.CARD, fg=C.SUB).pack(side="left", pady=(2, 0))
            chips = tk.Frame(inner, bg=C.CARD)
            chips.pack(fill="x")
            for it in top[:5]:
                c = tk.Frame(chips, bg=C.SOFT)
                c.pack(side="left", padx=(0, 8), pady=2)
                tk.Label(c, text=" " + it.get("name", ""), font=F_SMALL, bg=C.SOFT, fg=C.INK).pack(side="left", padx=(8, 4), pady=3)
                tk.Label(c, text=self._fmt_pct(it.get("day")), font=F_MID, bg=C.SOFT, fg=self._pct_color(it.get("day"))).pack(
                    side="left", padx=(0, 8), pady=3
                )
                self._bind_click_tree(
                    c, lambda code=it.get("code", ""): webbrowser.open("https://fund.eastmoney.com/{0}.html".format(code))
                )

        # 自选基金表头
        fh = tk.Frame(inner, bg=C.CARD)
        fh.pack(fill="x", pady=(14, 4))
        tk.Label(fh, text="自选基金", font=F_H, bg=C.CARD, fg=C.TEAL).pack(side="left")
        tk.Label(fh, text="  点击任意行跳转天天基金详情", font=F_TINY, bg=C.CARD, fg=C.SUB).pack(side="left", pady=(4, 0))
        heads = ["基金", "净值走势", "最新净值", "日期", "日涨跌", "近1周", "近1月", "近3月"]
        hf = tk.Frame(inner, bg=C.CARD)
        hf.pack(fill="x", pady=(2, 2))
        for i, htxt in enumerate(heads):
            tk.Label(hf, text=htxt, font=F_TINY, bg=C.CARD, fg=C.SUB, width=11 if i else 22, anchor="w").grid(
                row=0, column=i, sticky="w", padx=6
            )

        # 基金行
        errs = []
        for f in funds.get("watchlist") or []:
            if f.get("error"):
                errs.append("{0}({1})".format(f.get("code"), f.get("error")))
            row = tk.Frame(inner, bg=C.CARD, highlightbackground=C.LINE, highlightthickness=1)
            row.pack(fill="x", pady=3)

            left = tk.Frame(row, bg=C.CARD)
            left.grid(row=0, column=0, sticky="w", padx=(12, 6), pady=8)
            left.grid_columnconfigure(0, weight=1)
            tk.Label(left, text=f.get("name", f.get("code", "")), font=F_MID, bg=C.CARD, fg=C.INK).pack(anchor="w")
            tk.Label(left, text=f.get("code", ""), font=F_TINY, bg=C.CARD, fg=C.SUB).pack(anchor="w")

            trend = f.get("trend") or []
            if len(trend) >= 2:
                sp = tk.Canvas(row, width=96, height=40, bg=C.CARD, highlightthickness=0, bd=0)
                sp.grid(row=0, column=1, padx=6)
                sparkline(sp, 96, 40, [v for _, v in trend])
            else:
                tk.Label(row, text="暂无走势", font=F_TINY, bg=C.CARD, fg=C.SUB).grid(row=0, column=1, padx=6)

            nav = f.get("nav")
            nav_s = "--" if nav in (None, 0) else "{0:.4f}".format(float(nav))
            tk.Label(row, text=nav_s, font=F_NUM, bg=C.CARD, fg=C.INK).grid(row=0, column=2, sticky="w", padx=6)
            tk.Label(row, text=f.get("nav_date", "--"), font=F_TINY, bg=C.CARD, fg=C.SUB).grid(row=0, column=3, sticky="w", padx=6)
            for ci, key in ((4, "day_chg"), (5, "w1"), (6, "m1"), (7, "m3")):
                v = f.get(key)
                tk.Label(row, text=self._fmt_pct(v), font=F_MID, bg=C.CARD, fg=self._pct_color(v)).grid(
                    row=0, column=ci, sticky="w", padx=6
                )
            self._bind_click_tree(
                row,
                lambda code=f.get("code", ""): webbrowser.open("https://fund.eastmoney.com/{0}.html".format(code)),
            )

        if errs:
            tk.Label(
                inner, text="提示：部分基金数据获取失败（{0}），稍后点右上角\"刷新数据\"重试。".format(errs[0]),
                font=F_TINY, bg=C.CARD, fg=C.SUB,
            ).pack(anchor="w", pady=6)

    # ============ 每日一课 ============
