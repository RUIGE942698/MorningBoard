# -*- coding: utf-8 -*-
"""MorningBoard 界面模块：history。"""
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
class HistoryTabMixin:
    # ---- history ----
    def _open_history_folder(self):
        """用资源管理器打开归档文件夹。"""
        import subprocess
        hist_dir = os.path.join(config.CACHE_DIR, "history")
        os.makedirs(hist_dir, exist_ok=True)
        subprocess.Popen(["explorer", hist_dir])

    def _backup_history(self):
        """把全部历史归档复制到桌面「晨报历史档案」文件夹。"""
        import shutil
        hist_dir = os.path.join(config.CACHE_DIR, "history")
        desktop = os.path.join(os.path.expanduser("~"), "Desktop")
        target = os.path.join(desktop, "晨报历史档案")
        os.makedirs(target, exist_ok=True)
        n = 0
        for fn in os.listdir(hist_dir):
            if fn.endswith(".json"):
                try:
                    shutil.copy2(os.path.join(hist_dir, fn), os.path.join(target, fn))
                    n += 1
                except Exception:  # noqa: BLE001
                    pass
        if n:
            tk.messagebox.showinfo("备份完成", "已将 {0} 天的历史档案复制到桌面「晨报历史档案」文件夹。\n以后每天备份会自动同步新增的日期。".format(n))
        else:
            tk.messagebox.showinfo("备份", "暂无历史档案可备份（每天 20:00 生成内容后自动归档）。")

    def _open_history(self):
        """历史回顾：切换到独立板块并刷新列表。"""
        self.render_history()
        self.nb.select(self.tab_history)

    def render_history(self):
        """独立板块：历史归档日期列表 + 内容浏览。"""
        import glob

        hist_dir = os.path.join(config.CACHE_DIR, "history")
        self._hist_files = sorted(glob.glob(os.path.join(hist_dir, "*.json")), reverse=True)
        self.hist_listbox.delete(0, "end")
        if not self._hist_files:
            self.lbl_history_stat.configure(text="暂无历史记录")
            self.hist_text.configure(state="normal")
            self.hist_text.delete("1.0", "end")
            self.hist_text.insert("end", "暂无历史记录\n\n每天 20:00 生成内容后会自动归档到这里，从明天起即可回看每天的课程。", "body")
            self.hist_text.configure(state="disabled")
            return
        dates = [os.path.basename(f)[:10] for f in self._hist_files]
        for d in dates:
            self.hist_listbox.insert("end", d)
        self.lbl_history_stat.configure(text="共 {0} 天记录".format(len(dates)))
        self.hist_listbox.selection_set(0)
        self._on_history_select()

    def _on_history_select(self, _event=None):
        import json as _json
        sel = self.hist_listbox.curselection()
        files = getattr(self, "_hist_files", [])
        if not sel or sel[0] >= len(files):
            return
        try:
            with open(files[sel[0]], encoding="utf-8") as f:
                data = _json.load(f)
        except Exception:  # noqa: BLE001
            return
        self._render_archive_text(self.hist_text, data)

    def _render_archive_text(self, txt, data):
        txt.configure(state="normal")
        txt.delete("1.0", "end")
        flag = " · ✨ AI 生成" if data.get("ai_generated") else " · 静态精选"
        if data.get("dedup"):
            flag += "  ⚠ {0}".format(data["dedup"])
        txt.insert("end", "{0} {1}{2}\n".format(data.get("date", ""), data.get("weekday", ""), flag), "date")
        lesson = data.get("lesson") or {}
        if lesson:
            txt.insert("end", "【每日一课 · {0}】\n".format(data.get("lesson_cat", "")), "h")
            txt.insert("end", lesson.get("title", "") + "\n", "h")
            txt.insert("end", lesson.get("sub", "") + "\n", "sub")
            for p in lesson.get("body", []) or []:
                txt.insert("end", p + "\n\n", "body")
            links = lesson.get("links") or []
            if links:
                txt.insert("end", "延伸名词：" + " · ".join(links) + "\n", "sub")
        th = data.get("thinking") or []
        if th:
            txt.insert("end", "━" * 30 + "\n", "sep")
            txt.insert("end", "\n【思辨训练】\n", "lab")
            for i, it in enumerate(th, 1):
                txt.insert("end", "⚖️ 思辨题 {0}：{1}\n".format(i, it.get("t", "")), "item")
                for p in it.get("pro", []):
                    txt.insert("end", "  ✅ " + p + "\n", "item")
                for p in it.get("con", []):
                    txt.insert("end", "  🔻 " + p + "\n", "item")
                for p in it.get("ask", []):
                    txt.insert("end", "  ❓ " + p + "\n", "item")
                txt.insert("end", "\n", "item")
        ex = data.get("expression")
        if ex:
            txt.insert("end", "━" * 30 + "\n", "sep")
            txt.insert("end", "\n【表达能力】\n", "lab")
            txt.insert("end", ex.get("t", "") + "\n", "h")
            txt.insert("end", ex.get("s", "") + "\n", "sub")
            for p in ex.get("b", []) or []:
                txt.insert("end", p + "\n\n", "body")
        cards = data.get("lesson_cards") or []
        if cards:
            txt.insert("end", "━" * 30 + "\n", "sep")
            txt.insert("end", "\n【今日小卡】\n", "lab")
            for i, c in enumerate(cards, 1):
                if i > 1:
                    txt.insert("end", "·   ·   ·   ·   ·   ·   ·\n", "sep")
                txt.insert("end", "▎卡{0:02d}  [{1}]  {2}\n".format(i, c.get("cat", ""), c.get("title", "")), "h")
                if c.get("sub"):
                    txt.insert("end", "     {0}\n".format(c.get("sub", "")), "sub")
                for p in c.get("body", []) or []:
                    txt.insert("end", "     " + p + "\n\n", "item")
                links = c.get("links") or []
                if links:
                    txt.insert("end", "     延伸名词：" + " · ".join(links) + "\n", "sub")
        quote = data.get("quote")
        if quote and quote.get("text"):
            txt.insert("end", "━" * 30 + "\n", "sep")
            txt.insert("end", "\n✒ 金句：{0} — {1}\n".format(quote.get("text", ""), quote.get("author", "")), "sub")
        hl = data.get("news_headlines") or []
        if hl:
            txt.insert("end", "━" * 30 + "\n", "sep")
            txt.insert("end", "\n【当日联播要闻】\n", "lab")
            for t in hl:
                txt.insert("end", "  · " + t + "\n", "item")
        idx = data.get("indices") or []
        if idx:
            parts = []
            for it in idx:
                try:
                    pct_s = "{0:+.2f}%".format(float(it.get("pct")))
                except (TypeError, ValueError):
                    pct_s = "--"
                parts.append("{0} {1} ({2})".format(it.get("name", ""), it.get("price", ""), pct_s))
            txt.insert("end", "━" * 30 + "\n", "sep")
            txt.insert("end", "\n【指数收盘】\n", "lab")
            txt.insert("end", "  " + "  ".join(parts) + "\n", "item")
        tech = data.get("tech") or []
        if tech:
            txt.insert("end", "━" * 30 + "\n", "sep")
            txt.insert("end", "\n【科技前沿】\n", "lab")
            for t in tech:
                txt.insert("end", "  · " + t.get("title", "") + "\n", "item")
        txt.configure(state="disabled")

