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
                font=F_BASE, bg=C.CARD, fg=C.UP,
            ).pack(padx=20, pady=8)
            tk.Label(
                card.body, text="新闻联播每天 19:00 播出，早间开机自动回退显示前一晚节目单。",
                font=F_SMALL, bg=C.CARD, fg=C.SUB,
            ).pack(padx=20)
            return

        groups = {}
        for it in items:
            g = classify_news(it.get("title", ""))
            groups.setdefault(g, []).append(it)

        # 统计条
        stat = Card(inner, 1000, self._h(44), radius=12, fill=C.SOFT, outline=C.LINE)
        stat.pack(fill="x", pady=(2, 8))
        parts = ["共 {0} 条".format(len(items))]
        order = ["时政", "国内", "国际", "财经", "快讯"]
        for g in order:
            if g in groups:
                parts.append("{0} {1}".format(g, len(groups[g])))
        tk.Label(
            stat.body, text="  ·  ".join(parts), font=F_SMALL, bg=C.SOFT, fg=C.SUB,
        ).pack(pady=10)

        # 头条
        head = items[0]
        hc = Card(inner, 1000, self._h(92), radius=14, fill=C.SOFT, outline=C.SOFT_LINE)
        hc.pack(fill="x", pady=(0, 10))
        row = tk.Frame(hc.body, bg=C.SOFT)
        row.pack(fill="x", padx=18, pady=10)
        tk.Label(row, text="头条", font=F_TINY, bg=C.ACCENT, fg=C.ON_ACCENT, padx=8, pady=2).pack(side="left")
        head_lb = tk.Label(
            row, text=head.get("title", ""), font=("Microsoft YaHei UI", 12, "bold"),
            bg=C.SOFT, fg=C.LINK, wraplength=880, justify="left", cursor="hand2",
        )
        head_lb.pack(side="left", padx=10)
        head_lb.bind(
            "<Button-1>",
            lambda e, t=head.get("title", ""), u=head.get("url", ""): self._news_menu(e, t, u),
        )
        tk.Label(inner, text="🖱 点击任意新闻标题：看央视原视频或搜索详情", font=F_TINY, bg=C.CARD, fg=C.SUB).pack(
            anchor="w", pady=(0, 4)
        )

        # 分组
        for g in order:
            if g not in groups:
                continue
            gh = tk.Frame(inner, bg=C.CARD)
            gh.pack(fill="x", pady=(10, 4))
            self._chip(gh, " " + g + "要闻 ", GROUP_COLORS[g], fg=C.ON_ACCENT).pack(side="left")
            tk.Label(
                gh, text="  {0} 条".format(len(groups[g])), font=F_SMALL, bg=C.CARD, fg=C.SUB,
            ).pack(side="left", pady=(1, 0))

            for i, it in enumerate(groups[g]):
                rc = Card(inner, 1000, self._h(44), radius=10, fill=C.CARD)
                rc.pack(fill="x", pady=2)
                row = tk.Frame(rc.body, bg=C.CARD)
                row.pack(fill="both", expand=True, padx=(10, 12), pady=4)
                row.grid_columnconfigure(0, minsize=40)   # 编号列固定宽，保证对齐
                row.grid_columnconfigure(1, weight=1)     # 标题列占满剩余宽度
                num = tk.Label(
                    row, text="{0:02d}".format(i + 1), font=("Consolas", 9, "bold"),
                    bg=GROUP_COLORS[g], fg=C.ON_ACCENT, width=3, anchor="center",
                )
                num.grid(row=0, column=0, sticky="w", pady=6)
                title_lb = tk.Label(
                    row, text=it.get("title", ""), font=F_BASE, bg=C.CARD, fg=C.LINK,
                    anchor="w", justify="left", cursor="hand2",
                )
                title_lb.grid(row=0, column=1, sticky="we", padx=(12, 0), pady=6)
                title_lb.bind(
                    "<Button-1>",
                    lambda e, t=it.get("title", ""), u=it.get("url", ""): self._news_menu(e, t, u),
                )

        # 前沿速报单独放一个常驻容器：切换难度时只动这一块，绝不重建上方新闻列表
        self._tech_box = tk.Frame(inner, bg=C.CARD)
        self._tech_box.pack(fill="x")
        self._render_tech(self._tech_box, news.get("tech") or {})

    # ============ 前沿速报（AI / 科技 / 科学） ============
    @staticmethod
    def _rel_time(age_hours):
        if age_hours is None:
            return "刚刚"
        if age_hours < 1:
            return "{0} 分钟前".format(int(age_hours * 60))
        if age_hours < 48:
            return "{0} 小时前".format(int(round(age_hours)))
        return "{0} 天前".format(int(age_hours // 24))

    def _set_tech_diff(self, opt):
        """切换阅读难度：只切换已有条目的显隐，不重建整页。

        原来这里直接调 render_news()，会把整个新闻页签（含上方全部新闻联播内容）
        销毁重建，副作用有三个，用户感知到的就是「页面跳回顶端重新加载」：
          1. inner 一度变空 → canvas 的 scrollregion 塌缩到 0 → Tk 把 yview 夹回顶部
          2. 上方与难度无关的内容也跟着重建，白闪一下
          3. 重建几十张卡片，有可感知的卡顿
        改为 pack_forget / pack 切换显隐：不销毁控件、不闪、滚动位置原样保留。
        """
        self._tech_diff = opt
        btn = getattr(self, "_tech_diff_btn", None)
        if btn is not None:
            try:
                btn.configure(text="难度：{0} ▾".format(opt))
            except Exception:  # noqa: BLE001
                pass
        self._apply_tech_diff()

    def _apply_tech_diff(self):
        """按当前难度过滤显隐；顺带把视口位置钉住，内容变矮也不会跳回顶部。"""
        diff = getattr(self, "_tech_diff", "全部")
        want = {"通俗+中等": ("通俗", "中等"), "仅通俗": ("通俗",),
                "仅专业": ("专业",)}.get(diff)
        blocks = getattr(self, "_tech_blocks", None) or []
        if not blocks:
            return

        sf = getattr(self, "scroll_news", None)
        pos = None
        if sf is not None:
            try:
                pos = sf.canvas.canvasy(0)      # 视口顶部在 inner 坐标里的位置
            except Exception:  # noqa: BLE001
                pos = None

        total = 0
        for blk in blocks:
            for card, _dlab in blk["cards"]:
                card.pack_forget()
            blk["head"].pack_forget()
            shown = [c for c, d in blk["cards"] if want is None or d in want]
            if not shown:
                continue                            # 该分组全被滤掉：连标题一起隐藏
            # 先 pack 标题再 pack 卡片，顺序不能反（Tk 的 pack 顺序 = 调用顺序）
            blk["head"].pack(fill="x", pady=(8, 3))
            blk["count"].configure(text="  {0} 条".format(len(shown)))
            for card in shown:
                card.pack(fill="x", pady=2)
            total += len(shown)

        empty = getattr(self, "_tech_empty", None)
        if empty is not None:
            if total:
                empty.pack_forget()
            else:
                empty.pack(anchor="w", pady=(6, 2))

        if sf is not None and pos:
            try:
                self.root.update_idletasks()
                total = sf.inner.winfo_reqheight()
                if total > 0:
                    sf.canvas.yview_moveto(min(1.0, float(pos) / total))
            except Exception:  # noqa: BLE001
                pass

    def _render_tech(self, inner, tech):
        items = tech.get("items") or []
        if not items:
            return
        # 注意：这里不再按难度预先过滤。全部条目一次建好，难度切换只在
        # _apply_tech_diff 里切换显隐——预过滤会让每次切换都必须重建（跳顶的根因）。
        updated = (tech.get("updated_at") or "")
        th = tk.Frame(inner, bg=C.CARD)
        th.pack(fill="x", pady=(14, 4))
        tk.Label(th, text="⚡ 前沿速报", font=F_MID, bg=C.CARD,
                 fg=C.MUTED_BLUE).pack(side="left")
        if updated:
            tk.Label(th, text="  更新 {0}".format(updated[11:16]), font=F_TINY,
                     bg=C.CARD, fg=C.SUB).pack(side="left")
        sites = [s for s in (tech.get("sites") or [])
                 if s.get("name") and s.get("url")]
        if sites:
            mb = tk.Menubutton(th, text="信源入口 ▾", relief="flat", bg=C.SOFT,
                               fg=C.LINK, font=F_TINY, cursor="hand2",
                               padx=8, pady=2)
            m = tk.Menu(mb, tearoff=0)
            for s in sites:
                m.add_command(label=s.get("name"),
                              command=lambda u=s.get("url"): webbrowser.open(u))
            mb.configure(menu=m)
            mb.pack(side="right", padx=4)
        vocab_today = tech.get("vocab_today") or []
        vb = tk.Menubutton(th, text="📓 生词本 {0} ▾".format(len(vocab_today)),
                           relief="flat", bg=C.SOFT, fg=C.LINK, font=F_TINY,
                           cursor="hand2", padx=8, pady=2)
        vmenu = tk.Menu(vb, tearoff=0)
        vmenu.add_command(label="查看今日生词（{0} 个）".format(len(vocab_today)),
                          command=lambda: self._tech_vocab_dialog(tech))
        vmenu.add_command(label="导出 Markdown 到桌面",
                          command=lambda: self._tech_vocab_export(tech))
        vb.configure(menu=vmenu)
        vb.pack(side="right", padx=4)

        diff = getattr(self, "_tech_diff", "全部")
        db = self._tech_diff_btn = tk.Menubutton(
            th, text="难度：{0} ▾".format(diff), relief="flat",
                           bg=C.SOFT, fg=C.LINK, font=F_TINY, cursor="hand2",
                           padx=8, pady=2)
        dmenu = tk.Menu(db, tearoff=0)
        for opt in ("全部", "通俗+中等", "仅通俗", "仅专业"):
            dmenu.add_command(label=opt,
                              command=lambda o=opt: self._set_tech_diff(o))
        db.configure(menu=dmenu)
        db.pack(side="right", padx=4)

        tk.Label(inner, text="多源聚合 · 质量评分 · 难度分级 ｜ 点标题看原文；点「详情/延伸」看人话版、关键概念、先修知识与延伸阅读",
                 font=F_TINY, bg=C.CARD, fg=C.SUB).pack(anchor="w", pady=(0, 4))

        # 空状态：某些难度档（如「仅通俗」）当天可能一条都没有，
        # 光隐藏条目会留下一片空白，看起来像坏了。给一句兜底提示。
        self._tech_empty = tk.Label(
            inner, text="当前难度下暂无条目，换个筛选看看 →", font=F_SMALL,
            bg=C.CARD, fg=C.SUB)

        # 每个分组一个容器：标题与卡片同属一组，切换难度时整组一起显隐。
        # 顺序即 pack 顺序，_apply_tech_diff 会先全 forget 再按记录顺序重 pack，
        # 所以反复切换不会打乱分组次序。
        self._tech_blocks = []
        for key, label in (("ai", "前沿 AI"), ("tech", "科技产业"), ("physics", "物理"), ("medicine", "医学"), ("biology", "生物"), ("math", "数学")):
            gs = [x for x in items if (x.get("group") or "tech") == key]
            if not gs:
                continue
            gbox = tk.Frame(inner, bg=C.CARD)
            gbox.pack(fill="x")
            gh = tk.Frame(gbox, bg=C.CARD)
            gh.pack(fill="x", pady=(8, 3))
            self._chip(gh, " " + label + " ", C.MUTED_BLUE, fg=C.ON_ACCENT).pack(side="left")
            cnt = tk.Label(gh, text="  {0} 条".format(len(gs)), font=F_SMALL,
                           bg=C.CARD, fg=C.SUB)
            cnt.pack(side="left")
            blk = {"head": gh, "count": cnt, "cards": []}
            self._tech_blocks.append(blk)
            for it in gs:
                rc = Card(gbox, 1000, 52, radius=10)
                rc.pack(fill="x", pady=2)
                row = tk.Frame(rc.body, bg=C.CARD)
                row.pack(fill="both", expand=True, padx=(12, 10), pady=3)
                row.grid_columnconfigure(0, weight=1)
                score = it.get("score") or 0
                stars = "★" * max(1, min(5, int(round(score / 20.0))))
                dlab = ((it.get("explain") or {}).get("difficulty")) or "中等"
                dtag = {"通俗": "🟢通俗", "中等": "🟡中等", "专业": "🔴专业"}.get(dlab, dlab)
                meta = "{0} · {1} · {2}分 {3} · {4}".format(
                    it.get("source", ""), self._rel_time(it.get("age_hours")),
                    score, stars, dtag)
                tk.Label(row, text=meta, font=F_TINY, bg=C.CARD, fg=C.ACCENT).grid(
                    row=0, column=0, sticky="w")
                tl = tk.Label(row, text=it.get("title", ""), font=F_SMALL, bg=C.CARD,
                              fg=C.LINK, anchor="w", justify="left", cursor="hand2",
                              wraplength=780)
                tl.grid(row=1, column=0, sticky="we")
                tl.bind("<Button-1>", lambda e, t=it.get("title", ""), u=it.get("url", ""):
                        self._article_menu(e, t, u))
                if it.get("desc"):
                    tk.Label(row, text=fetch._clean_text(it.get("desc", ""))[:120],
                             font=F_TINY, bg=C.CARD, fg=C.SUB, anchor="w", justify="left",
                             wraplength=800).grid(row=2, column=0, sticky="we")
                self._btn(row, "详情/延伸", lambda i=it: self._tech_detail(i)).grid(
                    row=0, column=1, rowspan=3, padx=(8, 0))
                self._fit(rc, 52)
                blk["cards"].append((rc, dlab))

        self._apply_tech_diff()

    def _tech_detail(self, it):
        """详情弹窗：完整摘要 + 多平台延伸阅读 + 同主题其它来源。"""
        win = tk.Toplevel(self.root)
        win.title("前沿消息详情")
        win.configure(bg="#FFFDF7")
        win.geometry("780x540+220+120")
        try:
            win.attributes("-topmost", True)
        except Exception:  # noqa: BLE001
            pass
        title = it.get("title", "")
        tk.Label(win, text=title, bg="#FFFDF7", fg="#2A2722", wraplength=710,
                 justify="left", anchor="w",
                 font=("Microsoft YaHei UI", 12, "bold")).pack(anchor="w", padx=18, pady=(14, 2))
        if it.get("title_en"):
            tk.Label(win, text=it.get("title_en"), bg="#FFFDF7", fg="#8A8577",
                     wraplength=710, justify="left", anchor="w",
                     font=("Microsoft YaHei UI", 9)).pack(anchor="w", padx=18)
        ex = it.get("explain") or {}
        meta = "{0} · {1} · {2}分 · 阅读难度 {3} · {4}".format(
            it.get("source", ""), self._rel_time(it.get("age_hours")),
            it.get("score", ""), ex.get("difficulty") or "中等", it.get("date", ""))
        tk.Label(win, text=meta, bg="#FFFDF7", fg="#8C6B3F", anchor="w",
                 font=("Microsoft YaHei UI", 9)).pack(anchor="w", padx=18, pady=(2, 8))
        body = tk.Text(win, wrap="word", height=13, relief="flat", bg="#FFFFFF",
                       fg="#2A2722", font=("Microsoft YaHei UI", 10), padx=12, pady=8)
        body.pack(fill="both", expand=True, padx=18)
        body.tag_configure("h", font=("Microsoft YaHei UI", 10, "bold"),
                           foreground="#8C6B3F")
        body.tag_configure("term", font=("Microsoft YaHei UI", 10, "bold"),
                           foreground="#2A2722")
        if ex.get("eli5"):
            body.insert("end", "【人话版】\n", "h")
            body.insert("end", ex["eli5"] + "\n\n")
        if ex.get("prereq") and ex.get("difficulty") == "专业":
            body.insert("end", "【先修知识】（读这条前建议先知道）\n", "h")
            for t in ex["prereq"]:
                nm = t.get("t") or ""
                tag = "jump_" + str(abs(hash(nm)))
                body.tag_configure(tag, foreground="#3B6FA0", underline=True)
                body.tag_bind(tag, "<Button-1>", lambda e, n=nm: self._goto_term(n))
                body.insert("end", "• " + nm + "：", ("term", tag))
                body.insert("end", (t.get("d") or "") + "\n")
            body.insert("end", "\n")
        terms = ex.get("terms") or []
        if terms:
            body.insert("end", "【关键概念】（点词条可跳到术语词典）\n", "h")
            for t in terms:
                nm = t.get("t") or ""
                tag = "jump_" + str(abs(hash(nm)))
                body.tag_configure(tag, foreground="#3B6FA0", underline=True)
                body.tag_bind(tag, "<Button-1>", lambda e, n=nm: self._goto_term(n))
                body.insert("end", "• " + nm + "：", ("term", tag))
                body.insert("end", (t.get("d") or "") +
                            ("（术语词典）" if t.get("src") == "dict" else "（AI 解读）") + "\n")
            body.insert("end", "\n")
        if ex.get("why"):
            body.insert("end", "【为什么值得关注】\n", "h")
            body.insert("end", ex["why"] + "\n\n")
        body.insert("end", "【原始摘要】\n", "h")
        body.insert("end", (it.get("desc") or "（该源未提供摘要，点下方按钮打开原文查看）") + "\n")
        if it.get("also_in"):
            body.insert("end", "\n同主题其它来源：{0}\n".format("、".join(it["also_in"])))
        body.configure(state="disabled")

        bar = tk.Frame(win, bg="#FFFDF7")
        bar.pack(fill="x", pady=10, padx=18)
        q = urllib.parse.quote(title)
        for label, url in (
            ("打开原文", it.get("url", "")),
            ("百度检索", "https://www.baidu.com/s?wd=" + q),
            ("知乎检索", "https://www.zhihu.com/search?type=content&q=" + q),
            ("百度学术", "https://xueshu.baidu.com/s?wd=" + q),
            ("arXiv检索", "https://arxiv.org/search/?query=" + q + "&searchtype=all"),
            ("必应检索", "https://www.bing.com/search?q=" + q),
        ):
            if not url:
                continue
            tk.Button(bar, text=label, relief="flat", bg="#EFE9DA", fg="#2A2722",
                      font=("Microsoft YaHei UI", 9), cursor="hand2",
                      command=lambda u=url: webbrowser.open(u)).pack(side="left", padx=4)
        tk.Button(bar, text="关闭", relief="flat", bg="#EFE9DA", fg="#2A2722",
                  font=("Microsoft YaHei UI", 9), command=win.destroy).pack(side="right", padx=4)

    def _goto_term(self, name):
        """跳到「术语词典」并按该词搜索。

        步骤：① 把生词先同步进词典（AI 生成的概念原先不在词典里，才导致"跳过去是空的"）
              ② 领域筛选切回「全部」 ③ 填入关键词并搜索
        """
        try:
            from app import frontier as _fr
            try:
                _fr.sync_vocab_to_terms()        # 幂等：词典里没有的会补进去
            except Exception:  # noqa: BLE001
                pass
            if getattr(self, "_term_search", None) is None:
                self.render_terms()
            try:
                if getattr(self, "_term_domain", None) is not None:
                    self._set_term_domain(None)   # 切回「全部」领域
            except Exception:  # noqa: BLE001
                pass
            self._term_search.delete(0, "end")
            self._term_search.insert(0, name)
            self._term_query = name
            self._render_terms_list()
            self.nb.select(self.tab_terms)
            # 词典里仍然没有（例如概念名与录入名差异较大）→ 给出解释与检索入口，避免空白页
            try:
                from app import knowledge as _k
                lib = _k.load_term_library() or []
                if not [t for t in lib
                        if name in (t.get("t") or "") or name in (t.get("s") or "")]:
                    tk.messagebox.showinfo(
                        "术语词典暂无该词",
                        "「{0}」已加入术语词典，但需切换标签或重开播报窗口才能看到。\n\n"
                        "也可先用检索了解：百度 / 知乎 / 百度学术。".format(name))
            except Exception:  # noqa: BLE001
                pass
        except Exception:  # noqa: BLE001
            webbrowser.open("https://www.baidu.com/s?wd=" + urllib.parse.quote(name))

    def _vocab_rows(self, tech, limit_hist=60):
        """今日新增 + 历史累积（来自 cache/frontier_vocab.json）。"""
        today = tech.get("vocab_today") or []
        hist = []
        try:
            from app import frontier as _fr
            hist = (_fr.load_vocab().get("items") or [])[:limit_hist]
        except Exception:  # noqa: BLE001
            pass
        return today, hist

    def _vocab_days(self, limit=14):
        """已存档的生词日期（近 N 天）。"""
        try:
            from app import frontier as _fr
            return _fr.list_vocab_days(limit=limit)
        except Exception:  # noqa: BLE001
            return []

    def _vocab_of_day(self, day):
        try:
            from app import frontier as _fr
            return _fr.load_vocab_day(day)
        except Exception:  # noqa: BLE001
            return []

    def _tech_vocab_dialog(self, tech, day=None):
        """每日生词本：按日期 / 按领域两种视图 + 导出（今日 / 本月 / 全部历史）。"""
        today, hist = self._vocab_rows(tech)
        days = self._vocab_days()
        cur = {"day": day or dt.date.today().isoformat(), "mode": "日期"}

        win = tk.Toplevel(self.root)
        win.title("每日生词本")
        win.configure(bg="#FFFDF7")
        win.geometry("800x600+230+90")
        try:
            win.attributes("-topmost", True)
        except Exception:  # noqa: BLE001
            pass
        head = tk.Frame(win, bg="#FFFDF7")
        head.pack(fill="x", padx=18, pady=(14, 2))
        tk.Label(head, text="📓 每日生词本", bg="#FFFDF7", fg="#2A2722",
                 font=("Microsoft YaHei UI", 13, "bold")).pack(side="left")
        tk.Label(head, text="  点词条跳「术语词典」｜按天存档：cache/vocab/",
                 bg="#FFFDF7", fg="#8C6B3F",
                 font=("Microsoft YaHei UI", 9)).pack(side="left")

        bar0 = tk.Frame(win, bg="#FFFDF7")
        bar0.pack(fill="x", padx=18, pady=(6, 2))
        tk.Label(bar0, text="分组：", bg="#FFFDF7", fg="#8A8577",
                 font=("Microsoft YaHei UI", 9)).pack(side="left")
        mode_btns = {}
        for m in ("日期", "领域"):
            b = tk.Button(bar0, text=m, relief="flat", bg="#EFE9DA", fg="#2A2722",
                          font=("Microsoft YaHei UI", 9), cursor="hand2",
                          command=lambda mm=m: pick_mode(mm))
            b.pack(side="left", padx=3)
            mode_btns[m] = b

        bar1 = tk.Frame(win, bg="#FFFDF7")
        bar1.pack(fill="x", padx=18, pady=(2, 6))
        date_lb = tk.Label(bar1, text="日期：", bg="#FFFDF7", fg="#8A8577",
                           font=("Microsoft YaHei UI", 9))
        date_lb.pack(side="left")

        body = tk.Text(win, wrap="word", relief="flat", bg="#FFFFFF", fg="#2A2722",
                       font=("Microsoft YaHei UI", 10), padx=12, pady=8)
        body.pack(fill="both", expand=True, padx=18, pady=(2, 8))
        body.tag_configure("h", font=("Microsoft YaHei UI", 10, "bold"),
                           foreground="#8C6B3F")
        body.tag_configure("src", foreground="#8A8577",
                           font=("Microsoft YaHei UI", 8))
        body.tag_configure("new", foreground="#1E8449",
                           font=("Microsoft YaHei UI", 8, "bold"))
        body.tag_configure("cnt", foreground="#8A8577",
                           font=("Microsoft YaHei UI", 8))

        def add_term(r, show_item=True):
            nm = r.get("t") or ""
            tag = "vj_" + str(abs(hash(nm)))
            body.tag_configure(tag, foreground="#3B6FA0", underline=True)
            body.tag_bind(tag, "<Button-1>", lambda e, n=nm: self._goto_term(n))
            body.insert("end", "• " + nm + "：", ("term", tag))
            body.insert("end", (r.get("d") or ""))
            if r.get("new_today"):
                body.insert("end", "  新增", "new")
            if (r.get("hits_today") or 1) > 1:
                body.insert("end", "  ×{0}".format(r["hits_today"]), "cnt")
            body.insert("end", "\n")
            if show_item and r.get("item"):
                body.insert("end", "    出自：{0}\n".format(r["item"][:52]), "src")

        def render():
            body.configure(state="normal")
            body.delete("1.0", "end")
            if cur["mode"] == "领域":
                try:
                    from app import frontier as _fr
                    rows = (_fr.load_vocab().get("items") or [])
                    groups = _fr.vocab_by_domain(rows)
                except Exception:  # noqa: BLE001
                    groups = []
                body.insert("end", "【按领域】共 {0} 个概念（滚动总表）\n\n".format(len(rows)), "h")
                for label, items in groups:
                    body.insert("end", "◆ {0}（{1}）\n".format(label, len(items)), "h")
                    for r in items[:60]:
                        add_term(r)
                    if len(items) > 60:
                        body.insert("end", "  …… 其余 {0} 个见导出文件\n".format(len(items) - 60),
                                    "cnt")
                    body.insert("end", "\n")
            else:
                which = cur["day"]
                rows = (today if which == dt.date.today().isoformat() else None) \
                    or self._vocab_of_day(which)
                new_n = sum(1 for r in rows if r.get("new_today"))
                body.insert("end", "【{0}】当天 {1} 个词条（其中新增 {2} 个）\n\n".format(
                    which, len(rows), new_n), "h")
                for r in rows:
                    add_term(r)
            body.configure(state="disabled")

        def pick_mode(m):
            cur["mode"] = m
            for k, b in mode_btns.items():
                b.configure(bg="#D8CFB8" if k == m else "#EFE9DA")
            for w in bar1.winfo_children():
                if isinstance(w, tk.Button):
                    w.destroy()
            if m == "日期":
                date_lb.pack(side="left")
                for d, cnt, new in days:
                    tk.Button(bar1, text="{0}（{1}）".format(d[5:], cnt), relief="flat",
                              bg="#D8CFB8" if d == cur["day"] else "#EFE9DA", fg="#2A2722",
                              font=("Microsoft YaHei UI", 9), cursor="hand2",
                              command=lambda dd=d: pick(dd)).pack(side="left", padx=3)
            else:
                date_lb.pack_forget()
                tk.Label(bar1, text="（按领域汇总全部已收集的概念，最多每领域 60 条）",
                         bg="#FFFDF7", fg="#8A8577",
                         font=("Microsoft YaHei UI", 9)).pack(side="left")
            render()

        def pick(d):
            cur["day"] = d
            for w in bar1.winfo_children():
                if isinstance(w, tk.Button):
                    w.configure(bg="#D8CFB8" if w.cget("text").startswith(d[5:]) else "#EFE9DA")
            render()

        pick_mode("日期")

        bar = tk.Frame(win, bg="#FFFDF7")
        bar.pack(fill="x", pady=(0, 12), padx=18)
        tk.Button(bar, text="导出今日", relief="flat", bg="#EFE9DA", fg="#2A2722",
                  font=("Microsoft YaHei UI", 9), cursor="hand2",
                  command=lambda: self._tech_vocab_export(tech, all_days=False)
                  ).pack(side="left", padx=3)
        tk.Button(bar, text="导出本月汇总", relief="flat", bg="#EFE9DA", fg="#2A2722",
                  font=("Microsoft YaHei UI", 9), cursor="hand2",
                  command=self._tech_vocab_export_month).pack(side="left", padx=3)
        tk.Button(bar, text="导出全部历史", relief="flat", bg="#EFE9DA", fg="#2A2722",
                  font=("Microsoft YaHei UI", 9), cursor="hand2",
                  command=lambda: self._tech_vocab_export(tech, all_days=True)
                  ).pack(side="left", padx=3)
        tk.Button(bar, text="关闭", relief="flat", bg="#EFE9DA", fg="#2A2722",
                  font=("Microsoft YaHei UI", 9), command=win.destroy).pack(side="right")

    def _tech_vocab_export_month(self, month=None):
        """导出月度汇总（含领域分布、高频概念、每日明细）。"""
        from tkinter import messagebox as _mb
        try:
            from app import frontier as _fr
            path = _fr.export_month_markdown(month)
            data = _fr.monthly_rollup(month)
            _mb.showinfo("导出成功", "已导出 {0} 月度汇总：\n{1}\n\n"
                         "覆盖 {2} 天 / {3} 条记录 / 新增 {4} 个概念".format(
                             data["month"], path, len(data["days"]),
                             data["total"], data["new"]))
        except Exception as e:  # noqa: BLE001
            _mb.showerror("导出失败", str(e))

    def _tech_vocab_export(self, tech, all_days=False):
        """导出 Markdown：今日一份，或全部历史（按天分节）。"""
        from tkinter import messagebox as _mb
        try:
            out_dir = os.path.join(os.path.expanduser("~"), "Desktop", "每日播报生词本")
            os.makedirs(out_dir, exist_ok=True)
            stamp = dt.datetime.now().strftime("%Y-%m-%d")
            if all_days:
                path = os.path.join(out_dir, "生词本_全部历史_{0}.md".format(stamp))
                days = self._vocab_days(limit=365)
                with open(path, "w", encoding="utf-8") as f:
                    f.write("# 每日播报生词本 · 全部历史\n\n导出时间：{0}\n\n".format(
                        dt.datetime.now().strftime("%Y-%m-%d %H:%M")))
                    total = 0
                    for d, cnt, new in days:
                        rows = self._vocab_of_day(d)
                        f.write("\n## {0}（{1} 个，新增 {2}）\n\n".format(d, cnt, new))
                        for r in rows:
                            f.write("- **{0}**：{1}{2}\n".format(
                                r.get("t", ""), r.get("d", ""),
                                " ｜出自：" + r["item"] if r.get("item") else ""))
                        total += len(rows)
                    f.write("\n---\n共 {0} 天 / {1} 条词条记录\n".format(len(days), total))
            else:
                today, hist = self._vocab_rows(tech, limit_hist=200)
                rows = today + [x for x in hist if x not in today]
                path = os.path.join(out_dir, "生词本_{0}.md".format(stamp))
                with open(path, "w", encoding="utf-8") as f:
                    f.write("# 每日播报生词本\n\n生成时间：{0}\n\n".format(
                        dt.datetime.now().strftime("%Y-%m-%d %H:%M")))
                    f.write("## 今日新增（{0}）\n\n".format(len(today)))
                    for r in today:
                        f.write("- **{0}**：{1}\n".format(r.get("t", ""), r.get("d", "")))
                        if r.get("item"):
                            f.write("  - 出自：{0}\n".format(r["item"]))
                    f.write("\n## 历史累积\n\n")
                    for r in hist:
                        f.write("- **{0}**：{1}\n".format(r.get("t", ""), r.get("d", "")))
            _mb.showinfo("导出成功", "已导出到：\n{0}".format(path))
        except Exception as e:  # noqa: BLE001
            _mb.showerror("导出失败", str(e))

    # ============ 基金 ============
