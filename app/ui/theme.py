# -*- coding: utf-8 -*-
r"""每日晨报 MorningBoard 界面配色 / 字体 / 分组色板。

多主题支持：
- 每套主题是一份完整色值字典，收录在 THEMES 里；
- 取色统一走 `C`（Palette 对象）：`C.BG`、`C.INK`、`C.ACCENT`……
- 切主题调 `set_theme(name)`，它会同时刷新 `C` **和**模块级旧常量
  （BG/CARD/INK…），这样还没迁移到 `C.` 写法的代码在重建控件时也能拿到新色，
  实现渐进迁移，不必一次性改完 11 个文件。

配色规范遵循本机 `工作文件夹\.dsh\skills\dataviz\color-accessibility-guide`：
正文对比度 ≥ WCAG AA 4.5:1，涨跌不单靠红绿区分（另配 ✅/🔻 文字符号）。
"""

# ---------------- 主题表 ----------------
# 键名即旧的模块级常量名，新增语义别名：
#   SOFT      浅色卡片/区块底（原先散落 #FBF5E7 / #FBF7EE / #FBF2EC / #F4F0E6）
#   SOFT_LINE 与 SOFT 配套的描边
#   LINK      可点链接蓝
#   ON_ACCENT 强调底色块上的前景色（原先大量写死 #FFFFFF）
#   MUTED_BLUE 历史回顾页的板块标签色

_MORANDI = {
    "BG": "#F4F1E8",
    "CARD": "#FFFFFF",
    "CARD_HOVER": "#FBF5E9",
    "INK": "#2A2722",
    "SUB": "#6E685C",
    "LINE": "#DCD4C2",
    "ACCENT": "#9A4A3F",
    "ACCENT_D": "#7E3B32",
    "TEAL": "#33545C",
    "GOLD": "#A98E4A",
    "UP": "#B03A2E",
    "DOWN": "#1E7A5A",
    "FLAT": "#5C584E",
    "UP_TINT": "#F4DCD6",
    "DOWN_TINT": "#D8E9E0",
    "SOFT": "#FBF5E7",
    "SOFT_LINE": "#E4D5AC",
    "LINK": "#1F5FA8",
    "ON_ACCENT": "#FFFFFF",
    "MUTED_BLUE": "#4A6B8A",
}

_DARK = {
    "BG": "#1A1A1D",
    "CARD": "#25252B",
    "CARD_HOVER": "#303038",
    "INK": "#E8E6E1",
    "SUB": "#A8A49C",
    "LINE": "#3A3A44",
    "ACCENT": "#E08A6E",
    "ACCENT_D": "#C96F52",
    "TEAL": "#6FB3C4",
    "GOLD": "#D9BC6A",
    "UP": "#E5484D",
    "DOWN": "#3FA85F",
    "FLAT": "#9A958C",
    "UP_TINT": "#3D2426",
    "DOWN_TINT": "#1F3328",
    "SOFT": "#2C2C34",
    "SOFT_LINE": "#3E3E4A",
    "LINK": "#7FB3E8",
    "ON_ACCENT": "#1A1A1D",
    "MUTED_BLUE": "#8FB8DA",
}

_MINT = {
    # 护眼青：整界面明显的冷绿色系（底/卡/边/强调/链接全绿），与纸感暖色拉开
    "BG": "#E2F0E9",
    "CARD": "#F8FCFA",
    "CARD_HOVER": "#DCEEE4",
    "INK": "#1F2A26",
    "SUB": "#567068",
    "LINE": "#A8CFBE",
    "ACCENT": "#2F7A63",
    "ACCENT_D": "#245F4D",
    "TEAL": "#3D6B7A",
    "GOLD": "#8A7A2E",
    "UP": "#C0392B",
    "DOWN": "#1E7A5A",
    "FLAT": "#5C6B66",
    "UP_TINT": "#F6E3DF",
    "DOWN_TINT": "#DCEDE5",
    "SOFT": "#EAF5EF",
    "SOFT_LINE": "#9CC9B5",
    "LINK": "#2E7D5B",
    "ON_ACCENT": "#FFFFFF",
    "MUTED_BLUE": "#2E7D5B",
}

_CONTRAST = {
    # 高对比：浅灰底 + 白卡 + 黑框，黑白灰为主、强调只用警示红，硬朗清晰
    "BG": "#EAEAEA",
    "CARD": "#FFFFFF",
    "CARD_HOVER": "#F0F0F0",
    "INK": "#000000",
    "SUB": "#404040",
    "LINE": "#000000",
    "ACCENT": "#C0392B",
    "ACCENT_D": "#96281B",
    "TEAL": "#1A5490",
    "GOLD": "#7D6608",
    "UP": "#C0392B",
    "DOWN": "#0E7A46",
    "FLAT": "#404040",
    "UP_TINT": "#FBE3E0",
    "DOWN_TINT": "#D9EFE4",
    "SOFT": "#F5F5F5",
    "SOFT_LINE": "#B0B0B0",
    "LINK": "#0033CC",
    "ON_ACCENT": "#FFFFFF",
    "MUTED_BLUE": "#0033CC",
}

THEMES = {
    "morandi": _MORANDI,
    "dark": _DARK,
    "mint": _MINT,
    "contrast": _CONTRAST,
}

THEME_NAMES = {
    "morandi": "纸感莫兰迪",
    "dark": "深色墨",
    "mint": "护眼青",
    "contrast": "高对比",
}

DEFAULT_THEME = "morandi"


