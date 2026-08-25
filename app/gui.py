# -*- coding: utf-8 -*-
"""每日晨报 tkinter 界面（精致版）：新闻联播 / 基金投资 / 每日一课。"""
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

from . import config, fetch, generate, knowledge

# ---------------- 配色（莫兰迪，高对比版） ----------------
BG = "#F4F1E8"
CARD = "#FFFFFF"
CARD_HOVER = "#FBF5E9"
INK = "#2A2722"
SUB = "#6E685C"
LINE = "#DCD4C2"
ACCENT = "#9A4A3F"
ACCENT_D = "#7E3B32"
TEAL = "#33545C"
GOLD = "#A98E4A"
UP = "#B03A2E"
DOWN = "#1E7A5A"
FLAT = "#5C584E"
UP_TINT = "#F4DCD6"
DOWN_TINT = "#D8E9E0"

GROUP_COLORS = {
    "时政": ACCENT,
    "国内": TEAL,
    "国际": "#6B5B8E",
    "财经科技": GOLD,
    "快讯": "#7A6A3A",
    "其他": SUB,
}
CAT_COLORS = {
    "周易": "#9A4A3F",
    "哲学": "#33545C",
    "心理学": "#A07A2E",
    "美学": "#6B4E8E",
    "文学": "#8A5A2B",
    "音乐": "#4A7A8A",
    "毛选": "#B03A2E",
    "摄影": "#2E6B9E",
    "经济学": "#5B7A3A",
    "历史": "#7A5C3E",
    "茶艺": "#5A6B4A",
    "礼仪": "#7A6A8E",
    "官场文化": "#8C6B3F",
}
WEEKLY_COLORS = {
    "金融": "#A07A2E",
    "AI科技": "#4A7A8A",
    "医学": "#2E6B4F",
    "科学": "#6B4E8E",
    "国际局势": "#33545C",
    "民生": "#8A5A2B",
}
# 名词跳转平台
PLATFORMS = [
    ("百度百科", "https://baike.baidu.com/item/{q}"),
    ("哔哩哔哩", "https://search.bilibili.com/all?keyword={q}"),
    ("知乎", "https://www.zhihu.com/search?type=content&q={q}"),
    ("微信搜一搜", "https://weixin.sogou.com/weixin?type=2&query={q}"),
]

F_TITLE = ("Microsoft YaHei UI", 16, "bold")
F_H = ("Microsoft YaHei UI", 13, "bold")
F_MID = ("Microsoft YaHei UI", 11, "bold")
F_BASE = ("Microsoft YaHei UI", 11)
F_SMALL = ("Microsoft YaHei UI", 10)
F_TINY = ("Microsoft YaHei UI", 9)
F_NUM = ("Consolas", 12, "bold")


def rounded_rect(c, x1, y1, x2, y2, r, **kw):
    pts = [
        x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
        x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
        x1, y2, x1, y2 - r, x1, y1 + r, x1, y1,
    ]
    return c.create_polygon(pts, smooth=True, **kw)


