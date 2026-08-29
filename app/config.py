# -*- coding: utf-8 -*-
"""路径与配置加载。

开发模式：所有数据都在项目根目录（如桌面 MorningBoard_Share），行为不变。
打包模式（PyInstaller）：exe 是只读分发物，路径策略不同——
  - 只读资源（knowledge / tools / 内置 config.json）从 sys._MEIPASS 读取；
  - 可写数据（config.json / cache / 日志 / 历史归档 / 术语扩充）重定向到
    %APPDATA%\\MorningBoard，首次运行自动复制内置默认配置过去。
这样 exe 放哪都能跑，不会因为放桌面/只读目录而写不进去。
"""
import json
import os
import sys


def _is_frozen():
    return bool(getattr(sys, "frozen", False))


def _appdata_dir():
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, "MorningBoard")


if _is_frozen():
    ROOT = sys._MEIPASS  # PyInstaller 解压出的只读资源目录
    _DATA = _appdata_dir()
    KNOWLEDGE_DIR = os.path.join(ROOT, "knowledge")
    TERMS_DIR = os.path.join(_DATA, "terms")  # 术语扩充可写
    CACHE_DIR = os.path.join(_DATA, "cache")
    RAW_DIR = os.path.join(CACHE_DIR, "raw")
    CONFIG_PATH = os.path.join(_DATA, "config.json")
else:
    ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    CACHE_DIR = os.path.join(ROOT, "cache")
    RAW_DIR = os.path.join(CACHE_DIR, "raw")
    KNOWLEDGE_DIR = os.path.join(ROOT, "knowledge")
    TERMS_DIR = os.path.join(KNOWLEDGE_DIR, "terms")
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
    for d in (CACHE_DIR, RAW_DIR, TERMS_DIR):
        os.makedirs(d, exist_ok=True)


def ensure_config():
    """首次运行：把内置默认配置复制到可写目录（打包模式用，开发模式跳过）。"""
    if os.path.exists(CONFIG_PATH):
        return
    try:
        os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
        if _is_frozen():
            src = os.path.join(ROOT, "config.json")
            if os.path.exists(src):
                import shutil
                shutil.copy2(src, CONFIG_PATH)
                return
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_CONFIG, f, ensure_ascii=False, indent=1)
    except Exception:  # noqa: BLE001
        pass


def load_config():
    ensure_config()
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            cfg = json.load(f)
        merged = dict(DEFAULT_CONFIG)
        merged.update(cfg or {})
        return merged
    except Exception:  # noqa: BLE001
        return dict(DEFAULT_CONFIG)
