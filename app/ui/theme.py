# -*- coding: utf-8 -*-
"""每日晨报 MorningBoard 界面配色 / 字体 / 分组色板常量。"""
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