class Card(tk.Canvas):
    """圆角卡片：承载子内容（body 铺满卡片，内容真正左对齐），随尺寸变化自动重绘。"""

    def __init__(self, parent, w, h, radius=14, fill=CARD, outline=LINE, bg=BG):
        super().__init__(parent, width=w, height=h, bg=bg, highlightthickness=0, bd=0)
        self._fill = fill
        self._radius = radius
        self._outline = outline
        self._shape = None
        self.body = tk.Frame(self, bg=fill)
        self._win = self.create_window(
            w // 2, h // 2, window=self.body, width=max(8, w - 4), height=max(8, h - 4)
        )
        self.bind("<Configure>", self._resize)

    def _redraw(self, w, h):
        if self._shape is not None:
            self.delete(self._shape)
        r = max(4, min(self._radius, w // 2, h // 2))
        self._shape = rounded_rect(self, 2, 2, max(4, w - 2), max(4, h - 2), r,
                                   fill=self._fill, outline=self._outline, width=1)
        self.coords(self._win, w // 2, h // 2)
        self.itemconfig(self._win, width=max(8, w - 4), height=max(8, h - 4))

    def _resize(self, e):
        self._redraw(e.width, e.height)

    def wire(self, command=None):
        targets = [self, self.body]
        for t in targets:
            if command:
                t.configure(cursor="hand2")
                t.bind("<Button-1>", lambda e: command())
            t.bind("<Enter>", lambda e: self._hover(True))
            t.bind("<Leave>", lambda e: self._hover(False))

    def _hover(self, on):
        if self._shape is not None:
            self.itemconfig(self._shape, outline=(ACCENT if on else self._outline), width=(1.6 if on else 1))


class ScrollFrame(tk.Frame):
    """可滚动画布容器。"""

    def __init__(self, parent, bg=CARD):
        super().__init__(parent, bg=bg)
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0)
        self.sb = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = tk.Frame(self.canvas, bg=bg)
        self._win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=self.sb.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.sb.pack(side="right", fill="y")
        self.inner.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfig(self._win, width=e.width))
        for w in (self.canvas, self.sb, self.inner):
            w.bind("<MouseWheel>", self._on_wheel)

    def _on_wheel(self, e):
        self.canvas.yview_scroll(int(-e.delta / 120), "units")


def sparkline(c, w, h, values, pad=4):
    """画迷你走势图（面积+折线）。返回 None 若数据不足。"""
    vals = [v for v in values if isinstance(v, (int, float)) and v > 0]
    if len(vals) < 2:
        return
    color = UP if vals[-1] >= vals[0] else DOWN
    vmin, vmax = min(vals), max(vals)
    rng = (vmax - vmin) or 1.0
    step = (w - 2 * pad) / (len(vals) - 1)
    pts = []
    for i, v in enumerate(vals):
        x = pad + i * step
        y = h - pad - (v - vmin) / rng * (h - 2 * pad)
        pts.append((x, y))
    area = [pts[0][0], h - 1]
    for p in pts:
        area += [p[0], p[1]]
    area += [pts[-1][0], h - 1]
    c.create_polygon(area, fill=(UP_TINT if color == UP else DOWN_TINT), outline="")
    coords = [c for p in pts for c in p]
    c.create_line(*coords, fill=color, width=1.6, smooth=True)


def classify_news(title):
    t = title
    if any(k in t for k in ("联播快讯", "一组简讯", "简讯")):
        return "快讯"
    if any(k in t for k in (
        "习近平", "李强", "赵乐际", "王沪宁", "蔡奇", "丁薛祥", "李希", "韩正",
        "国务院", "人大常委会", "全国政协", "政治局", "中央", "总理", "人大", "政协",
        "会见", "主持", "出席", "讲话", "慰问", "纪念", "考察",
    )):
        return "时政"
    if any(k in t for k in (
        "俄", "俄罗斯", "俄方", "美国", "美方", "法国", "法方", "英国", "英方", "德国", "德方",
        "日本", "日方", "韩国", "韩方", "伊朗", "以色列", "巴以", "乌克兰", "欧盟", "欧洲",
        "联合国", "北约", "国际", "全球", "世卫", "中东", "印度", "沙特", "土耳其", "巴西",
        "澳大利亚", "西班牙", "意大利", "瑞典", "挪威", "波兰", "朝鲜", "叙利亚", "黎巴嫩",
        "巴基斯坦", "阿富汗", "非洲", "拉美", "加拿大", "墨西哥", "阿根廷", "埃及", "利比亚",
        "苏丹", "尼日利亚", "南非", "越南", "泰国", "印尼", "马来西亚", "新加坡", "菲律宾",
        "缅甸", "老挝", "柬埔寨", "蒙古", "哈萨克斯坦", "白俄罗斯", "塞尔维亚", "匈牙利",
        "希腊", "葡萄牙", "爱尔兰", "比利时", "荷兰", "瑞士", "奥地利", "丹麦", "芬兰", "捷克",
        "罗马尼亚", "保加利亚", "克罗地亚", "阿联酋", "卡塔尔", "科威特", "约旦", "伊拉克",
        "也门", "摩洛哥", "突尼斯",
    )):
        return "国际"
    if any(k in t for k in (
        "经济", "财政", "央行", "金融", "市场", "产业", "科技", "AI", "人工智能", "数字",
        "出口", "投资", "消费", "企业", "能源", "粮食", "农业", "基建", "贸易", "工业",
        "制造", "服务", "创新", "研发", "工程", "项目", "建设", "改革", "开放", "政策",
        "税收", "物价", "就业", "收入", "乡村", "生态", "环保", "低碳", "新能源", "半导体",
        "芯片", "互联网", "数据", "平台", "航天", "卫星", "高铁", "通信",
    )):
        return "财经科技"
    return "国内"


class MorningApp:
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
        self.root.configure(bg=BG)
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
        if not self.data or self.data.get("date") != today_iso or news_stale:
            self._set_status("正在更新晨报数据…")
            self._start_refresh()

    # ------------------------------------------------------------ 构建
    def _build_style(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TNotebook", background=BG, borderwidth=0)
        style.configure("TNotebook.Tab", font=F_SMALL, padding=(20, 8), background="#E9E3D5", foreground=INK)
        style.map("TNotebook.Tab", background=[("selected", CARD)], foreground=[("selected", ACCENT)])
        style.configure("Vertical.TScrollbar", background="#D8D1C2", troughcolor=BG, bordercolor=BG, arrowcolor=SUB)

    def _btn(self, parent, text, cmd, **kw):
        return tk.Button(
            parent, text=text, command=cmd, font=F_SMALL, bg=CARD, fg=INK,
            activebackground=CARD_HOVER, activeforeground=ACCENT, relief="flat", bd=1,
            highlightthickness=1, highlightbackground=LINE, highlightcolor=LINE,
            padx=12, pady=3, cursor="hand2", **kw,
        )

    def _chip(self, parent, text, color, font=None, fg="#FFFFFF"):
        return tk.Label(
            parent, text=text, font=font or F_TINY, bg=color, fg=fg, padx=7, pady=1,
        )

    def _build_topbar(self):
        bar = tk.Frame(self.root, bg=BG)
        bar.pack(fill="x", padx=18, pady=(14, 8))

        logo = Card(bar, 44, 44, radius=12, fill=ACCENT, outline=ACCENT)
        logo.pack(side="left")
        tk.Label(logo.body, text="晨", font=("Microsoft YaHei UI", 17, "bold"), bg=ACCENT, fg="#FFFFFF").pack(
            padx=13, pady=8
        )

        tk.Label(bar, text="每日晨报", font=F_TITLE, bg=BG, fg=INK).pack(side="left", padx=(12, 0))
        tk.Label(bar, text="MorningBoard · 每天 30 秒看世界", font=F_SMALL, bg=BG, fg=SUB).pack(
            side="left", padx=10, pady=(6, 0)
        )

        self.lbl_status = tk.Label(bar, text="", font=F_SMALL, bg=BG, fg=SUB)
        self.lbl_status.pack(side="right", padx=(0, 12))

        self.btn_web = self._btn(bar, "打开央视网", lambda: webbrowser.open("https://tv.cctv.com/lm/xwlb/"))
        self.btn_web.pack(side="right", padx=4)

        self.var_top = tk.BooleanVar(value=False)
        tk.Checkbutton(
            bar, text="置顶", variable=self.var_top, command=self._toggle_top,
            font=F_SMALL, bg=BG, fg=INK, activebackground=BG, selectcolor=CARD,
        ).pack(side="right", padx=4)
        self.root.attributes("-topmost", self.var_top.get())

        self.btn_refresh = self._btn(bar, "刷新数据", self._start_refresh)
        self.btn_refresh.pack(side="right", padx=4)

        self.lbl_date = tk.Label(bar, text="", font=F_MID, bg=BG, fg=ACCENT)
        self.lbl_date.pack(side="right", padx=12)

    def _build_statusbar(self):
        sb = tk.Frame(self.root, bg=BG)
        sb.pack(fill="x", padx=20, pady=(0, 8))
        self.lbl_foot = tk.Label(
            sb, text="", font=F_TINY, bg=BG, fg=SUB, justify="left", anchor="w",
        )
        self.lbl_foot.pack(side="left")

    def _build_notebook(self):
        self.nb = ttk.Notebook(self.root)
        self.nb.pack(fill="both", expand=True, padx=12, pady=(2, 6))

        self.tab_news = tk.Frame(self.nb, bg=CARD)
        self.tab_funds = tk.Frame(self.nb, bg=CARD)
        self.tab_lesson = tk.Frame(self.nb, bg=CARD)
        self.tab_weekly = tk.Frame(self.nb, bg=CARD)
        self.tab_think = tk.Frame(self.nb, bg=CARD)
        self.tab_express = tk.Frame(self.nb, bg=CARD)
        self.tab_terms = tk.Frame(self.nb, bg=CARD)
        self.tab_history = tk.Frame(self.nb, bg=CARD)
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

        # 历史回顾 tab：左日期列表 + 右内容（自带滚动，不用 ScrollFrame）
        hh = tk.Frame(self.tab_history, bg=CARD)
        hh.pack(fill="x", padx=14, pady=(12, 6))
        tk.Label(hh, text="📁 历史回顾", font=F_H, bg=CARD, fg=TEAL).pack(side="left")
        self.lbl_history_stat = tk.Label(hh, text="", font=F_SMALL, bg=CARD, fg=SUB)
        self.lbl_history_stat.pack(side="left", padx=10, pady=(4, 0))
        self.btn_hist_backup = self._btn(hh, "💾 备份到桌面", self._backup_history)
        self.btn_hist_backup.pack(side="right", padx=4)
        self.btn_hist_open = self._btn(hh, "📂 打开归档文件夹", self._open_history_folder)
        self.btn_hist_open.pack(side="right", padx=4)
        hm = tk.Frame(self.tab_history, bg=CARD)
        hm.pack(fill="both", expand=True, padx=14, pady=(0, 12))
        self.hist_listbox = tk.Listbox(
            hm, width=18, font=F_SMALL, bg=CARD, fg=INK, relief="solid", bd=1,
            highlightthickness=0, selectbackground=TEAL, selectforeground="#FFFFFF",
        )
        self.hist_listbox.pack(side="left", fill="y")
        self.hist_text = tk.Text(
            hm, wrap="word", font=F_BASE, bg=CARD, fg=INK, bd=0,
            highlightthickness=0, padx=16, pady=12, state="disabled",
        )
        self.hist_text.pack(side="left", fill="both", expand=True, padx=(8, 0))
        self.hist_text.tag_configure("date", font=("Microsoft YaHei UI", 14, "bold"), foreground=TEAL, spacing1=6, spacing3=14)
        self.hist_text.tag_configure("h", font=("Microsoft YaHei UI", 12, "bold"), foreground=INK, spacing1=8, spacing3=6)
        self.hist_text.tag_configure("sub", font=F_SMALL, foreground=SUB, spacing3=8)
        self.hist_text.tag_configure("body", font=F_BASE, foreground=INK, spacing1=3, spacing3=7)
        self.hist_text.tag_configure("lab", font=("Microsoft YaHei UI", 10, "bold"), foreground="#4A6B8A", spacing1=10, spacing3=6)
        self.hist_text.tag_configure("item", font=F_SMALL, foreground=INK, spacing1=3, spacing3=6)
        self.hist_text.tag_configure("sep", font=F_TINY, foreground=LINE, spacing1=12, spacing3=2)
        self.hist_listbox.bind("<<ListboxSelect>>", self._on_history_select)

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

    def _on_refreshed(self, payload, err):
        self._refreshing = False
        self.btn_refresh.configure(state="normal", text="刷新数据")
        if payload:
            self.data = payload
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

    # ============ 新闻 ============
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
        tone_color = {"普涨": UP, "普跌": DOWN}.get(tone, FLAT)
        banner = Card(inner, 1000, self._h(52), radius=12, fill="#FBF7EE", outline=LINE)
        banner.pack(fill="x", pady=(2, 10))
        self._chip(banner.body, " 今日市场 ", tone_color, fg="#FFFFFF").pack(side="left", padx=(18, 10), pady=13)
        tk.Label(
            banner.body, text="{0} · {1} 个指数：{2} 涨 {3} 跌".format(tone, len(pcts), ups, downs),
            font=F_BASE, bg="#FBF7EE", fg=INK,
        ).pack(side="left", pady=12)
        if funds.get("index_error"):
            tk.Label(banner.body, text="（" + funds["index_error"] + "）", font=F_TINY, bg="#FBF7EE", fg=SUB).pack(
                side="left", pady=13
            )

        # 指数卡片 4x2（点击跳腾讯行情）
        cfg_indices = config.load_config().get("indices", [])
        grid = tk.Frame(inner, bg=CARD)
        grid.pack(fill="x")
        for i in range(4):
            grid.grid_columnconfigure(i, weight=1, uniform="idx")
        for i, it in enumerate(indices[:8]):
            card = Card(grid, 1000, self._h(94), radius=12)
            card.grid(row=i // 4, column=i % 4, sticky="we", padx=4, pady=4)
            bw = card.body
            tk.Label(bw, text=it.get("name", ""), font=F_SMALL, bg=CARD, fg=SUB).pack(anchor="w", padx=(16, 0), pady=(8, 0))
            pr = it.get("price")
            pr_s = "--" if pr in (None, "-") else "{0:,.2f}".format(float(pr))
            tk.Label(bw, text=pr_s, font=F_NUM, bg=CARD, fg=INK).pack(anchor="w", padx=(16, 0), pady=(0, 0))
            pct = it.get("pct")
            chg = it.get("chg")
            arrow = "▲" if isinstance(pct, (int, float)) and pct > 0 else ("▼" if isinstance(pct, (int, float)) and pct < 0 else "·")
            chg_s = "--" if chg in (None, "-") else "{0:+,.2f}".format(float(chg))
            tk.Label(
                bw, text=" {0} {1}  {2}".format(arrow, self._fmt_pct(pct), chg_s),
                font=F_MID, bg=CARD, fg=self._pct_color(pct),
            ).pack(anchor="w", padx=(16, 0))
            secid = cfg_indices[i]["secid"] if i < len(cfg_indices) else ""
            tcode = fetch._to_tencent_code(secid) if secid else ""
            self._bind_click_tree(bw, lambda t=tcode: webbrowser.open("https://gu.qq.com/" + t))
        tk.Label(inner, text="🖱 点击指数卡跳转腾讯行情", font=F_TINY, bg=CARD, fg=SUB).pack(anchor="w", pady=(2, 0))

        # 涨幅榜
        top = funds.get("top_gainers") or []
        if top:
            tg = tk.Frame(inner, bg=CARD)
            tg.pack(fill="x", pady=(12, 6))
            tk.Label(tg, text="🔥 今日基金涨幅榜", font=F_MID, bg=CARD, fg=ACCENT).pack(side="left")
            tk.Label(tg, text="  （近1个交易日）", font=F_TINY, bg=CARD, fg=SUB).pack(side="left", pady=(2, 0))
            chips = tk.Frame(inner, bg=CARD)
            chips.pack(fill="x")
            for it in top[:5]:
                c = tk.Frame(chips, bg="#FBF2EC")
                c.pack(side="left", padx=(0, 8), pady=2)
                tk.Label(c, text=" " + it.get("name", ""), font=F_SMALL, bg="#FBF2EC", fg=INK).pack(side="left", padx=(8, 4), pady=3)
                tk.Label(c, text=self._fmt_pct(it.get("day")), font=F_MID, bg="#FBF2EC", fg=self._pct_color(it.get("day"))).pack(
                    side="left", padx=(0, 8), pady=3
                )
                self._bind_click_tree(
                    c, lambda code=it.get("code", ""): webbrowser.open("https://fund.eastmoney.com/{0}.html".format(code))
                )

        # 自选基金表头
        fh = tk.Frame(inner, bg=CARD)
        fh.pack(fill="x", pady=(14, 4))
        tk.Label(fh, text="自选基金", font=F_H, bg=CARD, fg=TEAL).pack(side="left")
        tk.Label(fh, text="  点击任意行跳转天天基金详情", font=F_TINY, bg=CARD, fg=SUB).pack(side="left", pady=(4, 0))
        heads = ["基金", "净值走势", "最新净值", "日期", "日涨跌", "近1周", "近1月", "近3月"]
        hf = tk.Frame(inner, bg=CARD)
        hf.pack(fill="x", pady=(2, 2))
        for i, htxt in enumerate(heads):
            tk.Label(hf, text=htxt, font=F_TINY, bg=CARD, fg=SUB, width=11 if i else 22, anchor="w").grid(
                row=0, column=i, sticky="w", padx=6
            )

        # 基金行
        errs = []
        for f in funds.get("watchlist") or []:
            if f.get("error"):
                errs.append("{0}({1})".format(f.get("code"), f.get("error")))
            row = tk.Frame(inner, bg=CARD, highlightbackground=LINE, highlightthickness=1)
            row.pack(fill="x", pady=3)

            left = tk.Frame(row, bg=CARD)
            left.grid(row=0, column=0, sticky="w", padx=(12, 6), pady=8)
            left.grid_columnconfigure(0, weight=1)
            tk.Label(left, text=f.get("name", f.get("code", "")), font=F_MID, bg=CARD, fg=INK).pack(anchor="w")
            tk.Label(left, text=f.get("code", ""), font=F_TINY, bg=CARD, fg=SUB).pack(anchor="w")

            trend = f.get("trend") or []
            if len(trend) >= 2:
                sp = tk.Canvas(row, width=96, height=40, bg=CARD, highlightthickness=0, bd=0)
                sp.grid(row=0, column=1, padx=6)
                sparkline(sp, 96, 40, [v for _, v in trend])
            else:
                tk.Label(row, text="暂无走势", font=F_TINY, bg=CARD, fg=SUB).grid(row=0, column=1, padx=6)

            nav = f.get("nav")
            nav_s = "--" if nav in (None, 0) else "{0:.4f}".format(float(nav))
            tk.Label(row, text=nav_s, font=F_NUM, bg=CARD, fg=INK).grid(row=0, column=2, sticky="w", padx=6)
            tk.Label(row, text=f.get("nav_date", "--"), font=F_TINY, bg=CARD, fg=SUB).grid(row=0, column=3, sticky="w", padx=6)
            for ci, key in ((4, "day_chg"), (5, "w1"), (6, "m1"), (7, "m3")):
                v = f.get(key)
                tk.Label(row, text=self._fmt_pct(v), font=F_MID, bg=CARD, fg=self._pct_color(v)).grid(
                    row=0, column=ci, sticky="w", padx=6
                )
            self._bind_click_tree(
                row,
                lambda code=f.get("code", ""): webbrowser.open("https://fund.eastmoney.com/{0}.html".format(code)),
            )

        if errs:
            tk.Label(
                inner, text="提示：部分基金数据获取失败（{0}），稍后点右上角\"刷新数据\"重试。".format(errs[0]),
                font=F_TINY, bg=CARD, fg=SUB,
            ).pack(anchor="w", pady=6)

    # ============ 每日一课 ============
    def render_lesson(self):
        inner = self.scroll_lesson.inner
        for w in inner.winfo_children():
            w.destroy()
        if not self.data or not self.data.get("lesson"):
            return
        plan = self.data["lesson"]

        # 控制条
        ctl = tk.Frame(inner, bg=CARD)
        ctl.pack(fill="x", pady=(2, 8))
        self.lbl_lesson_progress = tk.Label(ctl, text="", font=F_SMALL, bg=CARD, fg=SUB)
        self.lbl_lesson_progress.pack(side="left", padx=4)
        self.btn_random = self._btn(ctl, "🎲 换一条", self._random_lesson)
        self.btn_random.pack(side="right", padx=4)
        self.btn_history = self._btn(ctl, "📁 历史回顾", self._open_history)
        self.btn_history.pack(side="right", padx=4)
        self.btn_today = self._btn(ctl, "回到今日课程", self._back_to_today)
        self.btn_today.pack(side="right", padx=4)
        tk.Label(ctl, text="每日一课", font=F_H, bg=CARD, fg=INK).pack(side="left")

        # 主课卡片
        self._main_card = Card(inner, 1000, self._h(320), radius=16)
        self._main_card.pack(fill="x", pady=(0, 10))
        self._render_main_body(plan.get("main"))

        # 金句
        quote = plan.get("quote")
        if quote:
            qc = Card(inner, 1000, self._h(64), radius=12, fill="#FBF5E7", outline="#E4D5AC")
            qc.pack(fill="x", pady=(0, 10))
            tk.Label(qc.body, text="✒ 每日金句", font=F_TINY, bg="#FBF5E7", fg=GOLD).pack(side="left", padx=(16, 8), pady=20)
            tk.Label(
                qc.body, text="“{0}”".format(quote.get("text", "")), font=("Microsoft YaHei UI", 10, "bold"),
                bg="#FBF5E7", fg="#7A6530", wraplength=760, justify="left",
            ).pack(side="left", padx=(0, 8), pady=18)
            tk.Label(qc.body, text="— " + quote.get("author", ""), font=F_SMALL, bg="#FBF5E7", fg=SUB).pack(
                side="left", pady=20
            )

        # 小卡
        tk.Label(inner, text="今日小卡 · 点击任意一张展开阅读", font=F_SMALL, bg=CARD, fg=SUB).pack(anchor="w", pady=(2, 4))
        cards = plan.get("cards") or []
        if cards:
            cg = tk.Frame(inner, bg=CARD)
            cg.pack(fill="x")
            for i in range(3):
                cg.grid_columnconfigure(i, weight=1, uniform="card")
            for i, it in enumerate(cards):
                self._render_mini_card(cg, i, it)

    def _render_main_body(self, item):
        for w in self._main_card.body.winfo_children():
            w.destroy()
        if not item:
            return
        self._cur_item = item
        cat = item.get("cat", "")
        color = CAT_COLORS.get(cat, TEAL)
        body = self._main_card.body

        # 模块1：分类徽章 + 进度
        top = tk.Frame(body, bg=CARD)
        top.pack(fill="x", padx=20, pady=(14, 2))
        self._chip(top, " " + cat + " ", color).pack(side="left")
        self.lbl_lesson_progress.configure(
            text="第 {0}/{1} 课".format(item.get("idx", 0) + 1, item.get("total", 0))
        )

        # 模块2：标题 + 一句话概括
        tk.Label(
            body, text=item.get("title", ""), font=("Microsoft YaHei UI", 15, "bold"),
            bg=CARD, fg=color, anchor="w", justify="left",
        ).pack(fill="x", padx=20, pady=(8, 0))
        tk.Label(
            body, text=item.get("sub", ""), font=F_SMALL, bg=CARD, fg=SUB, anchor="w", justify="left",
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
                body, wrap="word", font=F_BASE, fg=INK, bg=CARD, bd=0,
                highlightthickness=0, height=total_lines + 1,
                spacing1=5, spacing3=7, padx=6, pady=2,
            )
            btext.pack(fill="x", padx=16, pady=2)
            btext.tag_configure("link", foreground="#1F5FA8", underline=True)
            full_text = "\n\n".join(main_paras) + "\n\n"
            btext.insert("1.0", full_text)
            for s, e, t in self._find_terms(full_text, knowledge.load_terms()):
                btext.tag_add("link", "1.0 + {0} chars".format(s), "1.0 + {0} chars".format(e))
            btext.tag_bind("link", "<Button-1>", self._on_text_link)
            btext.tag_bind("link", "<Enter>", lambda e: btext.configure(cursor="hand2"))
            btext.tag_bind("link", "<Leave>", lambda e: btext.configure(cursor=""))
            btext.configure(state="disabled")
        if action_paras:
            ac = tk.Frame(body, bg="#FBF5E7", highlightbackground="#E4D5AC", highlightthickness=1)
            ac.pack(fill="x", padx=20, pady=(4, 2))
            tk.Label(ac, text="💡 今日行动", font=F_SMALL, bg="#FBF5E7", fg=GOLD).pack(anchor="w", padx=14, pady=(8, 2))
            for p in action_paras:
                tk.Label(
                    ac, text=p, font=F_BASE, bg="#FBF5E7", fg="#6B5B2E",
                    anchor="w", justify="left", wraplength=900,
                ).pack(fill="x", padx=14, pady=(0, 8))

        # 模块5：延伸学习
        links = item.get("links") or []
        if links:
            lf = tk.Frame(body, bg=CARD)
            lf.pack(fill="x", padx=20, pady=(6, 2))
            tk.Label(lf, text="延伸学习：", font=F_SMALL, bg=CARD, fg=GOLD).pack(side="left", pady=1)
            for term in links[:6]:
                chip = tk.Label(
                    lf, text=" " + term + " ", font=F_SMALL, bg="#F3EBD9", fg="#7A6530",
                    padx=7, pady=1, cursor="hand2",
                )
                chip.pack(side="left", padx=(0, 6), pady=1)
                chip.bind("<Button-1>", lambda e, t=term: self._link_menu(e, t))
            tk.Label(lf, text="点击名词→选平台", font=F_TINY, bg=CARD, fg=SUB).pack(side="left", padx=(2, 0))

        # 进度条 + 同类课程导航
        total = item.get("total", 0) or 1
        idx = item.get("idx", 0)
        pbar = tk.Canvas(body, width=200, height=10, bg=CARD, highlightthickness=0, bd=0)
        pbar.pack(anchor="w", padx=20, pady=(10, 6))
        rounded_rect(pbar, 1, 1, 200, 10, 5, fill=LINE, outline="")
        w_fill = max(6, int(200 * (idx + 1) / total))
        rounded_rect(pbar, 1, 1, w_fill, 10, 5, fill=color, outline="")

        nav = tk.Frame(body, bg=CARD)
        nav.pack(fill="x", padx=20, pady=(2, 14))
        tk.Label(nav, text="同类课程连续学", font=F_TINY, bg=CARD, fg=SUB).pack(side="left", pady=(4, 0))
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
        color = CAT_COLORS.get(it.get("cat", ""), TEAL)
        self._chip(card.body, " " + it.get("cat", "") + " ", color).pack(anchor="w", padx=14, pady=(10, 3))
        tk.Label(
            card.body, text=it.get("title", ""), font=F_MID, bg=CARD, fg=INK,
            anchor="w", justify="left", wraplength=300,
        ).pack(fill="x", padx=14, pady=(0, 1))
        tk.Label(
            card.body, text=it.get("sub", ""), font=F_TINY, bg=CARD, fg=SUB,
            anchor="w", justify="left", wraplength=300,
        ).pack(fill="x", padx=14, pady=(0, 1))
        b0 = (it.get("body") or [""])[0]
        if b0:
            snip = b0 if len(b0) <= 40 else b0[:40] + "…"
            tk.Label(
                card.body, text=snip, font=F_TINY, bg=CARD, fg=SUB,
                anchor="w", justify="left", wraplength=300,
            ).pack(fill="x", padx=14, pady=(0, 2))
        tk.Label(
            card.body, text="第 {0}/{1} 课 · 点击展开".format(it.get("idx", 0) + 1, it.get("total", 0)),
            font=F_TINY, bg=CARD, fg=GOLD,
        ).pack(anchor="w", padx=14, pady=(0, 8))

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
        txt.insert(
            "end",
            "{0} {1}".format(data.get("date", ""), data.get("weekday", ""))
            + (" · ✨ AI 生成" if data.get("ai_generated") else " · 静态精选") + "\n",
            "date",
        )
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
    THINK_COLOR = "#B5651D"
    EXPR_COLOR = "#2F6B5A"

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

    def render_thinking(self):
        inner = self.scroll_think.inner
        for w in inner.winfo_children():
            w.destroy()

        head = tk.Frame(inner, bg=CARD)
        head.pack(fill="x", pady=(2, 4))
        tk.Label(head, text="🧠 思辨训练", font=F_H, bg=CARD, fg=self.THINK_COLOR).pack(side="left")
        tk.Label(head, text="思维工具 · 论证对垒 · 谬误识别", font=F_SMALL, bg=CARD, fg=SUB).pack(
            side="left", padx=10, pady=(4, 0)
        )
        self._btn(head, "🎲 换一组", self._thinking_shuffle).pack(side="right")
        tk.Label(
            inner, text="训练方法：先读今日工具 → 用它拆解两道思辨题 → 再识别今日逻辑谬误。答案没有标准，论证过程即收获。",
            font=F_TINY, bg=CARD, fg=SUB,
        ).pack(anchor="w", pady=(0, 6))

        # 1) 今日思维工具
        tool = self._tool_pick()
        if tool:
            card, body = self._lesson_card(inner, " 🧰 今日思维工具 ", self.THINK_COLOR, tool)
            for p in tool.get("b", []):
                tk.Label(
                    body, text=p, font=F_SMALL, bg=CARD, fg=INK,
                    anchor="w", justify="left", wraplength=950,
                ).pack(fill="x", padx=18, pady=4)
            self._link_chips(body, tool.get("links", []), "延伸工具：", self.THINK_COLOR, "#F5EBDD", "#8A5A20")
            self._fit(card, 120)

        # 2) 思辨题：论证对垒
        for i, it in enumerate(self._thinking_pick(2), 1):
            card, body = self._lesson_card(inner, " ⚖️ 思辨题 {0} ".format(i), "#4A6B8A", it)
            for p in it.get("pro", []):
                tk.Label(
                    body, text="✅ 正方：" + p, font=F_SMALL, bg=CARD, fg="#1E7A5A",
                    anchor="w", justify="left", wraplength=950,
                ).pack(fill="x", padx=18, pady=3)
            for p in it.get("con", []):
                tk.Label(
                    body, text="🔻 反方：" + p, font=F_SMALL, bg=CARD, fg="#B03A2E",
                    anchor="w", justify="left", wraplength=950,
                ).pack(fill="x", padx=18, pady=3)
            for p in it.get("ask", []):
                tk.Label(
                    body, text="❓ " + p, font=F_SMALL, bg="#F4F0E6", fg="#7A6530",
                    anchor="w", justify="left", wraplength=950,
                ).pack(fill="x", padx=18, pady=4)
            self._link_chips(body, it.get("links", []), "延伸思考：", self.THINK_COLOR, "#F5EBDD", "#8A5A20")
            self._fit(card, 120)

        # 3) 今日谬误
        fal = self._fallacy_pick()
        if fal:
            card, body = self._lesson_card(inner, " 🚨 今日谬误雷达 ", "#8E3B3B", fal)
            for p in fal.get("b", []):
                tk.Label(
                    body, text=p, font=F_SMALL, bg=CARD, fg=INK,
                    anchor="w", justify="left", wraplength=950,
                ).pack(fill="x", padx=18, pady=4)
            self._link_chips(body, fal.get("links", []), "延伸学习：", "#8E3B3B", "#F5E5E5", "#7A3030")
            self._fit(card, 120)

    # ------------------------------------------------------------ 表达能力
    def _expression_pick(self):
        # 优先用当日 AI 生成的表达课（有则用之；点过"换一课"后回到静态库）
        ai = (self.data or {}).get("expression")
        if ai and not getattr(self, "_expression_random", False):
            return ai
        arr = knowledge.load_expression()
        if not arr:
            return None
        if getattr(self, "_expression_random", False):
            return random.choice(arr)
        return arr[(dt.date.today().timetuple().tm_yday - 1) % len(arr)]

    def _expression_shuffle(self):
        self._expression_random = True
        self.render_expression()

    def render_expression(self):
        inner = self.scroll_express.inner
        for w in inner.winfo_children():
            w.destroy()

        head = tk.Frame(inner, bg=CARD)
        head.pack(fill="x", pady=(2, 4))
        tk.Label(head, text="📣 表达能力", font=F_H, bg=CARD, fg=self.EXPR_COLOR).pack(side="left")
        tk.Label(head, text="结构化表达 · 即兴发言 · 演讲辩论 · 每天一课", font=F_SMALL, bg=CARD, fg=SUB).pack(
            side="left", padx=10, pady=(4, 0)
        )
        self._btn(head, "🎲 换一课", self._expression_shuffle).pack(side="right")
        tk.Label(
            inner, text="每天一课，学完立即用今天的一个场景练一遍——表达是练出来的，不是看会的。",
            font=F_TINY, bg=CARD, fg=SUB,
        ).pack(anchor="w", pady=(0, 6))

        it = self._expression_pick()
        if not it:
            return
        card, body = self._lesson_card(inner, " 📣 今日表达课 ", self.EXPR_COLOR, it)
        for p in it.get("b", []):
            if p.startswith("今天的启发"):
                tk.Label(
                    body, text="💡 " + p, font=F_SMALL, bg="#FBF5E7", fg="#6B5B2E",
                    anchor="w", justify="left", wraplength=950,
                ).pack(fill="x", padx=18, pady=3)
            else:
                tk.Label(
                    body, text=p, font=F_SMALL, bg=CARD, fg=INK,
                    anchor="w", justify="left", wraplength=950,
                ).pack(fill="x", padx=18, pady=4)
        self._link_chips(body, it.get("links", []), "延伸学习：", self.EXPR_COLOR, "#E4EFEA", "#2E6B5A")
        self._fit(card, 140)

    # ------------------------------------------------------------ 每周总结
    def render_weekly(self):
        inner = self.scroll_weekly.inner
        for w in inner.winfo_children():
            w.destroy()
        weekly = (self.data or {}).get("weekly")
        if not weekly:
            card = Card(inner, 1000, self._h(190), radius=14)
            card.pack(fill="x", pady=24)
            tk.Label(card.body, text="🗓 每周总结", font=F_H, bg=CARD, fg=GOLD).pack(padx=22, pady=(20, 6))
            tk.Label(
                card.body, text="每周日《新闻联播》播完后自动生成，汇总本周六大主题：\n金融 · AI科技 · 医学 · 科学 · 国际局势 · 民生",
                font=F_BASE, bg=CARD, fg=INK, justify="left",
            ).pack(padx=22, pady=4)
            tk.Label(
                card.body, text="本周日晚 20:00 弹窗时即可看到", font=F_SMALL, bg=CARD, fg=SUB,
            ).pack(padx=22, pady=(4, 20))
            return

        tk.Label(
            inner, text="🗓 每周总结  {0}".format(weekly.get("range", "")),
            font=F_H, bg=CARD, fg=GOLD,
        ).pack(anchor="w", pady=(2, 2))
        tk.Label(
            inner, text="梳理本周联播 {0} 条 · 生成于 {1}".format(
                weekly.get("news_count", 0), (weekly.get("generated_at") or "")[11:16]
            ),
            font=F_SMALL, bg=CARD, fg=SUB,
        ).pack(anchor="w", pady=(0, 8))

        idxw = weekly.get("indices") or []
        if idxw:
            tk.Label(inner, text="本周大盘", font=F_MID, bg=CARD, fg=TEAL).pack(anchor="w", pady=(0, 4))
            grid = tk.Frame(inner, bg=CARD)
            grid.pack(fill="x")
            for i in range(4):
                grid.grid_columnconfigure(i, weight=1, uniform="wk")
            for i, it in enumerate(idxw[:8]):
                card = Card(grid, 1000, self._h(80), radius=12)
                card.grid(row=i // 4, column=i % 4, sticky="we", padx=4, pady=4)
                bw = card.body
                tk.Label(bw, text=it.get("name", ""), font=F_SMALL, bg=CARD, fg=SUB).pack(anchor="w", padx=14, pady=(7, 0))
                try:
                    close_s = "{0:,.2f}".format(float(it.get("close", 0)))
                except (TypeError, ValueError):
                    close_s = "--"
                tk.Label(bw, text=close_s, font=F_NUM, bg=CARD, fg=INK).pack(anchor="w", padx=14)
                pct = it.get("week_pct")
                tk.Label(
                    bw, text="周涨跌 {0}".format(self._fmt_pct(pct)),
                    font=F_MID, bg=CARD, fg=self._pct_color(pct),
                ).pack(anchor="w", padx=14, pady=(0, 7))

        # 本周科技要闻（量子位 RSS + 官网入口）
        media = weekly.get("media") or {}
        qbit = media.get("qbitai") or []
        sites = media.get("sites") or []
        if qbit:
            mh = tk.Frame(inner, bg=CARD)
            mh.pack(fill="x", pady=(14, 4))
            tk.Label(mh, text="⚡ 本周科技要闻", font=F_MID, bg=CARD, fg="#4A6B8A").pack(side="left")
            for s in sites:
                self._btn(mh, "前往 {0} ↗".format(s.get("name", "")),
                          lambda u=s.get("url", ""): webbrowser.open(u)).pack(side="right", padx=4)
            tk.Label(
                inner, text="来源：量子位（AI/科技前沿）· 点击标题打开原文或搜索详情",
                font=F_TINY, bg=CARD, fg=SUB,
            ).pack(anchor="w", pady=(0, 4))
            for it in qbit:
                rc = Card(inner, 1000, self._h(40), radius=10)
                rc.pack(fill="x", pady=2)
                row = tk.Frame(rc.body, bg=CARD)
                row.pack(fill="both", expand=True, padx=(14, 12), pady=3)
                row.grid_columnconfigure(0, weight=1)
                tl = tk.Label(
                    row, text="▍" + it.get("title", ""), font=F_SMALL, bg=CARD, fg="#1F5FA8",
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

        for sec in weekly.get("cats") or []:
            cat = sec.get("cat", "")
            color = WEEKLY_COLORS.get(cat, TEAL)
            ch = tk.Frame(inner, bg=CARD)
            ch.pack(fill="x", pady=(12, 4))
            self._chip(ch, " " + cat + " ", color, fg="#FFFFFF").pack(side="left")
            tk.Label(ch, text="  {0} 条".format(len(sec.get("items", []))), font=F_SMALL, bg=CARD, fg=SUB).pack(
                side="left", pady=(1, 0)
            )
            for t in sec.get("items", []):
                rc = Card(inner, 1000, self._h(38), radius=10)
                rc.pack(fill="x", pady=2)
                row = tk.Frame(rc.body, bg=CARD)
                row.pack(fill="both", expand=True, padx=(14, 12), pady=4)
                row.grid_columnconfigure(0, weight=1)
                tk.Label(
                    row, text="•  " + t, font=F_SMALL, bg=CARD, fg=INK, anchor="w", justify="left",
                ).grid(row=0, column=0, sticky="we")

    # ------------------------------------------------------------ 术语词典
    TERM_COLOR = "#4A6B8A"

    def _set_term_domain(self, d):
        self._term_domain = d
        self.render_terms()

    def _ai_expand_terms(self):
        """AI 生成并追加当前/随机领域的新术语。"""
        import random as _r

        from . import ai_gen, terms_updater

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
                items = ai_gen.generate_terms(domain, 3)
                if not items:
                    self.root.after(0, lambda: self._set_status("AI 生成失败，请重试"))
                    return
                n = terms_updater.append_terms(domain, items)
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
        from . import ai_gen, terms_updater

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
        head = tk.Frame(inner, bg=CARD)
        head.pack(fill="x", pady=(2, 4))
        tk.Label(head, text="📖 术语词典", font=F_H, bg=CARD, fg=self.TERM_COLOR).pack(side="left")
        tk.Label(head, text="各领域专业名词与基础知识 · 系统补认知", font=F_SMALL, bg=CARD, fg=SUB).pack(
            side="left", padx=10, pady=(4, 0)
        )
        self._btn(head, "➕ 新增领域", self._ai_new_domain).pack(side="right", padx=4)
        self._btn(head, "🧠 AI 扩充", self._ai_expand_terms).pack(side="right", padx=4)
        tk.Label(head, text="🔍", font=F_SMALL, bg=CARD).pack(side="right", padx=(0, 4))
        self._term_search = tk.Entry(
            head, font=F_SMALL, width=26, bg=CARD, fg=INK, relief="solid", bd=1,
            highlightthickness=1, highlightbackground=LINE,
        )
        self._term_search.pack(side="right")
        if self._term_query:
            self._term_search.insert(0, self._term_query)
        self._term_search.bind("<KeyRelease>", self._on_term_search)

        # 领域筛选 chips
        domains = sorted({t["domain"] for t in all_terms})
        chips = tk.Frame(inner, bg=CARD)
        chips.pack(fill="x", pady=(4, 2))

        def make_chip(label, domain, active):
            lb = tk.Label(
                chips, text=" " + label + " ", font=F_SMALL,
                bg=(self.TERM_COLOR if active else "#EDE9E0"),
                fg=("#FFFFFF" if active else INK),
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
            font=F_TINY, bg=CARD, fg=SUB,
        ).pack(anchor="w", pady=(2, 4))
        if limited:
            tk.Label(
                inner, text="💡 术语较多，为流畅滚动仅展示前 100 条——点击上方领域或输入关键词查看全部",
                font=F_TINY, bg=CARD, fg=GOLD,
            ).pack(anchor="w", pady=(0, 4))

        cards = []
        for it in terms:
            card, body = self._lesson_card(inner, " " + it.get("domain", "") + " ", self.TERM_COLOR, it)
            for p in it.get("b", []):
                tk.Label(
                    body, text=p, font=F_SMALL, bg=CARD, fg=INK,
                    anchor="w", justify="left", wraplength=950,
                ).pack(fill="x", padx=18, pady=3)
            self._link_chips(body, it.get("links", []), "延伸学习：", self.TERM_COLOR, "#E7EDF3", "#33556B")
            cards.append(card)
        # 批量布局：一次完成几何计算，再统一按内容自适应高度（避免逐卡 update_idletasks 卡顿）
        inner.update_idletasks()
        for card in cards:
            card.configure(height=max(110, card.body.winfo_reqheight() + 36))

    # ------------------------------------------------------------ 工具
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
    def _fmt_pct(v):
        if v is None:
            return "--"
        try:
            f = float(v)
        except (TypeError, ValueError):
            return "--"
        return "{0:+.2f}%".format(f)


def main(smoke=False):
    root = tk.Tk()
    MorningApp(root, smoke=smoke)
    root.mainloop()
