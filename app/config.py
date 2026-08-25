# -*- coding: utf-8 -*-
"""路径与配置加载。"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(ROOT, "cache")
RAW_DIR = os.path.join(CACHE_DIR, "raw")
KNOWLEDGE_DIR = os.path.join(ROOT, "knowledge")
CONFIG_PATH = os.path.join(ROOT, "config.json")
TODAY_PATH = os.path.join(CACHE_DIR, "today.json")

DEFAULT_CONFIG = {
    "indices": [
        {"secid": "1.000001", "name": "上证指数"},
        {"secid": "0.399001", "name": "深证成指"},
        {"secid": "0.399006", "name": "创业板指"},
        {"secid": "1.000300", "name": "沪深300"},
        {"secid": "1.000688", "name": "科创50"},
    ],
    "funds": ["161725", "003095", "005827", "110020", "000001"],
    "news_max_items": 30,
}


def ensure_dirs():
    for d in (CACHE_DIR, RAW_DIR):
        os.makedirs(d, exist_ok=True)


def load_config():
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            cfg = json.load(f)
        merged = dict(DEFAULT_CONFIG)
        merged.update(cfg or {})
        return merged
    except Exception:
        return dict(DEFAULT_CONFIG)
