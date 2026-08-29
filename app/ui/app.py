# -*- coding: utf-8 -*-
"""MorningBoard 主应用：MorningApp 组合各标签页 mixin。"""
import datetime as dt
import os
import threading
import tkinter as tk
from tkinter import ttk
import webbrowser
from app import ai_gen, config, generate
from app.ui.theme import *
from app.ui.widgets import *
from .tabs.base import BaseTabMixin
from .tabs.news import NewsTabMixin
from .tabs.funds import FundsTabMixin
from .tabs.lesson import LessonTabMixin
from .tabs.history import HistoryTabMixin
from .tabs.thinking import ThinkingTabMixin
from .tabs.expression import ExpressionTabMixin
from .tabs.weekly import WeeklyTabMixin
from .tabs.terms import TermsTabMixin

class MorningApp(BaseTabMixin, NewsTabMixin, FundsTabMixin, LessonTabMixin, HistoryTabMixin, ThinkingTabMixin, ExpressionTabMixin, WeeklyTabMixin, TermsTabMixin):
    def __init__(self, root, smoke=False):
        self.root = root
        self.smoke = smoke
        self._refreshing = False
        self._random_mode = False
        self._term_domain = None
        self._term_query = ""
        self._term_search = None
        self.data = self._load_cache()

        self.root.title("每日晨报 · MorningBoard")
        # 全局滚轮：鼠标在任意控件上都能滚动所在板块
        self.root.bind_all("<MouseWheel>", self._on_global_wheel)
        ico = os.path.join(config.ROOT, "tools", "csgo_bg.ico")
        if not os.path.exists(ico):
            ico = os.path.join(config.ROOT, "tools", "csgo.ico")
        if os.path.exists(ico):
            try:
                self.root.iconbitmap(ico)
            except Exception:  # noqa: BLE001
                pass
        # DPI 缩放：设置 tk 内部缩放 + 窗口尺寸按系统缩放放大（防止高分屏模糊/偏小）
        dpi_scale = 1.0
        try:
            import ctypes
            sf = ctypes.windll.shcore.GetScaleFactorForDevice(0)  # 100/125/150/200
            dpi_scale = max(1.0, sf / 100.0)
            self.root.tk.call("tk", "scaling", sf / 75.0)
        except Exception:  # noqa: BLE001
            pass
        self._dpi_scale = dpi_scale

        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        w = min(int(1180 * dpi_scale), int(sw * 0.92))
        h = min(int(840 * dpi_scale), int(sh * 0.92))
        self.root.geometry("{0}x{1}+{2}+{3}".format(w, h, max(0, (sw - w) // 2), max(0, (sh - h) // 2 - 20)))
        # 先应用用户保存的主题，再构建界面（否则会先按默认主题画一遍再重画）
        try:
            _saved = (config.load_config() or {}).get("theme")
            if _saved:
                set_theme(_saved)
        except Exception:  # noqa: BLE001
            pass
        self.root.configure(bg=C.BG)
        self.root.minsize(int(1000 * dpi_scale), int(700 * dpi_scale))

        self._build_style()
        self._build_topbar()
        self._build_statusbar()
        self._build_notebook()
        self.render_all()

        if smoke:
            self.root.after(3000, self.root.destroy)

        today = dt.date.today()
        today_iso = today.isoformat()
        news_date = ((self.data or {}).get("news") or {}).get("date") or ""
        # 双保险：缓存日期不是今天，或联播日期早于昨天（如 20:00 生成任务没跑成）→ 后台刷新
        news_stale = bool(news_date) and news_date < (today - dt.timedelta(days=1)).isoformat()
        # 三保险：AI 可用，但今日缓存里思辨/表达两块是空的（上次生成时 AI 没生效）→ 后台补生成
        ai_missing = False
        try:
            if ai_gen.enabled() and self.data and self.data.get("date") == today_iso:
                ai_missing = not ((self.data.get("thinking") or {}).get("items")) and not (
                    self.data.get("expression")
                )
        except Exception:  # noqa: BLE001
            ai_missing = False
        if not self.data or self.data.get("date") != today_iso or news_stale or ai_missing:
            self._set_status("正在更新晨报数据…")
            self._start_refresh()

    # ------------------------------------------------------------ 构建
    def _build_style(self):
        """ttk 控件样式。切主题时会重新调用一次，所以这里全部走 C 取色。"""
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TNotebook", background=C.BG, borderwidth=0)
        style.configure("TNotebook.Tab", font=F_SMALL, padding=(20, 8), background=C.SOFT, foreground=C.INK)
        style.map("TNotebook.Tab", background=[("selected", C.CARD)], foreground=[("selected", C.ACCENT)])
        style.configure("Vertical.TScrollbar", background=C.LINE, troughcolor=C.BG, bordercolor=C.BG, arrowcolor=C.SUB)

    def _btn(self, parent, text, cmd, **kw):
        return tk.Button(
            parent, text=text, command=cmd, font=F_SMALL, bg=C.CARD, fg=C.INK,
            activebackground=C.CARD_HOVER, activeforeground=C.ACCENT, relief="flat", bd=1,
            highlightthickness=1, highlightbackground=C.LINE, highlightcolor=C.LINE,
            padx=12, pady=3, cursor="hand2", **kw,
        )

    def _chip(self, parent, text, color, font=None, fg=None):
        # fg 默认 None（不是写死 #FFFFFF）：深色主题下强调底上要用深色字才看得清
        return tk.Label(
            parent, text=text, font=font or F_TINY, bg=color, fg=(fg or C.ON_ACCENT), padx=7, pady=1,
        )

    def _build_topbar(self):
        # 可重复调用：切主题时销毁重建（pack 时用 before=nb 保持排在笔记本身上面）
        if getattr(self, "_topbar", None) is not None:
            self._topbar.destroy()
        bar = tk.Frame(self.root, bg=C.BG)
        kw = {"fill": "x", "padx": 18, "pady": (14, 8)}
        if getattr(self, "nb", None) is not None:
            kw["before"] = self.nb
        bar.pack(**kw)
        self._topbar = bar

        logo = Card(bar, 44, 44, radius=12, fill=C.ACCENT, outline=C.ACCENT)
        logo.pack(side="left")
        tk.Label(logo.body, text="晨", font=("Microsoft YaHei UI", 17, "bold"), bg=C.ACCENT, fg=C.ON_ACCENT).pack(
            padx=13, pady=8
        )

        tk.Label(bar, text="每日晨报", font=F_TITLE, bg=C.BG, fg=C.INK).pack(side="left", padx=(12, 0))
        tk.Label(bar, text="MorningBoard · 每天 30 秒看世界", font=F_SMALL, bg=C.BG, fg=C.SUB).pack(
            side="left", padx=10, pady=(6, 0)
        )

        self.lbl_status = tk.Label(bar, text="", font=F_SMALL, bg=C.BG, fg=C.SUB)
        self.lbl_status.pack(side="right", padx=(0, 12))

        self.btn_web = self._btn(bar, "打开央视网", lambda: webbrowser.open("https://tv.cctv.com/lm/xwlb/"))
        self.btn_web.pack(side="right", padx=4)

        if not hasattr(self, "var_top"):
            self.var_top = tk.BooleanVar(value=False)
        tk.Checkbutton(
            bar, text="置顶", variable=self.var_top, command=self._toggle_top,
            font=F_SMALL, bg=C.BG, fg=C.INK, activebackground=C.BG, selectcolor=C.CARD,
        ).pack(side="right", padx=4)
        self.root.attributes("-topmost", self.var_top.get())

        self.btn_refresh = self._btn(bar, "刷新数据", self._start_refresh)
        self.btn_refresh.pack(side="right", padx=4)

        self.btn_theme = self._btn(bar, "🎨 主题", self._open_theme_menu)
        self.btn_theme.pack(side="right", padx=4)

        self.lbl_date = tk.Label(bar, text="", font=F_MID, bg=C.BG, fg=C.ACCENT)
        self.lbl_date.pack(side="right", padx=12)

    def _build_statusbar(self):
        if getattr(self, "_statusbar", None) is not None:
            self._statusbar.destroy()
        sb = tk.Frame(self.root, bg=C.BG)
        kw = {"fill": "x", "padx": 20, "pady": (0, 8)}
        if getattr(self, "nb", None) is not None:
            kw["after"] = self.nb
        sb.pack(**kw)
        self._statusbar = sb
        self.lbl_foot = tk.Label(
            sb, text="", font=F_TINY, bg=C.BG, fg=C.SUB, justify="left", anchor="w",
        )
        self.lbl_foot.pack(side="left")

    def _build_notebook(self):
        self.nb = ttk.Notebook(self.root)
        self.nb.pack(fill="both", expand=True, padx=12, pady=(2, 6))

        self.tab_news = tk.Frame(self.nb, bg=C.CARD)
        self.tab_funds = tk.Frame(self.nb, bg=C.CARD)
        self.tab_lesson = tk.Frame(self.nb, bg=C.CARD)
        self.tab_weekly = tk.Frame(self.nb, bg=C.CARD)
        self.tab_think = tk.Frame(self.nb, bg=C.CARD)
        self.tab_express = tk.Frame(self.nb, bg=C.CARD)
        self.tab_terms = tk.Frame(self.nb, bg=C.CARD)
        self.tab_history = tk.Frame(self.nb, bg=C.CARD)
        self.nb.add(self.tab_news, text="📰 新闻联播")
        self.nb.add(self.tab_funds, text="📈 基金投资")
        self.nb.add(self.tab_lesson, text="📚 每日一课")
        self.nb.add(self.tab_weekly, text="🗓 每周总结")
        self.nb.add(self.tab_think, text="🧠 思辨训练")
        self.nb.add(self.tab_express, text="📣 表达能力")
        self.nb.add(self.tab_terms, text="📖 术语词典")
        self.nb.add(self.tab_history, text="📁 历史回顾")

        self.scroll_news = ScrollFrame(self.tab_news)
        self.scroll_news.pack(fill="both", expand=True, padx=14, pady=12)
        self.scroll_funds = ScrollFrame(self.tab_funds)
        self.scroll_funds.pack(fill="both", expand=True, padx=14, pady=12)
        self.scroll_lesson = ScrollFrame(self.tab_lesson)
        self.scroll_lesson.pack(fill="both", expand=True, padx=14, pady=12)
        self.scroll_weekly = ScrollFrame(self.tab_weekly)
        self.scroll_weekly.pack(fill="both", expand=True, padx=14, pady=12)
        self.scroll_think = ScrollFrame(self.tab_think)
        self.scroll_think.pack(fill="both", expand=True, padx=14, pady=12)
        self.scroll_express = ScrollFrame(self.tab_express)
        self.scroll_express.pack(fill="both", expand=True, padx=14, pady=12)
        self.scroll_terms = ScrollFrame(self.tab_terms)
        self.scroll_terms.pack(fill="both", expand=True, padx=14, pady=12)

        self._build_history_pane()

    def _build_history_pane(self):
        """历史回顾页（左日期列表 + 右正文）。可重复调用，切主题时销毁重建。"""
        if getattr(self, "_hist_head", None) is not None:
            self._hist_head.destroy()
        if getattr(self, "_hist_main", None) is not None:
            self._hist_main.destroy()

        hh = tk.Frame(self.tab_history, bg=C.CARD)
        hh.pack(fill="x", padx=14, pady=(12, 6))
        self._hist_head = hh
        tk.Label(hh, text="📁 历史回顾", font=F_H, bg=C.CARD, fg=C.TEAL).pack(side="left")
        self.lbl_history_stat = tk.Label(hh, text="", font=F_SMALL, bg=C.CARD, fg=C.SUB)
        self.lbl_history_stat.pack(side="left", padx=10, pady=(4, 0))
        self.btn_hist_backup = self._btn(hh, "💾 备份到桌面", self._backup_history)
        self.btn_hist_backup.pack(side="right", padx=4)
        self.btn_hist_open = self._btn(hh, "📂 打开归档文件夹", self._open_history_folder)
        self.btn_hist_open.pack(side="right", padx=4)

        hm = tk.Frame(self.tab_history, bg=C.CARD)
        hm.pack(fill="both", expand=True, padx=14, pady=(0, 12))
        self._hist_main = hm
        self.hist_listbox = tk.Listbox(
            hm, width=18, font=F_SMALL, bg=C.CARD, fg=C.INK, relief="solid", bd=1,
            highlightthickness=0, selectbackground=C.TEAL, selectforeground=C.ON_ACCENT,
        )
        self.hist_listbox.pack(side="left", fill="y")
        self.hist_text = tk.Text(
            hm, wrap="word", font=F_BASE, bg=C.CARD, fg=C.INK, bd=0,
            highlightthickness=0, padx=16, pady=12, state="disabled",
        )
        self.hist_text.pack(side="left", fill="both", expand=True, padx=(8, 0))
        self._restyle_history_text()
        self.hist_listbox.bind("<<ListboxSelect>>", self._on_history_select)

    def _restyle_history_text(self):
        """历史回顾正文的 tag 配色（切主题时重新配置一次即可，不用重建控件）。"""
        t = getattr(self, "hist_text", None)
        if t is None:
            return
        t.configure(bg=C.CARD, fg=C.INK)
        for name, kw in (
            ("date", dict(font=("Microsoft YaHei UI", 14, "bold"), foreground=C.TEAL, spacing1=6, spacing3=14)),
            ("h", dict(font=("Microsoft YaHei UI", 12, "bold"), foreground=C.INK, spacing1=8, spacing3=6)),
            ("sub", dict(font=F_SMALL, foreground=C.SUB, spacing3=8)),
            ("body", dict(font=F_BASE, foreground=C.INK, spacing1=3, spacing3=7)),
            ("lab", dict(font=("Microsoft YaHei UI", 10, "bold"), foreground=C.MUTED_BLUE, spacing1=10, spacing3=6)),
            ("item", dict(font=F_SMALL, foreground=C.INK, spacing1=3, spacing3=6)),
            ("sep", dict(font=F_TINY, foreground=C.LINE, spacing1=12, spacing3=2)),
        ):
            t.tag_configure(name, **kw)
        lb = getattr(self, "hist_listbox", None)
        if lb is not None:
            lb.configure(bg=C.CARD, fg=C.INK, selectbackground=C.TEAL, selectforeground=C.ON_ACCENT)

    def _restyle_chrome(self):
        """切换主题时刷新窗口本体、各 tab 容器与 ScrollFrame 的底色。"""
        self.root.configure(bg=C.BG)
        for name in ("tab_news", "tab_funds", "tab_lesson", "tab_weekly",
                     "tab_think", "tab_express", "tab_terms", "tab_history"):
            w = getattr(self, name, None)
            if w is not None:
                w.configure(bg=C.CARD)
        for name in ("scroll_news", "scroll_funds", "scroll_lesson", "scroll_weekly",
                     "scroll_think", "scroll_express", "scroll_terms"):
            sf = getattr(self, name, None)
            if sf is not None:
                sf.configure(bg=C.CARD)
                sf.canvas.configure(bg=C.CARD)
                sf.inner.configure(bg=C.CARD)
        # 历史页里的两个容器框架
        for holder in (getattr(self, "_hist_head", None), getattr(self, "_hist_main", None)):
            if holder is not None:
                holder.configure(bg=C.CARD)

    # ------------------------------------------------------------ 数据
    def _load_cache(self):
        try:
            import json
            with open(config.TODAY_PATH, encoding="utf-8") as f:
                return json.load(f)
        except Exception:  # noqa: BLE001
            return None

    def _set_status(self, msg):
        self.lbl_status.configure(text=msg)

    def _toggle_top(self):
        self.root.attributes("-topmost", self.var_top.get())

    def _start_refresh(self):
        if self._refreshing:
            return
        self._refreshing = True
        self.btn_refresh.configure(state="disabled", text="刷新中…")
        self._set_status("正在抓取最新数据…")

        def work():
            err = None
            payload = None
            try:
                payload, _ = generate.generate_today(force=True)
            except Exception as e:  # noqa: BLE001
                err = e
            self.root.after(0, self._on_refreshed, payload, err)

        threading.Thread(target=work, daemon=True).start()

    def _start_ai_regen(self, modules, source="ai"):
        """只重新生成内容模块（思辨/表达），不重抓新闻基金。

        source="ai"：AI 命题；source="web"：抓当日网络热点再做内容。
        """
        if self._refreshing:
            return
        self._refreshing = True
        self.btn_refresh.configure(state="disabled", text="生成中…")
        self._set_status("正在抓取网络热点…" if source == "web" else "AI 正在生成新内容…")

        def work():
            payload, changed, error = None, [], ""
            try:
                payload, changed, error = generate.regenerate_ai_modules(modules, source=source)
            except Exception as e:  # noqa: BLE001
                error = str(e)
            self.root.after(0, self._on_ai_regen_done, payload, changed, error)

        threading.Thread(target=work, daemon=True).start()

    def _on_ai_regen_done(self, payload, changed, error):
        self._refreshing = False
        self.btn_refresh.configure(state="normal", text="刷新数据")
        if payload:
            self.data = payload
            self._thinking_random = False
            self._expression_random = False
            self.render_all()
        if changed:
            msg = "已更新：" + "、".join(changed)
            if error:
                msg += "（" + error + "）"
            self._set_status(msg)
        else:
            self._set_status(error or "AI 生成失败，仍显示静态库内容")

    def _on_refreshed(self, payload, err):
        self._refreshing = False
        self.btn_refresh.configure(state="normal", text="刷新数据")
        if payload:
            self.data = payload
            # 刷新/更新后重置随机标记：优先显示新的 AI 内容（换一条/换一组是临时显示）
            self._random_mode = False
            self._thinking_random = False
            self._expression_random = False
            self.render_all()
            self._set_status("更新于 " + (payload.get("generated_at", "") or "")[11:16])
        else:
            self._set_status("刷新失败，当前显示缓存数据")

    # ------------------------------------------------------------ 渲染
    def render_all(self):
        today = dt.date.today()
        if self.data and self.data.get("date") == today.isoformat():
            d = today
            self.lbl_date.configure(
                text="{0}月{1}日 {2}".format(d.month, d.day, self.data.get("weekday", ""))
            )
        else:
            d = today
            self.lbl_date.configure(text="{0}月{1}日".format(d.month, d.day))
        gen = (self.data or {}).get("generated_at", "") or ""
        self.lbl_foot.configure(
            text="数据来源：央视网《新闻联播》· 天天基金/腾讯行情 · 本地知识库    缓存生成于 {0}    自选基金请编辑 config.json".format(
                gen[:16] if gen else "--"
            )
        )
        self.render_news()
        self.render_funds()
        self.render_lesson()
        self.render_weekly()
        self.render_thinking()
        self.render_expression()
        self.render_terms()
        self.render_history()

    # ------------------------------------------------------------ 主题
    def _open_theme_menu(self):
        """顶栏「🎨 主题」的下拉菜单。"""
        m = tk.Menu(
            self.root, tearoff=0, bg=C.CARD, fg=C.INK, font=F_SMALL,
            activebackground=C.CARD_HOVER, activeforeground=C.ACCENT,
        )
        cur = current_theme()
        for key, label in THEME_NAMES.items():
            m.add_command(
                label=label + ("  ✓" if key == cur else ""),
                command=lambda k=key: self._apply_theme(k),
            )
        b = self.btn_theme
        m.tk_popup(b.winfo_rootx(), b.winfo_rooty() + b.winfo_height())

    def _apply_theme(self, name):
        """切换主题：改配色 → 存配置 → 重建界面骨架 → 重渲所有板块。"""
        set_theme(name)
        config.save_config({"theme": name})
        self._build_style()          # ttk 控件（标签页/滚动条）
        self._restyle_chrome()       # 窗口底色 + 各 tab 容器 + 滚动区
        self._build_topbar()         # 顶栏（含主题按钮本身）
        self._build_statusbar()      # 状态栏
        self._build_history_pane()   # 历史页（含正文 tag 配色）
        self.render_all()            # 8 个板块内容全部重渲
        self._set_status("已切换到「{0}」主题".format(THEME_NAMES.get(name, name)))

    # ============ 新闻 ============
def main(smoke=False):
    # 打包版首次运行：把老版本（源码目录）的历史归档/配置迁移过来
    try:
        config.migrate_legacy_data()
    except Exception:  # noqa: BLE001
        pass
    root = tk.Tk()
    MorningApp(root, smoke=smoke)
    root.mainloop()
