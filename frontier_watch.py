# -*- coding: utf-8 -*-
"""前沿速报后台进程：定时抓取高质量前沿消息（AI/科技/科学），达阈值即桌面弹窗。

- 只有分数 >= app.frontier.PUSH_MIN_SCORE 的新条目才弹窗（避免打扰）
- 同时把结果写入 cache/frontier.json，播报界面打开即是最新
- 弹窗为置顶小窗：最多 3 条，点击打开原文，若干秒后自动关闭

用法：
    pythonw frontier_watch.py                 常驻（默认每 60 分钟）
    pythonw frontier_watch.py --interval 30   自定义间隔（分钟）
    python frontier_watch.py --once           只检查一次
    python frontier_watch.py --once --no-ui   只抓取/写缓存，不弹窗
"""
import argparse
import json
import os
import sys
import time
import traceback
import urllib.parse
import webbrowser
from datetime import datetime

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app import config, frontier  # noqa: E402

LOG_PATH = os.path.join(config.CACHE_DIR, "frontier_push.log")
MAX_ITEMS_IN_TOAST = 3
TOAST_SECONDS = 25
LOCK_PORT = 18766   # 单实例保护：避免重复弹窗


def acquire_lock():
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", LOCK_PORT))
        s.listen(1)
        return s
    except OSError:
        return None


def log(msg):
    line = "[{0}] {1}".format(datetime.now().strftime("%Y-%m-%d %H:%M:%S"), msg)
    try:
        os.makedirs(config.CACHE_DIR, exist_ok=True)
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:  # noqa: BLE001
        pass
    try:
        if sys.stdout:
            print(line, flush=True)
    except Exception:  # noqa: BLE001
        pass


