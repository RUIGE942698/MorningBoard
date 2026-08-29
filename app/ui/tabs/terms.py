# -*- coding: utf-8 -*-
"""MorningBoard 界面模块：terms。"""
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
class TermsTabMixin:
    # ---- terms ----

    def _set_term_domain(self, d):
        self._term_domain = d
        self.render_terms()

    def _ai_expand_terms(self):
        """AI 生成并追加当前/随机领域的新术语。"""
        import random as _r

        from app import ai_gen, terms_updater

        if not ai_gen.enabled():
            tk.messagebox.showinfo(
                "AI 扩充", "未配置 DeepSeek API Key，无法生成。\n\n配置方法：系统环境变量添加 DEEPSEEK_API_KEY=你的key（platform.deepseek.com 申请），重启后生效。"
            )
            return
        doms = terms_updater.list_domains()
        if not doms:
            return
        domain = self._term_domain or _r.choice(doms)
        self._set_status("正在生成「{0}」新术语…".format(domain))

        def work():
            try:
                results = terms_updater.expand_domains([domain], 3)
                n = results[0][1] if results else 0
                self.root.after(0, lambda: self._terms_expanded(domain, n))
            except Exception:  # noqa: BLE001
                self.root.after(0, lambda: self._set_status("AI 扩充失败"))

        threading.Thread(target=work, daemon=True).start()

    def _terms_expanded(self, domain, n):
        self._set_status("「{0}」新增 {1} 条术语".format(domain, n))
        self.render_terms()
        tk.messagebox.showinfo("AI 扩充完成", "「{0}」已新增 {1} 条术语。".format(domain, n))

    def _ai_new_domain(self):
        """AI 生成一个全新领域并入库。"""
        from app import ai_gen, terms_updater

        if not ai_gen.enabled():
            tk.messagebox.showinfo(
                "新增领域", "未配置 DeepSeek API Key，无法生成。\n\n配置方法：系统环境变量添加 DEEPSEEK_API_KEY=你的key（platform.deepseek.com 申请），重启后生效。"
            )
            return
        self._set_status("正在策划新领域…")

        def work():
            try:
                domain = terms_updater.generate_new_domain(count=10)
                self.root.after(0, lambda: self._new_domain_done(domain))
            except Exception:  # noqa: BLE001
                self.root.after(0, lambda: self._new_domain_done(None))

        threading.Thread(target=work, daemon=True).start()

    def _new_domain_done(self, domain):
        if domain:
            self._set_status("新增领域「{0}」".format(domain))
            self.render_terms()
            tk.messagebox.showinfo("新增领域完成", "已新增领域「{0}」（10 条术语）。".format(domain))
        else:
            self._set_status("新领域生成失败或与现有领域重名，请重试")

    def _on_term_search(self, event=None):
        self._term_query = (self._term_search.get() if self._term_search else "").strip()
        self.render_terms()

    def render_terms(self):
        inner = self.scroll_terms.inner
        for w in inner.winfo_children():
            w.destroy()

        all_terms = knowledge.load_term_library()
        head = tk.Frame(inner, bg=C.CARD)
        head.pack(fill="x", pady=(2, 4))
        tk.Label(head, text="📖 术语词典", font=F_H, bg=C.CARD, fg=section('terms')[0]).pack(side="left")
        tk.Label(head, text="各领域专业名词与基础知识 · 系统补认知", font=F_SMALL, bg=C.CARD, fg=C.SUB).pack(
            side="left", padx=10, pady=(4, 0)
        )
        self._btn(head, "➕ 新增领域", self._ai_new_domain).pack(side="right", padx=4)
        self._btn(head, "🧠 AI 扩充", self._ai_expand_terms).pack(side="right", padx=4)
        tk.Label(head, text="🔍", font=F_SMALL, bg=C.CARD).pack(side="right", padx=(0, 4))
        self._term_search = tk.Entry(
            head, font=F_SMALL, width=26, bg=C.CARD, fg=C.INK, relief="solid", bd=1,
            highlightthickness=1, highlightbackground=C.LINE,
        )
        self._term_search.pack(side="right")
        if self._term_query:
            self._term_search.insert(0, self._term_query)
        self._term_search.bind("<KeyRelease>", self._on_term_search)

        # 领域筛选 chips
        domains = sorted({t["domain"] for t in all_terms})
        chips = tk.Frame(inner, bg=C.CARD)
        chips.pack(fill="x", pady=(4, 2))

        def make_chip(label, domain, active):
            lb = tk.Label(
                chips, text=" " + label + " ", font=F_SMALL,
                bg=(section('terms')[0] if active else C.SOFT),
                fg=(C.ON_ACCENT if active else C.INK),
                padx=9, pady=2, cursor="hand2",
            )
            return lb

        a = make_chip("全部", None, self._term_domain is None)
        a.pack(side="left", padx=(0, 6), pady=2)
        a.bind("<Button-1>", lambda e: self._set_term_domain(None))
        for dm in domains:
            lb = make_chip(dm, dm, self._term_domain == dm)
            lb.pack(side="left", padx=(0, 6), pady=2)
            lb.bind("<Button-1>", lambda e, d=dm: self._set_term_domain(d))

        # 筛选
        terms = all_terms
        if self._term_domain:
            terms = [t for t in terms if t["domain"] == self._term_domain]
        q = self._term_query
        if q:
            terms = [t for t in terms if q in t.get("t", "") or q in t.get("s", "")]

        # 流畅优化：全部视图限制渲染数量（控件过多是滚动卡顿主因），搜索/选领域时全量
        limited = False
        if not self._term_domain and not q and len(terms) > 100:
            terms = terms[:100]
            limited = True

        tk.Label(
            inner, text="共 {0} 条术语{1}".format(len(terms), " · 搜索“{0}”".format(q) if q else ""),
            font=F_TINY, bg=C.CARD, fg=C.SUB,
        ).pack(anchor="w", pady=(2, 4))
        if limited:
            tk.Label(
                inner, text="💡 术语较多，为流畅滚动仅展示前 100 条——点击上方领域或输入关键词查看全部",
                font=F_TINY, bg=C.CARD, fg=C.GOLD,
            ).pack(anchor="w", pady=(0, 4))

        cards = []
        for it in terms:
            card, body = self._lesson_card(inner, " " + it.get("domain", "") + " ", section('terms')[0], it)
            for p in it.get("b", []):
                tk.Label(
                    body, text=p, font=F_SMALL, bg=C.CARD, fg=C.INK,
                    anchor="w", justify="left", wraplength=950,
                ).pack(fill="x", padx=18, pady=3)
            self._link_chips(body, it.get("links", []), "延伸学习：", section('terms')[0], section("terms")[1], section("terms")[2])
            cards.append(card)
        # 批量布局：一次完成几何计算，再统一按内容自适应高度（避免逐卡 update_idletasks 卡顿）
        inner.update_idletasks()
        for card in cards:
            card.configure(height=max(110, card.body.winfo_reqheight() + 36))

    # ------------------------------------------------------------ 工具
