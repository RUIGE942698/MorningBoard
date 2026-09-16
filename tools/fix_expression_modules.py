# -*- coding: utf-8 -*-
"""按精确规则重做表达能力知识库的模块标签。

规则（避免上一版贪心关键词误判）：
  1. 原始条目（扩充前的 23 条）：用教练模块的关键词推断 _infer_module
  2. 计划内条目（标题以计划主题开头，AI 常追加副标题）：用该主题所属模块
  3. 计划外条目（AI 多返回的）：用 _infer_module
"""
import io
import json
import os
import sys

ROOT = r'C:\Users\lenovo\Desktop\压缩包\MorningBoard'
os.chdir(ROOT)
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from app import expression_coach as coach  # noqa: E402
from expand_expression_kb import TOPICS, norm_title  # noqa: E402

KB = r'knowledge\expression.json'
kb = json.load(io.open(KB, encoding='utf-8'))
orig = json.load(io.open(KB + '.bak_expand', encoding='utf-8'))
orig_titles = {norm_title(x.get('t')) for x in orig}

planned = []          # [(normalized_topic, module)]
for mod, topics in TOPICS.items():
    for t in topics:
        planned.append((norm_title(t), mod))


def _infer_clean(it):
    """剥掉已有 module 字段后再推断（_infer_module 会优先返回已存在的值）。"""
    probe = {k: v for k, v in it.items() if k != 'module'}
    return coach._infer_module(probe)


def decide(it):
    nt = norm_title(it.get('t'))
    if nt in orig_titles:
        return _infer_clean(it), 'orig'
    for pnorm, mod in planned:
        if nt.startswith(pnorm):
            return mod, 'planned'
    return _infer_clean(it), 'extra'


from collections import Counter  # noqa: E402
before = Counter(x.get('module') for x in kb)
kinds = Counter()
for it in kb:
    m, kind = decide(it)
    kinds[kind] += 1
    it['module'] = m
after = Counter(x.get('module') for x in kb)

io.open(KB, 'w', encoding='utf-8').write(json.dumps(kb, ensure_ascii=False, indent=1))
print('判定来源:', dict(kinds))
print('模块分布（前）:', dict(before))
print('模块分布（后）:', dict(after))
print('\n关键条目归属复核:')
for want in ('PREP 即兴表达', '电梯演讲', 'SCQA', '金字塔原理', '讲故事的结构',
             '被质疑时的四步回应', '停顿的力量', '紧张重定义', '互惠原则'):
    for it in kb:
        if str(it.get('t', '')).startswith(want):
            print('   [{0}] {1}'.format(it.get('module'), it.get('t')[:40]))
            break
