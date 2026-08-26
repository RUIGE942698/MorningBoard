# -*- coding: utf-8 -*-
"""通用 UI 控件：圆角卡片 / 可滚动容器 / 迷你走势图 / 新闻分类。"""
import tkinter as tk
from tkinter import ttk
from .theme import *
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
        # 不再单独绑定滚轮——由 MorningApp 的全局滚轮统一处理（鼠标在任意子控件上都能滚动）
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
