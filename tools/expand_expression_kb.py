# -*- coding: utf-8 -*-
"""扩充表达能力知识库：按 6 大模块补齐豆包方案里软件缺失的主题。

- 每个模块给定明确主题清单（覆盖结构化/说服/故事/声音肢体/即兴控场/临场心态）
- 分批调用 DeepSeek（每批 3 条），容错解析，逐条校验（字段/长度/占位词）
- 与现有条目去重（标题归一化 + 相似度），补齐 module 字段
- 写入前备份 knowledge/expression.json
"""
import difflib
import io
import json
import os
import re
import sys
import time

ROOT = r'C:\Users\lenovo\Desktop\压缩包\MorningBoard'
os.chdir(ROOT)
sys.path.insert(0, ROOT)
from app import ai_gen  # noqa: E402

KB = r'knowledge\expression.json'

TOPICS = {
    "structure": [
        "金字塔原理的纵向结构：疑问-回答链",
        "三点式表达：为什么讲三点最容易被记住",
        "问题-方案-收益（PSB）结构",
        "对比结构：用「不是…而是…」制造认知落差",
        "黄金圈 Why-How-What：从动机切入的表达顺序",
        "结论先行的三种开场方式",
        "时间线结构：按顺序讲清一件复杂的事",
        "结构化表达的一分钟自检清单",
    ],
    "persuasion": [
        "亚里士多德修辞三要素：可信度-情绪-逻辑",
        "互惠原则的正当用法",
        "承诺与一致：让对方先点头再谈正事",
        "社会认同：用同类人的行为说服",
        "权威借力：不吹嘘地建立专业感",
        "稀缺与紧迫感：何时该用、何时会反噬",
        "损失厌恶：把收益改写成损失来讲",
        "先跟后带：说服反对者的四步对话法",
    ],
    "story": [
        "微型英雄之旅：目标-困难-转折-收获",
        "好故事三要素：具体细节、情绪波动、顿悟时刻",
        "用对话代替叙述：让故事有现场感",
        "类比与比喻：把陌生的讲成熟悉的",
        "数字故事化：让数据有画面",
        "自嘲的分寸：拉近距离而不掉价",
        "30 秒故事模板与句式",
    ],
    "voice": [
        "停顿的力量：重点前后各停一秒",
        "重音转移：同一句话的三种意思",
        "语速控制：把关键句刻意放慢",
        "气息与音量：不喊也能传到最后排",
        "眼神的扇形覆盖",
        "手势开放区与站姿",
        "口头禅清理：嗯啊呃与然后",
        "收尾的下沉语气：避免升调显得没底气",
    ],
    "improv": [
        "Yes-And 接话法：先接纳再推进",
        "被质疑时的四步回应：复述-承认-立场-收尾",
        "被问到不会的问题怎么办",
        "即兴开场三选一",
        "一句话总结：把复杂的事压成一句",
        "控场：把跑题的讨论拉回主线",
        "礼貌打断与接话的技术",
        "临场忘词的三秒救场",
    ],
    "mindset": [
        "把紧张重新定义为兴奋",
        "允许停顿：停顿比「嗯」更显沉稳",
        "失误修复：说错话后的三种处理",
        "上台前五分钟流程",
        "自我对话：把「我要讲好」换成「我要讲清」",
        "观众视角：他们没你想的那么在乎",
        "复盘的三个问题",
    ],
}


def norm_title(t):
    return re.sub(r'[\s：:·、，,。.！!？?—\-“”"\'（）()【】\[\]]', '', str(t or ''))


def load_kb():
    return json.load(io.open(KB, encoding='utf-8'))


def valid(item, module):
    if not isinstance(item, dict):
        return None
    t = str(item.get('t') or '').strip()
    s = str(item.get('s') or '').strip()
    b = [str(x).strip() for x in (item.get('b') or []) if str(x).strip()]
    links = [str(x).strip() for x in (item.get('links') or []) if str(x).strip()]
    if len(t) < 6 or len(s) < 8:
        return None
    if len(b) < 3 or sum(len(x) for x in b) < 220:
        return None
    item = ai_gen._strip_placeholders({'t': t, 's': s, 'b': b[:5], 'links': links[:4]})
    item['module'] = module
    item['links'] = list(item.get('links') or [])
    return item


