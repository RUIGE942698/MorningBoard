# -*- coding: utf-8 -*-
"""MorningBoard 界面模块：aiweekly（AI 前沿）。

数据来自 app.ai_weekly —— 与「AI 周报」共用同一套抓取 / 归一化 / 去重 / 打分 /
层级配额算法，只是时间窗口收窄到 2 天，用于每日晨报里的速览。
"""
import tkinter as tk
import webbrowser

from app import config
from app.ui.theme import *
from app.ui.widgets import *

# 层级配色：一手官方最醒目，聚合与观点依次收敛
_TIER_COLOR = {
    1: "TEAL",
    2: "GOLD",
    3: "MUTED_BLUE",
    4: "ACCENT",
    5: "SUB",
}


class AIWeeklyTabMixin:
    def _tier_color(self, tier):
        name = _TIER_COLOR.get(tier or 9, "SUB")
        return getattr(C, name, C.SUB)

    def _on_ai_brief_ready(self):
        """后台预热完成后由 app.py 通过 root.after 回调到主线程，刷新页签。

        优先用 brief.json 里刚抓到的结果；拿不到就退回 payload 里已有的数据。
        仅在内容确实变了才重绘，避免无谓闪烁。
        """
        try:
            from app import ai_weekly
            cached = ai_weekly._read_brief_cache() or {}
        except Exception:  # noqa: BLE001
            return
        items = cached.get("items") or []
        if not items:
            return
        block = (self.data or {}).get("ai_brief") or {}
        if len(block.get("items") or []) == len(items):
            return
        meta = cached.get("meta") or {}
        self.data = self.data or {}
        self.data["ai_brief"] = {
            "items": items,
            "updated_at": cached.get("updated_at") or meta.get("updated_at") or "",
            "cached": True,
            "pending": False,
            "source_ok": meta.get("source_ok") or 0,
            "source_total": meta.get("source_total") or 0,
            "error": "",
        }
        self.render_ai_weekly()

    def render_ai_weekly(self):
        inner = self.scroll_aiweekly.inner
        for w in inner.winfo_children():
            w.destroy()

        block = (self.data or {}).get("ai_brief") or {}
        items = block.get("items") or []
        # 兜底：payload 里还没有（首次启动、缓存刚写好）就直接读缓存文件
        if not items:
            try:
                from app import ai_weekly
                cached = ai_weekly._read_brief_cache() or {}
                if cached.get("items"):
                    meta = cached.get("meta") or {}
                    block = {
                        "items": cached.get("items") or [],
                        "updated_at": cached.get("updated_at") or meta.get("updated_at") or "",
                        "source_ok": meta.get("source_ok") or 0,
                        "source_total": meta.get("source_total") or 0,
                    }
                    items = block["items"]
            except Exception:  # noqa: BLE001
                pass

        tk.Label(
            inner, text="🤖 AI 前沿速览", font=F_H, bg=C.CARD, fg=C.MUTED_BLUE,
        ).pack(anchor="w", pady=(2, 2))

        if not items:
            card = Card(inner, 1000, self._h(190), radius=14)
            card.pack(fill="x", pady=24)
            tk.Label(card.body, text="🤖 AI 前沿速览", font=F_H, bg=C.CARD, fg=C.MUTED_BLUE).pack(
                padx=22, pady=(20, 6))
            err = block.get("error") or ""
            body = ("自动抓取 20+ 个信息源（OpenAI / Anthropic / DeepMind / DeepSeek 官方 feed，\n"
                    "GitHub 周榜、Hugging Face、量子位 / IT之家 / InfoQ，以及 OpenRouter 匿名测试位），\n"
                    "按 AI 相关性过滤、跨源判重、重要性打分后选出当日大事。")
            if err:
                body += "\n\n上次抓取未成功：{0}".format(err[:90])
            tk.Label(card.body, text=body, font=F_BASE, bg=C.CARD, fg=C.INK,
                     justify="left").pack(padx=22, pady=4)
            tk.Label(card.body, text="下次晨报生成时会自动重试", font=F_SMALL,
                     bg=C.CARD, fg=C.SUB).pack(padx=22, pady=(4, 20))
            return

        meta_bits = []
        if block.get("source_total"):
            meta_bits.append("源 {0}/{1} 可用".format(
                block.get("source_ok") or 0, block.get("source_total")))
        when = (block.get("updated_at") or "")[5:16].replace("T", " ")
        if when:
            meta_bits.append("抓取于 {0}".format(when))
        if block.get("pending"):
            meta_bits.append("后台更新中")
        tk.Label(
            inner, text="近 2 天 · 共 {0} 条".format(len(items)) + (
                "  ·  " + " · ".join(meta_bits) if meta_bits else ""),
            font=F_SMALL, bg=C.CARD, fg=C.SUB,
        ).pack(anchor="w", pady=(0, 8))

        for it in items:
            tier = it.get("tier")
            rc = Card(inner, 1000, self._h(64), radius=10)
            rc.pack(fill="x", pady=3)
            row = tk.Frame(rc.body, bg=C.CARD)
            row.pack(fill="both", expand=True, padx=(14, 12), pady=6)
            row.grid_columnconfigure(1, weight=1)

            self._chip(row, " " + (it.get("tier_name") or "前沿")[:6] + " ",
                       self._tier_color(tier), fg=C.ON_ACCENT).grid(
                row=0, column=0, sticky="nw", padx=(0, 8), pady=(1, 0))

            title = it.get("title") or ""
            tl = tk.Label(
                row, text=title, font=F_SMALL, bg=C.CARD, fg=C.LINK,
                anchor="w", justify="left", cursor="hand2", wraplength=880,
            )
            tl.grid(row=0, column=1, sticky="we")
            if it.get("url"):
                tl.bind("<Button-1>",
                        lambda e, t=title, u=it.get("url", ""): self._article_menu(e, t, u))

            bits = [b for b in (it.get("source"), it.get("date")) if b]
            seen = it.get("also_seen") or []
            if seen:
                bits.append("另有 {0} 家报道".format(len(seen)))
            tk.Label(
                row, text="  ".join(str(b) for b in bits), font=F_TINY,
                bg=C.CARD, fg=C.SUB, anchor="w", justify="left", wraplength=880,
            ).grid(row=1, column=1, sticky="we", pady=(2, 0))

        foot = tk.Frame(inner, bg=C.CARD)
        foot.pack(fill="x", pady=(12, 2))
        tk.Label(
            foot, text="每周日 20:00 生成完整《AI 周报》（约 20 条，覆盖 5 层来源）",
            font=F_TINY, bg=C.CARD, fg=C.SUB,
        ).pack(side="left")
        self._btn(foot, "打开周报目录 ↗",
                  lambda: self._open_weekly_dir()).pack(side="right", padx=4)

    def _open_weekly_dir(self):
        import os
        import subprocess
        d = os.path.join(config.CACHE_DIR, "ai_weekly", "reports")
        try:
            if os.path.isdir(d):
                os.startfile(d)          # noqa: S606  Windows 专用
            else:
                webbrowser.open("https://github.com/trending?since=weekly")
        except Exception:  # noqa: BLE001
            webbrowser.open("https://github.com/trending?since=weekly")
