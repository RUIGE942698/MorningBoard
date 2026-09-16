# -*- coding: utf-8 -*-
"""① 给老题回填 type/skeleton 标签；② 思辨题卡片显示「对撞点 / 条件化」。"""
import io
import json
import os
import shutil
import sys

ROOT = r'C:\Users\lenovo\Desktop\压缩包\MorningBoard'
os.chdir(ROOT)
sys.path.insert(0, ROOT)
from app import thinking_coach as coach  # noqa: E402

# ---------- ① 回填标签 ----------
P = r'knowledge\thinking.json'
items = json.load(io.open(P, encoding='utf-8'))
filled = 0
for it in items:
    if it.get('type') in coach.TYPE_KEYS and it.get('skeleton') in coach.SKELETON_KEYS:
        continue
    text = " ".join([str(it.get('t', '')), str(it.get('s', ''))] +
                    [str(x) for x in (it.get('ask') or [])] +
                    [str(x) for x in (it.get('pro') or [])[:1]])
    it.setdefault('type', coach.classify_type(text))
    it.setdefault('skeleton', coach.classify_skeleton(text))
    if it['type'] not in coach.TYPE_KEYS:
        it['type'] = coach.classify_type(text)
    if it['skeleton'] not in coach.SKELETON_KEYS:
        it['skeleton'] = coach.classify_skeleton(text)
    filled += 1
if filled:
    shutil.copy2(P, P + '.bak_tags')
    io.open(P, 'w', encoding='utf-8').write(json.dumps(items, ensure_ascii=False, indent=1))
print('回填标签:', filled, '条 | 题库共', len(items), '条')

from collections import Counter  # noqa: E402
print('类型分布:', dict(Counter(x.get('type') for x in items)))
print('骨架分布:', dict(Counter(x.get('skeleton') for x in items)))

# ---------- ② 界面显示对撞点/条件化 ----------
T = r'app\ui\tabs\thinking.py'
src = io.open(T, encoding='utf-8').read()
old = '''            for p in it.get("ask", []):
                tk.Label(
                    body, text="❓ " + p, font=F_SMALL, bg=_tint, fg=_ink,
                    anchor="w", justify="left", wraplength=950,
                ).pack(fill="x", padx=18, pady=4)'''
new = '''            if it.get("clash"):
                tk.Label(
                    body, text="💥 对撞点：" + it["clash"], font=F_SMALL, bg=C.CARD,
                    fg=C.MUTED_BLUE, anchor="w", justify="left", wraplength=950,
                ).pack(fill="x", padx=18, pady=(4, 2))
            if it.get("variables"):
                tk.Label(
                    body, text="🎚 关键变量：" + "、".join(it["variables"]), font=F_TINY,
                    bg=C.CARD, fg=C.SUB, anchor="w", justify="left", wraplength=950,
                ).pack(fill="x", padx=18)
            if it.get("conditional"):
                tk.Label(
                    body, text="🧩 条件化结论：" + it["conditional"], font=F_SMALL,
                    bg=_tint, fg=_ink, anchor="w", justify="left", wraplength=950,
                ).pack(fill="x", padx=18, pady=(2, 2))
            for p in it.get("ask", []):
                tk.Label(
                    body, text="❓ " + p, font=F_SMALL, bg=_tint, fg=_ink,
                    anchor="w", justify="left", wraplength=950,
                ).pack(fill="x", padx=18, pady=4)'''
assert src.count(old) == 1, '界面锚点未命中'
src = src.replace(old, new, 1)
shutil.copy2(T, T + '.bak_clash')
io.open(T, 'w', encoding='utf-8').write(src)
import py_compile  # noqa: E402
py_compile.compile(T, doraise=True)
print('界面已加「对撞点 / 关键变量 / 条件化」显示（备份 .bak_clash），语法 OK')
