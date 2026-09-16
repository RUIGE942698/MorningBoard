# -*- coding: utf-8 -*-
"""让 AI 表达课的「今天就用出去」永不缺失：提示词强化 + 程序兜底。"""
import io
import os
import shutil

ROOT = r'C:\Users\lenovo\Desktop\压缩包\MorningBoard'
os.chdir(ROOT)

# 1) 提示词：把 drill 提前并要求必填
A = 'app/ai_gen.py'
s = io.open(A, encoding='utf-8').read()
old = '''        '{"t":"<真实技巧名>：<副标题>","s":"一句话说明这个技巧解决什么问题（25字内）",'
        '"module":"structure|persuasion|story|voice|improv|mindset 之一",'
        '"b":["第1段：核心方法/步骤（约80字）","第2段：为什么有效（约80字）",'
        '"第3段：一个具体可模仿的示例（约120字，给场景和原话模板）","第4段：常见错误与纠正（约60字）"],'
        '"drill":"今天的练习动作（40字内，必须可验证：录 2 分钟/读一段/写一句，含具体要求）",'
        '"links":["延伸名词1","延伸名词2","延伸名词3"]}\\n"'''
new = '''        '{"t":"<真实技巧名>：<副标题>","s":"一句话说明这个技巧解决什么问题（25字内）",'
        '"module":"structure|persuasion|story|voice|improv|mindset 之一",'
        '"drill":"今天的练习动作（必填！40字内，可验证：录 2 分钟/读一段/写一句，含具体要求）",'
        '"b":["第1段：核心方法/步骤（约80字）","第2段：为什么有效（约80字）",'
        '"第3段：一个具体可模仿的示例（约120字，给场景和原话模板）","第4段：常见错误与纠正（约60字）"],'
        '"links":["延伸名词1","延伸名词2","延伸名词3"]}\\n"'''
assert s.count(old) == 1, '提示词锚点未命中'
s = s.replace(old, new, 1)
old2 = '        "b 至少 4 段；示例必须具体（给出场景和原话模板）；links 给 3 个延伸名词；drill 要能今晚就做完。\\n"'
new2 = ('        "b 至少 4 段；示例必须具体（给出场景和原话模板）；links 给 3 个延伸名词；'
        'drill 字段必须存在且能今晚就做完（缺失视为不合格）。\\n"')
assert s.count(old2) == 1, '尾部要求锚点未命中'
s = s.replace(old2, new2, 1)
shutil.copy2(A, A + '.bak_drill')
io.open(A, 'w', encoding='utf-8').write(s)
print('ai_gen: 提示词已强化（备份 .bak_drill）')

# 2) generate.py：AI 课缺 drill 时用当天即兴题目兜底
G = 'app/generate.py'
g = io.open(G, encoding='utf-8').read()
anchor = '''            ai_status["expression"] = bool(ai_expression)'''
assert g.count(anchor) == 1, 'generate 锚点未命中'
inject = '''            if ai_expression and not ai_expression.get("drill"):
                # 兜底：AI 偶尔漏掉 drill 字段，用当天即兴题目补上，保证「今天就用出去」不空
                try:
                    from app import expression_coach as _coach
                    _plan = _coach.today_plan()
                    for _b in (_plan.get("blocks") or []):
                        if _b.get("key") == "improv":
                            ai_expression["drill"] = _b.get("prompt")
                            break
                except Exception:  # noqa: BLE001
                    pass
            ai_status["expression"] = bool(ai_expression)'''
g = g.replace(anchor, inject, 1)
shutil.copy2(G, G + '.bak_drill')
io.open(G, 'w', encoding='utf-8').write(g)
import py_compile  # noqa: E402
py_compile.compile(A, doraise=True)
py_compile.compile(G, doraise=True)
print('generate: 已加 drill 兜底（备份 .bak_drill），语法 OK')
