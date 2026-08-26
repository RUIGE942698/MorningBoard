# -*- coding: utf-8 -*-
"""MorningBoard 界面模块：base。"""
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
class BaseTabMixin:
    # ---- base ----
    def _bind_click_tree(self, w, cmd):
        """给控件及其所有子控件绑定点击（整块区域可点）。"""
        w.configure(cursor="hand2")
        w.bind("<Button-1>", lambda e: cmd())
        for c in w.winfo_children():
            self._bind_click_tree(c, cmd)

    def _news_menu(self, event, title, url):
        """新闻标题点击：央视原视频 / 多平台搜索。"""
        m = tk.Menu(self.root, tearoff=0)
        q = urllib.parse.quote(title)
        if url:
            m.add_command(label="📺 央视原视频", command=lambda: webbrowser.open(url))
        m.add_command(label="百度搜索", command=lambda: webbrowser.open("https://www.baidu.com/s?wd=" + q))
        m.add_command(label="必应搜索", command=lambda: webbrowser.open("https://www.bing.com/search?q=" + q))
        m.add_command(label="B站搜索", command=lambda: webbrowser.open("https://search.bilibili.com/all?keyword=" + q))
        try:
            m.tk_popup(event.x_root, event.y_root)
        finally:
            m.grab_release()

    def _article_menu(self, event, title, url):
        """媒体文章点击：打开原文 / 多平台搜索。"""
        m = tk.Menu(self.root, tearoff=0)
        q = urllib.parse.quote(title)
        if url:
            m.add_command(label="🔗 打开原文", command=lambda: webbrowser.open(url))
        m.add_command(label="百度搜索", command=lambda: webbrowser.open("https://www.baidu.com/s?wd=" + q))
        m.add_command(label="必应搜索", command=lambda: webbrowser.open("https://www.bing.com/search?q=" + q))
        m.add_command(label="B站搜索", command=lambda: webbrowser.open("https://search.bilibili.com/all?keyword=" + q))
        try:
            m.tk_popup(event.x_root, event.y_root)
        finally:
            m.grab_release()

    @staticmethod
    @staticmethod
    def _find_terms(text, terms):
        """在正文中定位术语（长词优先、不重叠），返回 [(start, end, term)]。"""
        spans = []
        for term in terms:
            if not term:
                continue
            start = 0
            while True:
                i = text.find(term, start)
                if i < 0:
                    break
                if not any(s <= i < e for s, e, _ in spans):
                    spans.append((i, i + len(term), term))
                start = i + 1
        spans.sort()
        merged = []
        for s, e, t in spans:
            if merged and s < merged[-1][1]:
                continue
            merged.append((s, e, t))
        return merged

    def _on_text_link(self, event):
        w = event.widget
        try:
            idx = w.index("@{0},{1}".format(event.x, event.y))
        except Exception:  # noqa: BLE001
            return
        ranges = w.tag_ranges("link")
        for i in range(0, len(ranges), 2):
            if w.compare(ranges[i], "<=", idx) and w.compare(idx, "<", ranges[i + 1]):
                term = w.get(ranges[i], ranges[i + 1]).strip()
                if term:
                    self._link_menu(event, term)
                break

    def _link_menu(self, event, term):
        m = tk.Menu(self.root, tearoff=0)
        q = urllib.parse.quote(term)
        for name, url in PLATFORMS:
            m.add_command(label=name, command=lambda u=url.format(q=q): webbrowser.open(u))
        try:
            m.tk_popup(event.x_root, event.y_root)
        finally:
            m.grab_release()

    # ------------------------------------------------------------ 思辨训练
    def _lesson_card(self, inner, chip_text, chip_color, it):
        """通用知识卡头：chip + 标题 + 一句话。返回 (card, body)。"""
        card = Card(inner, 1000, self._h(120), radius=14)
        card.pack(fill="x", pady=6)
        body = card.body
        self._chip(body, chip_text, chip_color).pack(anchor="w", padx=18, pady=(12, 2))
        tk.Label(
            body, text=it.get("t", ""), font=("Microsoft YaHei UI", 13, "bold"),
            bg=CARD, fg=INK, anchor="w", justify="left", wraplength=950,
        ).pack(fill="x", padx=18)
        if it.get("s"):
            tk.Label(
                body, text=it.get("s", ""), font=F_SMALL, bg=CARD, fg=SUB,
                anchor="w", justify="left", wraplength=950,
            ).pack(fill="x", padx=18, pady=(2, 4))
        return card, body

    def _link_chips(self, parent, links, label="延伸学习：", color=GOLD, bg="#F3EBD9", fg="#7A6530"):
        if not links:
            return
        lf = tk.Frame(parent, bg=CARD)
        lf.pack(fill="x", padx=18, pady=(6, 2))
        tk.Label(lf, text=label, font=F_SMALL, bg=CARD, fg=color).pack(side="left", pady=1)
        for term in links[:6]:
            chip = tk.Label(
                lf, text=" " + term + " ", font=F_SMALL, bg=bg, fg=fg,
                padx=7, pady=1, cursor="hand2",
            )
            chip.pack(side="left", padx=(0, 6), pady=1)
            chip.bind("<Button-1>", lambda e, t=term: self._link_menu(e, t))

    def _fit(self, card, min_h):
        """先完成布局，再按内容实际高度自适应卡片（避免内容溢出/挤压）。"""
        card.body.update_idletasks()
        card.configure(height=max(min_h, card.body.winfo_reqheight() + 36))

    def _h(self, base):
        """按 DPI 缩放放大固定高度（150% 缩放下字号放大，卡片高度需同步放大防重叠）。"""
        return int(base * getattr(self, "_dpi_scale", 1.0))

    def _on_global_wheel(self, e):
        """全局滚轮：鼠标在任意控件上滚动时，滚动其所在板块。"""
        w = e.widget
        while w is not None:
            if isinstance(w, ScrollFrame):
                w._on_wheel(e)
                return "break"
            try:
                w = w.master
            except Exception:  # noqa: BLE001
                break
        return None

    @staticmethod
    @staticmethod
    def _pct_color(v):
        if v is None:
            return SUB
        try:
            f = float(v)
        except (TypeError, ValueError):
            return SUB
        return UP if f > 0 else (DOWN if f < 0 else SUB)

    @staticmethod
    @staticmethod
    def _fmt_pct(v):
        if v is None:
            return "--"
        try:
            f = float(v)
        except (TypeError, ValueError):
            return "--"
        return "{0:+.2f}%".format(f)