def gen_batch(module, topics, existing_titles):
    head = (
        "你是表达力教练，正在为一个中文「表达能力训练系统」编写知识库条目。\n"
        "请为下面每个技巧各写一条，**必须逐条对应**，不要增删：\n"
        + "\n".join("  {0}. {1}".format(i + 1, x) for i, x in enumerate(topics))
        + "\n避免与这些已存在条目重复：{0}\n".format("、".join(list(existing_titles)[:25]) or "（无）")
    )
    tpl = (
        '严格只输出一个 JSON 数组（不要 markdown 围栏、不要任何解释）：\n'
        '[{"t":"<技巧名>：<副标题>","s":"一句话说明它解决什么问题（30字内）",'
        '"b":["第1段 核心方法与步骤（100-140字，要能照着做）",'
        '"第2段 为什么有效（80-120字，可引用心理学/修辞学原理）",'
        '"第3段 具体示例（120-160字，给场景和可直接套用的原话模板）",'
        '"第4段 今天的练习动作（40-60字，可立即执行）"],'
        '"links":["延伸名词1","延伸名词2","延伸名词3"]}]\n'
    )
    tail = ("要求：b 必须 4 段且内容具体，禁止出现「技巧名」「副标题」「延伸名词」这类占位词；"
            "示例要像真实对话，不要泛泛而谈。")
    raw = ai_gen._chat(head + tpl + tail, max_tokens=2600, timeout=120)
    r = ai_gen._extract_json(raw)
    if isinstance(r, dict):
        r = [r]
    if not isinstance(r, list):
        return []
    return [x for x in (valid(v, module) for v in r) if x]


def main():
    import argparse
    ap = argparse.ArgumentParser(description='表达能力知识库扩充（AI 生成 + 校验 + 去重）')
    ap.add_argument('--module', help='只扩充指定模块：structure/persuasion/story/voice/improv/mindset')
    ap.add_argument('--topics', help='自定义主题，逗号分隔（配合 --module 使用）')
    ap.add_argument('--list', action='store_true', help='只看当前各模块条目数')
    args = ap.parse_args()

    kb = load_kb()
    from app import expression_coach as coach

    if args.list:
        mods, total = coach.module_progress()
        print('知识库共 {0} 条：'.format(total))
        for m in mods:
            print('  {0:<8} {1} 条'.format(m['name'], m['count']))
        return 0

    print('现有条目:', len(kb))

    topics_map = TOPICS
    if args.topics:
        mod = args.module or 'structure'
        assert mod in TOPICS, '未知模块：{0}（可用：{1}）'.format(mod, '/'.join(TOPICS))
        custom = [t.strip() for t in args.topics.replace('，', ',').split(',') if t.strip()]
        topics_map = {mod: custom}
        print('自定义主题 {0} 个 -> 模块 {1}'.format(len(custom), mod))
    elif args.module:
        assert args.module in TOPICS, '未知模块：{0}'.format(args.module)
        topics_map = {args.module: TOPICS[args.module]}

    # 1) 给现有条目补 module（按关键词推断，复用教练模块的规则）
    for it in kb:
        it.setdefault('module', coach._infer_module(it))
    have = {norm_title(it.get('t')) for it in kb}
    titles = {str(it.get('t') or '') for it in kb}

    added, failed = [], []
    for module, topics in topics_map.items():
        pending = [t for t in topics if norm_title(t) not in have]
        print('\n[{0}] 待生成 {1} 条'.format(module, len(pending)))
        for i in range(0, len(pending), 3):
            batch = pending[i:i + 3]
            got = []
            for attempt in (1, 2):
                try:
                    got = gen_batch(module, batch, titles)
                except Exception as e:  # noqa: BLE001
                    print('   批次异常:', type(e).__name__, e)
                    got = []
                if len(got) >= max(1, len(batch) - 1):
                    break
                time.sleep(2)
            for g in got:
                nt = norm_title(g.get('t'))
                if not nt or nt in have:
                    continue
                if any(difflib.SequenceMatcher(None, nt, h).ratio() > 0.82 for h in have):
                    continue
                have.add(nt)
                titles.add(g['t'])
                added.append(g)
                print('   + [{0}] {1}'.format(module, g['t'][:34]))
            got_topics = {norm_title(g['t'])[:6] for g in got}
            for t in batch:
                if norm_title(t)[:6] not in got_topics:
                    failed.append((module, t))
            time.sleep(1)

    if not added:
        print('\n没有新增条目（全部已存在或生成失败）')
        return 1

    io.open(KB + '.bak_expand', 'w', encoding='utf-8').write(
        io.open(KB, encoding='utf-8').read())
    kb.extend(added)
    io.open(KB, 'w', encoding='utf-8').write(json.dumps(kb, ensure_ascii=False, indent=1))
    print('\n新增 {0} 条 -> 知识库共 {1} 条（备份 {2}.bak_expand）'.format(
        len(added), len(kb), KB))
    if failed:
        print('未覆盖主题（可重跑补）：')
        for m, t in failed:
            print('   -', m, t)
    from collections import Counter
    print('模块分布:', dict(Counter(it.get('module') for it in kb)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
