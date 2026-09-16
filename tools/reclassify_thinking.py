# -*- coding: utf-8 -*-
"""用 AI 给老题准确分类（type + skeleton），替换关键词推断的兜底偏斜。"""
import io
import json
import os
import sys
from collections import Counter

ROOT = r'C:\Users\lenovo\Desktop\压缩包\MorningBoard'
os.chdir(ROOT)
sys.path.insert(0, ROOT)
from app import ai_gen, thinking_coach as coach  # noqa: E402

P = r'knowledge\thinking.json'
items = json.load(io.open(P, encoding='utf-8'))
lines = []
for i, it in enumerate(items, 1):
    ask = "；".join(it.get('ask') or [])[:60]
    lines.append("{0}. 《{1}》｜{2}｜追问：{3}".format(
        i, it.get('t', ''), (it.get('s') or '')[:40], ask))

prompt = (
    "下面是一个中文思辨题库的 66 道题（序号. 标题｜背景｜追问）。请为每一道标注两件事：\n"
    "① type（四类延伸题：balance 权衡界定 / attribution 归因判断 / solution 对策 / impact 影响）\n"
    "② skeleton（议题骨架：resource 资源分配 / efficiency 公平与效率 / generation 代际冲突 / "
    "regulation 监管边界 / rights 权利冲突 / externality 外部性 / information 信息不对称 / "
    "incentive 激励扭曲 / moral 道德直觉vs功利计算 / culture 文化与价值冲突）\n"
    "判断依据是这道题真正在争什么，而不是标题里出现了哪个词。\n\n"
    + "\n".join(lines) +
    "\n\n严格只输出 JSON 数组（不要解释、不要 markdown）：\n"
    '[{"i":1,"type":"balance","skeleton":"rights"}, ...]  共 66 条，i 必须与上面序号一一对应。'
)
raw = ai_gen._chat(prompt, max_tokens=2600, timeout=180)
data = ai_gen._extract_json(raw)
if isinstance(data, dict):
    data = [data]
if not isinstance(data, list):
    print('AI 返回解析失败，保持原标签')
    sys.exit(1)

changed = 0
for row in data:
    try:
        i = int(row.get('i'))
    except Exception:  # noqa: BLE001
        continue
    if not (1 <= i <= len(items)):
        continue
    t = row.get('type')
    s = row.get('skeleton')
    if t in coach.TYPE_KEYS and items[i - 1].get('type') != t:
        items[i - 1]['type'] = t
        changed += 1
    if s in coach.SKELETON_KEYS and items[i - 1].get('skeleton') != s:
        items[i - 1]['skeleton'] = s
        changed += 1

io.open(P + '.bak_ai_tags', 'w', encoding='utf-8').write(
    io.open(P, encoding='utf-8').read())
io.open(P, 'w', encoding='utf-8').write(json.dumps(items, ensure_ascii=False, indent=1))
print('AI 重标完成，改动字段', changed, '处')
print('类型分布:', dict(Counter(x.get('type') for x in items)))
print('骨架分布:', dict(Counter(x.get('skeleton') for x in items)))
print('\n抽样:')
for it in items[:6]:
    print('  [{0}/{1}] {2}'.format(it.get('type'), it.get('skeleton'), it.get('t', '')[:36]))
