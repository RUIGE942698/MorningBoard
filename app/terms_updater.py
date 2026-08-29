# -*- coding: utf-8 -*-
"""术语词典扩充：AI 生成新术语/新领域并写入词典。"""
import datetime as dt
import json
import os

from . import ai_gen, config


def _terms_dir():
    # 打包后知识库只读，术语扩充写到 %APPDATA%\\MorningBoard\\terms（开发时即 knowledge/terms）
    return config.TERMS_DIR


def list_domains():
    """返回现有领域列表。"""
    out = []
    try:
        for f in os.listdir(_terms_dir()):
            if not f.endswith(".json"):
                continue
            try:
                with open(os.path.join(_terms_dir(), f), encoding="utf-8") as fp:
                    data = json.load(fp)
                if data.get("domain"):
                    out.append(data["domain"])
            except Exception:  # noqa: BLE001
                pass
    except OSError:
        pass
    return out


def append_terms(domain, items):
    """把生成的术语追加到对应领域文件（按标题去重）。返回新增条数。"""
    try:
        files = os.listdir(_terms_dir())
    except OSError:
        return 0
    fn = None
    data = None
    for f in files:
        if not f.endswith(".json"):
            continue
        try:
            with open(os.path.join(_terms_dir(), f), encoding="utf-8") as fp:
                data = json.load(fp)
        except Exception:  # noqa: BLE001
            continue
        if data.get("domain") == domain:
            fn = f
            break
    if not fn or not isinstance(items, list):
        return 0
    existing = {it.get("t") for it in data.get("items", [])}
    added = [it for it in items if it.get("t") and it["t"] not in existing]
    if not added:
        return 0
    data.setdefault("items", []).extend(added)
    try:
        with open(os.path.join(_terms_dir(), fn), "w", encoding="utf-8") as fp:
            json.dump(data, fp, ensure_ascii=False, indent=1)
    except Exception:  # noqa: BLE001
        return 0
    return len(added)


def _domain_titles(domain):
    """该领域已有术语标题列表（用于 AI 防重复）。"""
    try:
        files = os.listdir(_terms_dir())
    except OSError:
        return []
    for f in files:
        if not f.endswith(".json"):
            continue
        try:
            with open(os.path.join(_terms_dir(), f), encoding="utf-8") as fp:
                data = json.load(fp)
        except Exception:  # noqa: BLE001
            continue
        if data.get("domain") == domain:
            return [it.get("t", "") for it in data.get("items", []) if it.get("t")]
    return []


def expand_domains(domains, count=3):
    """为给定领域列表各生成并追加 count 条术语。返回 [(domain, 新增数), ...]。"""
    results = []
    for domain in domains:
        try:
            items = ai_gen.generate_terms(domain, count, exclude=_domain_titles(domain))
            n = append_terms(domain, items or [])
            results.append((domain, n))
        except Exception:  # noqa: BLE001
            results.append((domain, 0))
    return results


def generate_new_domain(count=10):
    """用 AI 生成一个全新领域（领域名 + count 条术语），自动创建词典文件。

    返回新领域名；与现有领域重名或生成失败返回 None。
    """
    existing = set(list_domains())
    header = (
        "你是知识领域策划专家。请策划 1 个全新的、值得普通人系统了解的知识领域"
        "（务必不要与以下已有领域重复：{0}）。给领域起一个简洁的中文名（2-6 字），"
        "并编写 {1} 个该领域的重要专业术语。\n"
        "严格只输出一个 JSON 对象（不要任何其他文字、不要 markdown 围栏）：\n".format(
            "、".join(sorted(existing)[:40]), count
        )
    )
    json_tpl = (
        '{"domain":"领域名（如：茶艺、航空）",'
        '"items":[{"t":"术语名","s":"一句话定义（25字内）",'
        '"b":["第1段：是什么（约80字）","第2段：为什么重要（约80字）","第3段：常见误区或要点（约60字）"],'
        '"links":["延伸名词1","延伸名词2","延伸名词3"]}]}'
    )
    tail = "共 {0} 个术语；b 每段都是完整句子；items 数量必须等于 {0}。".format(count)
    data = ai_gen._extract_json(ai_gen._chat(header + json_tpl + "\n" + tail, max_tokens=4200))
    if not isinstance(data, dict) or not data.get("domain"):
        return None
    domain = str(data["domain"]).strip()
    items = data.get("items") or []
    if not domain or not items or domain in existing:
        return None
    fn = "terms_auto_{0}.json".format(dt.datetime.now().strftime("%Y%m%d%H%M%S"))
    try:
        with open(os.path.join(_terms_dir(), fn), "w", encoding="utf-8") as fp:
            json.dump({"domain": domain, "items": items}, fp, ensure_ascii=False, indent=1)
    except Exception:  # noqa: BLE001
        return None
    return domain
