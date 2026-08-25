# -*- coding: utf-8 -*-
"""入口：后台生成今日晨报缓存（供每日定时任务调用）。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import generate  # noqa: E402

if __name__ == "__main__":
    payload, is_new = generate.generate_today(force=True)
    news_n = len((payload.get("news") or {}).get("items", []))
    fund_n = len((payload.get("funds") or {}).get("watchlist", []))
    print("date={0} news={1} funds={2} new={3}".format(payload.get("date"), news_n, fund_n, is_new))
    sys.exit(0)