def _rel(age_hours):
    if age_hours is None:
        return ""
    if age_hours < 1:
        return "{0} 分钟前".format(int(age_hours * 60))
    if age_hours < 48:
        return "{0} 小时前".format(int(round(age_hours)))
    return "{0} 天前".format(int(age_hours // 24))


CACHE_REVIEW = os.path.join(config.CACHE_DIR, "frontier_review_state.json")
REVIEW_WINDOW = (19, 23)   # 晚间窗口：19:00–23:00 之间才推（睡前复习当天所学）
REVIEW_SAME_DAY = True     # True=复习"当天新增"；False=复习"前一天"


def in_review_window(now=None):
    now = now or datetime.now()
    return REVIEW_WINDOW[0] <= now.hour < REVIEW_WINDOW[1]


def maybe_review(force=False):
    """每天一次（默认仅在晚间窗口内）：把生词做成"睡前复习"弹窗。返回复习词条数。"""
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    if not force and not in_review_window(now):
        return 0
    st = {}
    try:
        with open(CACHE_REVIEW, encoding="utf-8") as f:
            st = json.load(f)
    except Exception:  # noqa: BLE001
        st = {}
    if not force and st.get("last_review") == today:
        return 0
    try:
        day, rows = frontier.review_vocab(same_day=REVIEW_SAME_DAY, limit=8)
    except Exception as e:  # noqa: BLE001
        log("复习取词失败: {0}".format(e))
        return 0
    if not rows:
        return 0
    log("生词复习推送: {0} 的 {1} 个概念（晚间窗口 {2}:00-{3}:00）".format(
        day, len(rows), REVIEW_WINDOW[0], REVIEW_WINDOW[1]))
    if show_review_toast(day, rows):
        try:
            os.makedirs(config.CACHE_DIR, exist_ok=True)
            st["last_review"] = today
            st["last_day"] = day
            st["count"] = len(rows)
            with open(CACHE_REVIEW, "w", encoding="utf-8") as f:
                json.dump(st, f, ensure_ascii=False)
        except Exception:  # noqa: BLE001
            pass
    return len(rows)


def show_review_toast(day, rows, seconds=30):
    """生词复习小窗：列出前一天新增的概念，点击可搜索。"""
    try:
        import tkinter as tk
        import webbrowser
    except Exception as e:  # noqa: BLE001
        log("复习弹窗不可用: {0}".format(e))
        return False
    try:
        win = tk.Tk()
        win.title("生词复习")
        win.configure(bg="#FFFDF7")
        win.attributes("-topmost", True)
        sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
        w, h = 470, 150 + 46 * len(rows)
        win.geometry("{0}x{1}+{2}+{3}".format(w, h, sw - w - 24, sh - h - 64))
        win.resizable(False, False)
        head = tk.Frame(win, bg="#2F6F4F", height=34)
        head.pack(fill="x")
        tk.Label(head, text="📓 睡前复习 · {0} 新增 {1} 个".format(day, len(rows)),
                 bg="#2F6F4F", fg="#FFFFFF",
                 font=("Microsoft YaHei UI", 10, "bold")).pack(side="left", padx=12, pady=6)
        tk.Label(head, text="点击词条可搜索", bg="#2F6F4F", fg="#EAF3EE",
                 font=("Microsoft YaHei UI", 8)).pack(side="right", padx=10)
        body = tk.Frame(win, bg="#FFFDF7")
        body.pack(fill="both", expand=True, padx=10, pady=6)
        for r in rows:
            t = r.get("t", "")
            row = tk.Frame(body, bg="#FFFFFF", highlightbackground="#E6E0D0",
                           highlightthickness=1)
            row.pack(fill="x", pady=2)
            lb = tk.Label(row, text="{0}：{1}".format(t, (r.get("d") or "")[:44]),
                          bg="#FFFFFF", fg="#2A2722", wraplength=w - 34,
                          justify="left", anchor="w", cursor="hand2",
                          font=("Microsoft YaHei UI", 9))
            lb.pack(fill="x", padx=10, pady=5)
            lb.bind("<Button-1>", lambda e, q=t: webbrowser.open(
                "https://www.baidu.com/s?wd=" + urllib.parse.quote(q)))
        foot = tk.Frame(win, bg="#FFFDF7")
        foot.pack(fill="x", pady=(0, 8))
        tk.Button(foot, text="知道了", command=win.destroy, relief="flat",
                  bg="#EFE9DA", fg="#2A2722",
                  font=("Microsoft YaHei UI", 9)).pack(side="right", padx=10)
        tk.Label(foot, text="全部生词：播报界面 → 前沿速报 → 📓 生词本",
                 bg="#FFFDF7", fg="#8A8577",
                 font=("Microsoft YaHei UI", 8)).pack(side="left", padx=10)
        win.after(seconds * 1000, lambda: win.winfo_exists() and win.destroy())
        win.mainloop()
        return True
    except Exception as e:  # noqa: BLE001
        log("复习弹窗失败: {0}".format(e))
        return False


GROUP_NAME = {"ai": "前沿 AI", "tech": "科技产业", "physics": "物理",
              "medicine": "医学", "biology": "生物", "math": "数学"}


def show_toast(items):
    """置顶小窗提醒（Tk，无控制台）。"""
    try:
        import tkinter as tk
    except Exception as e:  # noqa: BLE001
        log("toast 不可用(Tk 缺失): {0}".format(e))
        return False
    try:
        win = tk.Tk()
        win.title("前沿速报")
        win.configure(bg="#FFFDF7")
        win.attributes("-topmost", True)
        try:
            win.attributes("-alpha", 0.98)
        except Exception:  # noqa: BLE001
            pass
        sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
        w, h = 460, 120 + 76 * min(len(items), MAX_ITEMS_IN_TOAST)
        win.geometry("{0}x{1}+{2}+{3}".format(w, h, sw - w - 24, sh - h - 64))
        win.resizable(False, False)

        head = tk.Frame(win, bg="#8C6B3F", height=34)
        head.pack(fill="x")
        tk.Label(head, text="🚀 前沿速报 · {0} 条高分消息".format(len(items)),
                 bg="#8C6B3F", fg="#FFFFFF", font=("Microsoft YaHei UI", 10, "bold")
                 ).pack(side="left", padx=12, pady=6)
        tk.Label(head, text="点击条目打开原文", bg="#8C6B3F", fg="#F4F1E8",
                 font=("Microsoft YaHei UI", 8)).pack(side="right", padx=10)

        body = tk.Frame(win, bg="#FFFDF7")
        body.pack(fill="both", expand=True, padx=10, pady=6)
        for it in items[:MAX_ITEMS_IN_TOAST]:
            row = tk.Frame(body, bg="#FFFFFF", highlightbackground="#E6E0D0",
                           highlightthickness=1)
            row.pack(fill="x", pady=3)
            meta = "{0} · {1}分 · {2}".format(
                GROUP_NAME.get(it.get("group"), it.get("group", "")),
                it.get("score", ""), _rel(it.get("age_hours")))
            tk.Label(row, text=meta, bg="#FFFFFF", fg="#8C6B3F",
                     font=("Microsoft YaHei UI", 8)).pack(anchor="w", padx=10, pady=(6, 0))
            title = it.get("title_zh") or it.get("title", "")
            tl = tk.Label(row, text=title, bg="#FFFFFF", fg="#2A2722", wraplength=w - 40,
                          justify="left", anchor="w",
                          font=("Microsoft YaHei UI", 10, "bold"), cursor="hand2")
            tl.pack(fill="x", padx=10)
            desc = (it.get("desc_zh") or it.get("desc") or "")[:120]
            if desc:
                tk.Label(row, text=desc, bg="#FFFFFF", fg="#6B6558", wraplength=w - 40,
                         justify="left", anchor="w",
                         font=("Microsoft YaHei UI", 8)).pack(fill="x", padx=10)
            url = it.get("url", "")
            if url:
                for wid in (row, tl):
                    wid.bind("<Button-1>", lambda e, u=url: webbrowser.open(u))
            tk.Frame(row, bg="#FFFFFF", height=6).pack(fill="x")

        foot = tk.Frame(win, bg="#FFFDF7")
        foot.pack(fill="x", pady=(0, 8))
        tk.Button(foot, text="关闭", command=win.destroy, relief="flat",
                  bg="#EFE9DA", fg="#2A2722", font=("Microsoft YaHei UI", 9)
                  ).pack(side="right", padx=10)
        tk.Button(foot, text="打开每日播报查看全部",
                  command=lambda: (webbrowser.open("http://127.0.0.1"), win.destroy()),
                  relief="flat", bg="#EFE9DA", fg="#2A2722",
                  font=("Microsoft YaHei UI", 9)).pack(side="right", padx=4)
        win.after(TOAST_SECONDS * 1000, lambda: win.winfo_exists() and win.destroy())
        win.mainloop()
        return True
    except Exception as e:  # noqa: BLE001
        log("toast 失败: {0} | {1}".format(e, traceback.format_exc(limit=1)))
        return False


def check_once(no_ui=False):
    """跑一次检查：抓取 -> 比对 -> 弹窗。返回本次推送条数。"""
    try:
        fresh = frontier.check_new_for_push()
    except Exception as e:  # noqa: BLE001
        log("检查失败: {0}".format(e))
        return 0
    data = frontier.load_cached() or {}
    log("检查完成: 入选 {0} 条, 本次新高分消息 {1} 条 ({2})".format(
        data.get("kept", "?"), len(fresh), data.get("updated_at", "")))
    if fresh and not no_ui:
        lines = ["{0} [{1}分] {2}".format(
            GROUP_NAME.get(x.get("group"), x.get("group", "")), x.get("score"),
            (x.get("title_zh") or x.get("title", ""))[:60]) for x in fresh[:5]]
        log("推送: " + " | ".join(lines))
        show_toast(fresh)
    if not no_ui:
        try:
            maybe_review()          # 每天一次：前一天生词复习提醒
        except Exception as e:  # noqa: BLE001
            log("复习推送异常: {0}".format(e))
    return len(fresh)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--interval", type=int, default=60, help="检查间隔（分钟）")
    ap.add_argument("--once", action="store_true", help="只检查一次")
    ap.add_argument("--no-ui", action="store_true", help="不弹窗")
    ap.add_argument("--review", action="store_true", help="立即弹一次生词复习（忽略时段与每日限制）")
    ap.add_argument("--monthly", action="store_true", help="导出本月生词汇总 Markdown")
    args = ap.parse_args()

    if args.monthly:
        try:
            path = frontier.export_month_markdown()
            print("[OK] 月度汇总 -> {0}".format(path))
        except Exception as e:  # noqa: BLE001
            print("[FAIL] {0}".format(e))
        return 0
    if args.review:
        n = maybe_review(force=True)
        print("[OK] 复习推送 {0} 个概念".format(n))
        return 0

    log("前沿速报启动 (interval={0} 分钟, ai={1})".format(
        args.interval, frontier.ai_available()))
    if args.once:
        check_once(no_ui=args.no_ui)
        return 0
    lock = acquire_lock()
    if lock is None:
        log("已有实例在运行，本次退出")
        return 0
    try:
        while True:
            try:
                check_once(no_ui=args.no_ui)
            except KeyboardInterrupt:
                log("收到中断，退出")
                return 0
            except Exception as e:  # noqa: BLE001
                log("循环异常: {0}".format(e))
            time.sleep(max(5, args.interval) * 60)
    finally:
        try:
            lock.close()
        except Exception:  # noqa: BLE001
            pass


if __name__ == "__main__":
    raise SystemExit(main())