class _Palette:
    """取色对象：`C.BG` / `C.INK`……切主题时原地更新，所有持有者同步生效。"""

    def __init__(self, d):
        self.__dict__.update(d)

    def __getattr__(self, k):
        # 未定义的键返回空串而不是抛异常，避免个别字段缺失直接崩界面
        return self.__dict__.get(k, "")


C = _Palette(dict(THEMES[DEFAULT_THEME]))
_current = DEFAULT_THEME


def current_theme():
    return _current


def set_theme(name):
    """切换主题：刷新 Palette，并同步模块级旧常量（兼容尚未迁移的代码）。"""
    global _current
    _current = name if name in THEMES else DEFAULT_THEME
    C.__dict__.update(THEMES[_current])
    globals().update(THEMES[_current])
    _refresh_derived()
    return _current


# ---------------- 模块级常量（= 当前主题取值，切主题时同步刷新） ----------------
BG = _MORANDI["BG"]
CARD = _MORANDI["CARD"]
CARD_HOVER = _MORANDI["CARD_HOVER"]
INK = _MORANDI["INK"]
SUB = _MORANDI["SUB"]
LINE = _MORANDI["LINE"]
ACCENT = _MORANDI["ACCENT"]
ACCENT_D = _MORANDI["ACCENT_D"]
TEAL = _MORANDI["TEAL"]
GOLD = _MORANDI["GOLD"]
UP = _MORANDI["UP"]
DOWN = _MORANDI["DOWN"]
FLAT = _MORANDI["FLAT"]
UP_TINT = _MORANDI["UP_TINT"]
DOWN_TINT = _MORANDI["DOWN_TINT"]
SOFT = _MORANDI["SOFT"]
SOFT_LINE = _MORANDI["SOFT_LINE"]
LINK = _MORANDI["LINK"]
ON_ACCENT = _MORANDI["ON_ACCENT"]
MUTED_BLUE = _MORANDI["MUTED_BLUE"]

# 分组/分类色板：随主题重建（深色下整体提亮，保证卡底上有足够对比度）
GROUP_COLORS = {}
CAT_COLORS = {}
WEEKLY_COLORS = {}

# 分类色在深色主题下的替代值（键与浅色一致）
_CAT_DARK = {
    "周易": "#E0857A",
    "哲学": "#7FB3C4",
    "心理学": "#D9B45C",
    "美学": "#B394D6",
    "文学": "#D69A6A",
    "音乐": "#7FC2D6",
    "毛选": "#E5484D",
    "摄影": "#6FA8DC",
    "经济学": "#9CC46F",
    "历史": "#C2A178",
    "茶艺": "#9AB88A",
    "礼仪": "#BCA0D6",
    "官场文化": "#D6B478",
}
_CAT_LIGHT = {
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
_WEEKLY_LIGHT = {
    "金融": "#A07A2E",
    "AI科技": "#4A7A8A",
    "医学": "#2E6B4F",
    "科学": "#6B4E8E",
    "国际局势": "#33545C",
    "民生": "#8A5A2B",
}
_WEEKLY_DARK = {
    "金融": "#D9B45C",
    "AI科技": "#7FC2D6",
    "医学": "#6FBF95",
    "科学": "#B394D6",
    "国际局势": "#7FB3C4",
    "民生": "#D69A6A",
}


# 板块配色三元组：(强调色 accent, 淡底 tint, 淡底上的深字 ink)
# 各 tab 用 section("think") 这样的方式取，深色主题下自动换成提亮版，
# 否则浅色淡底（#F5EBDD 这类）配深色字在深色卡上会糊成一片。
_SECTIONS_LIGHT = {
    "think": ("#B5651D", "#F5EBDD", "#8A5A20"),
    "fallacy": ("#8E3B3B", "#F5E5E5", "#7A3030"),
    "lesson": ("#A98E4A", "#F3EBD9", "#7A6530"),
    "express": ("#2F6B5A", "#E7EDF3", "#33556B"),
    "terms": ("#2E6B5A", "#E4EFEA", "#2E6B5A"),
    "info": ("#4A6B8A", "#EAF1F6", "#1F5FA8"),
}
_SECTIONS_DARK = {
    "think": ("#E8A05C", "#3A2E20", "#F0C896"),
    "fallacy": ("#E57373", "#3D2426", "#F2A9A9"),
    "lesson": ("#D9BC6A", "#3A3220", "#E8D49A"),
    "express": ("#6FB3C4", "#223038", "#A8D8E6"),
    "terms": ("#7FCFA8", "#22382E", "#A8E0C0"),
    "info": ("#7FB3E8", "#22303D", "#A8CCF0"),
}


def section(name):
    """取板块配色三元组 (accent, tint, ink)，随主题切换。"""
    table = _SECTIONS_DARK if _current == "dark" else _SECTIONS_LIGHT
    return table.get(name) or _SECTIONS_LIGHT.get(name) or (ACCENT, SOFT, INK)


def _refresh_derived():
    """重建随主题变化的色板字典。"""
    global GROUP_COLORS, CAT_COLORS, WEEKLY_COLORS
    is_dark = _current == "dark"
    GROUP_COLORS.clear()
    GROUP_COLORS.update(
        {
            "时政": C.ACCENT,
            "国内": C.TEAL,
            "国际": "#B394D6" if is_dark else "#6B5B8E",
            "财经科技": C.GOLD,
            "快讯": "#C2A178" if is_dark else "#7A6A3A",
            "其他": C.SUB,
        }
    )
    CAT_COLORS.clear()
    CAT_COLORS.update(_CAT_DARK if is_dark else _CAT_LIGHT)
    WEEKLY_COLORS.clear()
    WEEKLY_COLORS.update(_WEEKLY_DARK if is_dark else _WEEKLY_LIGHT)


_refresh_derived()

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
