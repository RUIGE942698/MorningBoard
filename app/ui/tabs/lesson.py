# -*- coding: utf-8 -*-
"""MorningBoard 界面模块：lesson。"""
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
class LessonTabMixin:
    # ---- lesson ----
    def render_lesson(self):
        inner = self.scroll_lesson.inner
        for w in inner.winfo_children():
            w.destroy()
        if not self.data or not self.data.get("lesson"):
            return
        plan = self.data["lesson"]

        # 控制条
        ctl = tk.Frame(inner, bg=C.CARD)
        ctl.pack(fill="x", pady=(2, 8))
        self.lbl_lesson_progress = tk.Label(ctl, text="", font=F_SMALL, bg=C.CARD, fg=C.SUB)
        self.lbl_lesson_progress.pack(side="left", padx=4)
        self.btn_random = self._btn(ctl, "🎲 换一条", self._random_lesson)
        self.btn_random.pack(side="right", padx=4)
        self.btn_history = self._btn(ctl, "📁 历史回顾", self._open_history)
        self.btn_history.pack(side="right", padx=4)
        self.btn_today = self._btn(ctl, "回到今日课程", self._back_to_today)
        self.btn_today.pack(side="right", padx=4)
        tk.Label(ctl, text="每日一课", font=F_H, bg=C.CARD, fg=C.INK).pack(side="left")

        # 主课卡片
        self._main_card = Card(inner, 1000, self._h(320), radius=16)
        self._main_card.pack(fill="x", pady=(0, 10))
        self._render_main_body(plan.get("main"))

        # 金句
        quote = plan.get("quote")
        if quote:
            qc = Card(inner, 1000, self._h(64), radius=12, fill=C.SOFT, outline=C.SOFT_LINE)
            qc.pack(fill="x", pady=(0, 10))
            tk.Label(qc.body, text="✒ 每日金句", font=F_TINY, bg=C.SOFT, fg=C.GOLD).pack(side="left", padx=(16, 8), pady=20)
            tk.Label(
                qc.body, text="“{0}”".format(quote.get("text", "")), font=("Microsoft YaHei UI", 10, "bold"),
                bg=C.SOFT, fg=section("lesson")[2], wraplength=760, justify="left",
            ).pack(side="left", padx=(0, 8), pady=18)
            tk.Label(qc.body, text="— " + quote.get("author", ""), font=F_SMALL, bg=C.SOFT, fg=C.SUB).pack(
                side="left", pady=20
            )

        # 小卡
        tk.Label(inner, text="今日小卡 · 整张卡片都可点，点哪都能展开", font=F_SMALL, bg=C.CARD, fg=C.SUB).pack(anchor="w", pady=(2, 4))
        cards = plan.get("cards") or []
        if cards:
            cg = tk.Frame(inner, bg=C.CARD)
            cg.pack(fill="x")
            for i in range(3):
                cg.grid_columnconfigure(i, weight=1, uniform="card")
            made = [self._render_mini_card(cg, i, it) for i, it in enumerate(cards)]
            self._equalize_mini_cards(made)

    def _render_main_body(self, item):
        for w in self._main_card.body.winfo_children():
            w.destroy()
        if not item:
            return
        self._cur_item = item
        cat = item.get("cat", "")
        color = CAT_COLORS.get(cat, C.TEAL)
        body = self._main_card.body

        # 模块1：分类徽章 + 进度
        top = tk.Frame(body, bg=C.CARD)
        top.pack(fill="x", padx=20, pady=(14, 2))
        self._chip(top, " " + cat + " ", color).pack(side="left")
        self.lbl_lesson_progress.configure(
            text="第 {0}/{1} 课".format(item.get("idx", 0) + 1, item.get("total", 0))
        )

        # 模块2：标题 + 一句话概括
        tk.Label(
            body, text=item.get("title", ""), font=("Microsoft YaHei UI", 15, "bold"),
            bg=C.CARD, fg=color, anchor="w", justify="left",
        ).pack(fill="x", padx=20, pady=(8, 0))
        tk.Label(
            body, text=item.get("sub", ""), font=F_SMALL, bg=C.CARD, fg=C.SUB, anchor="w", justify="left",
        ).pack(fill="x", padx=20, pady=(0, 6))

        # 模块3：正文（启发段抽出）+ 模块4：今日行动金卡
        paras = item.get("body", []) or []
        main_paras = [p for p in paras if not p.startswith("今天的启发")]
        action_paras = [p for p in paras if p.startswith("今天的启发")]
        if main_paras:
            f = tkfont.Font(root=self.root, family="Microsoft YaHei UI", size=10)
            per_line = max(10, int(940 / max(1, f.measure("测"))))
            total_lines = sum(max(1, math.ceil(len(p) / per_line)) for p in main_paras)
            btext = tk.Text(
                body, wrap="word", font=F_BASE, fg=C.INK, bg=C.CARD, bd=0,
                highlightthickness=0, height=total_lines + 1,
                spacing1=5, spacing3=7, padx=6, pady=2,
            )
            btext.pack(fill="x", padx=16, pady=2)
            btext.tag_configure("link", foreground=C.LINK, underline=True)
            full_text = "\n\n".join(main_paras) + "\n\n"
            btext.insert("1.0", full_text)
            for s, e, t in self._find_terms(full_text, knowledge.load_terms()):
                btext.tag_add("link", "1.0 + {0} chars".format(s), "1.0 + {0} chars".format(e))
            btext.tag_bind("link", "<Button-1>", self._on_text_link)
            btext.tag_bind("link", "<Enter>", lambda e: btext.configure(cursor="hand2"))
            btext.tag_bind("link", "<Leave>", lambda e: btext.configure(cursor=""))
            btext.configure(state="disabled")
        if action_paras:
            ac = tk.Frame(body, bg=C.SOFT, highlightbackground=C.SOFT_LINE, highlightthickness=1)
            ac.pack(fill="x", padx=20, pady=(4, 2))
            tk.Label(ac, text="💡 今日行动", font=F_SMALL, bg=C.SOFT, fg=C.GOLD).pack(anchor="w", padx=14, pady=(8, 2))
            for p in action_paras:
                tk.Label(
                    ac, text=p, font=F_BASE, bg=C.SOFT, fg=section("lesson")[2],
                    anchor="w", justify="left", wraplength=900,
                ).pack(fill="x", padx=14, pady=(0, 8))

        # 模块5：延伸学习
        links = item.get("links") or []
        if links:
            lf = tk.Frame(body, bg=C.CARD)
            lf.pack(fill="x", padx=20, pady=(6, 2))
            tk.Label(lf, text="延伸学习：", font=F_SMALL, bg=C.CARD, fg=C.GOLD).pack(side="left", pady=1)
            for term in links[:6]:
                chip = tk.Label(
                    lf, text=" " + term + " ", font=F_SMALL, bg=section("lesson")[1], fg=section("lesson")[2],
                    padx=7, pady=1, cursor="hand2",
                )
                chip.pack(side="left", padx=(0, 6), pady=1)
                chip.bind("<Button-1>", lambda e, t=term: self._link_menu(e, t))
            tk.Label(lf, text="点击名词→选平台", font=F_TINY, bg=C.CARD, fg=C.SUB).pack(side="left", padx=(2, 0))

        # 进度条 + 同类课程导航
        total = item.get("total", 0) or 1
        idx = item.get("idx", 0)
        pbar = tk.Canvas(body, width=200, height=10, bg=C.CARD, highlightthickness=0, bd=0)
        pbar.pack(anchor="w", padx=20, pady=(10, 6))
        rounded_rect(pbar, 1, 1, 200, 10, 5, fill=C.LINE, outline="")
        w_fill = max(6, int(200 * (idx + 1) / total))
        rounded_rect(pbar, 1, 1, w_fill, 10, 5, fill=color, outline="")

        nav = tk.Frame(body, bg=C.CARD)
        nav.pack(fill="x", padx=20, pady=(2, 14))
        tk.Label(nav, text="同类课程连续学", font=F_TINY, bg=C.CARD, fg=C.SUB).pack(side="left", pady=(4, 0))
        self._btn(nav, "← 上一篇", lambda: self._nav_lesson(-1)).pack(side="left", padx=(10, 4))
        self._btn(nav, "下一篇 →", lambda: self._nav_lesson(1)).pack(side="left", padx=4)

        # 高度自适应内容
        self._fit(self._main_card, 420)

    def _nav_lesson(self, delta):
        """同类课程切换：上一篇 / 下一篇。"""
        it = getattr(self, "_cur_item", None)
        if not it:
            return
        cat = it.get("cat", "")
        entries = (knowledge.load_all() or {}).get(cat) or []
        if not entries:
            return
        n = len(entries)
        idx = (int(it.get("idx", 0)) + delta) % n
        e = entries[idx]
        self._show_main({
            "cat": cat, "idx": idx, "total": n,
            "title": e.get("t", ""), "sub": e.get("s", ""),
            "body": e.get("b", []), "links": e.get("links", []),
        })

    def _render_mini_card(self, parent, i, it):
        card = Card(parent, 1000, self._h(170), radius=12)
        card.grid(row=i // 3, column=i % 3, sticky="we", padx=4, pady=4)
        card.wire(command=lambda it=it: self._show_main(it))
        color = CAT_COLORS.get(it.get("cat", ""), C.TEAL)
        self._chip(card.body, " " + it.get("cat", "") + " ", color).pack(anchor="w", padx=14, pady=(10, 3))
        tk.Label(
            card.body, text=it.get("title", ""), font=F_MID, bg=C.CARD, fg=C.INK,
            anchor="w", justify="left", wraplength=300,
        ).pack(fill="x", padx=14, pady=(0, 1))
        tk.Label(
            card.body, text=it.get("sub", ""), font=F_TINY, bg=C.CARD, fg=C.SUB,
            anchor="w", justify="left", wraplength=300,
        ).pack(fill="x", padx=14, pady=(0, 1))
        b0 = (it.get("body") or [""])[0]
        if b0:
            snip = b0 if len(b0) <= 40 else b0[:40] + "…"
            tk.Label(
                card.body, text=snip, font=F_TINY, bg=C.CARD, fg=C.SUB,
                anchor="w", justify="left", wraplength=300,
            ).pack(fill="x", padx=14, pady=(0, 2))
        cta = tk.Label(
            card.body,
            text="第 {0}/{1} 课 · 点击整张卡片展开 →".format(it.get("idx", 0) + 1, it.get("total", 0)),
            font=F_SMALL, bg=C.CARD, fg=C.GOLD,
        )
        cta.pack(anchor="w", padx=14, pady=(0, 8))
        # 悬停时 CTA 变强调色，配合卡片描边高亮，明确"这里能点"
        cta.bind("<Enter>", lambda e: cta.configure(fg=C.ACCENT))
        cta.bind("<Leave>", lambda e: cta.configure(fg=C.GOLD))
        return card

    def _equalize_mini_cards(self, cards, per_row=3):
        """小卡按内容自适应高度，并把同一排拉齐。

        坑：Card 是固定高度的 Canvas，内容超过卡片高度时会被**直接裁掉**
        （底部那行"点击展开"首当其冲——看不见也点不到，用户自然觉得"按键位置不明确"）。
        """
        if not cards:
            return
        try:
            self.root.update_idletasks()
        except Exception:  # noqa: BLE001
            pass
        base = self._h(170)
        need = []
        for c in cards:
            try:
                c.body.update_idletasks()
                need.append(max(base, c.body.winfo_reqheight() + 12))
            except Exception:  # noqa: BLE001
                need.append(base)
        for r in range(0, len(cards), per_row):
            chunk = cards[r : r + per_row]
            h = max(need[r : r + per_row])
            for c in chunk:
                c.configure(height=h)

    def _show_main(self, item):
        if not item:
            return
        self._render_main_body(item)

    def _random_lesson(self):
        if not self.data or not self.data.get("lesson"):
            return
        cat = self.data["lesson"]["main_cat"]
        entries = (knowledge.load_all() or {}).get(cat) or []
        if not entries:
            return
        e = random.choice(entries)
        item = {
            "cat": cat, "idx": 0, "total": len(entries),
            "title": e.get("t", ""), "sub": e.get("s", ""), "body": e.get("b", []),
            "links": e.get("links", []),
        }
        self._random_mode = True
        self._show_main(item)

    def _back_to_today(self):
        if not self.data or not self.data.get("lesson"):
            return
        self._random_mode = False
        self._show_main(self.data["lesson"].get("main"))

