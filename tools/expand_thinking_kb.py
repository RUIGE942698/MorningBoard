# -*- coding: utf-8 -*-
"""思辨知识库扩广度：议题题库 + 思维工具 + 谬误库。

- 议题：按 10 类骨架 × 多领域生成，每题带 type（四类延伸题）/skeleton（骨架）/domain
- 工具：论证与决策工具（图尔敏、钢人原则、贝叶斯、二阶效应…）
- 谬误：常见逻辑与统计谬误
分批调用 DeepSeek + 校验 + 去重 + 备份（.bak_expand）
用法：
  python tools/expand_thinking_kb.py --topics     只扩题库
  python tools/expand_thinking_kb.py --tools      只扩工具
  python tools/expand_thinking_kb.py --fallacies  只扩谬误
  python tools/expand_thinking_kb.py --all
"""
import argparse
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

TOPICS_FILE = r'knowledge\thinking.json'
TOOLS_FILE = r'knowledge\thinking_tools.json'
FALL_FILE = r'knowledge\fallacies.json'

# 每个骨架给 2 个种子方向（领域提示），AI 扩成 6 题
SEEDS = {
    "resource": "学位与学区、病床与挂号、编制与名额、科研经费分配、水资源配额、平台流量分配",
    "efficiency": "双减与升学竞争、最低工资、累进税、国企效率、平台算法派单、绩效工资",
    "generation": "延迟退休、养老金缺口、气候赔偿、核电留给后代、城市负债、遗产税",
    "regulation": "算法推荐监管、直播带货、AI 生成内容标识、校外培训、网约车准入、数据出境",
    "rights": "人脸识别与隐私、公共场所监控、未成年人网络保护、记者采访权、肖像权与 AI 换脸",
    "externality": "碳排放与碳税、外卖包装、噪音与广场舞、城市拥堵收费、电子烟、数据中心能耗",
    "information": "医患信息不对称、二手车市场、学历信号、食品标签、征信与评分、预制菜标识",
    "incentive": "考核指标造假、扶贫骗补、环保一刀切、论文数量考核、外卖骑手超时罚款、招商内卷",
    "moral": "自动驾驶电车难题、器官分配、安乐死、动物实验、战争中的平民伤亡、AI 替人做决定",
    "culture": "彩礼与婚俗、传统节日商业化、方言保护、集体主义与个人主义、国潮与全球化、家族养老",
}

TOOLS_SEEDS = [
    "图尔敏论证模型", "钢人原则：先构造对方最强版本", "反事实推理：与什么比", "奥卡姆剃刀",
    "贝叶斯更新：先验与证据权重", "成本收益分析与贴现", "边际分析：多一单位值不值",
    "机会成本：你放弃的那个选项", "二阶效应：然后呢，再然后呢", "激励相容：让制度自己长出好行为",
    "博弈论：囚徒困境与重复博弈", "公地悲剧与产权界定", "信息不对称与信号传递",
    "幸存者偏差", "回归均值：极端之后会回落", "相关性不等于因果", "随机对照与自然实验",
    "决策矩阵与加权评分", "事前验尸（Pre-mortem）", "红队思维：故意攻击自己的结论",
    "类比推理的边界", "必要与充分条件", "系统动力学：反馈回路与延迟", "规模效应与边际递减",
    "外部性内部化：庇古税与科斯定理", "道德风险与逆向选择", "路径依赖与锁定效应",
    "双盲与安慰剂对照",
]

FALLACY_SEEDS = [
    "滑坡谬误", "诉诸权威", "循环论证", "以偏概全", "虚假两难", "人身攻击", "红鲱鱼",
    "诉诸情感", "举证责任倒置", "后此谬误（时间先后当因果）", "合成谬误与分割谬误",
    "轶事证据", "数字误导：绝对值与相对值", "转移话题（Whataboutism）", "稻草人谬误的进阶变体",
    "幸存者偏差谬误", "平均数的陷阱", "断章取义", "虚假相关", "诉诸传统",
    "诉诸自然", "以势压人（诉诸武力/权力）", "错误类比", "特例辩护（不可证伪）",
    "以沉默为证", "赌徒谬误", "确认偏误", "锚定效应误用",
]


def norm_title(t):
    return re.sub(r'[\s：:·、，,。.！!？?—\-“”"\'（）()【】\[\]]', '', str(t or ''))


def load_list(path):
    d = json.load(io.open(path, encoding='utf-8'))
    return d if isinstance(d, list) else (d.get('items') or [])


def save_list(path, items):
    io.open(path + '.bak_expand', 'w', encoding='utf-8').write(
        io.open(path, encoding='utf-8').read())
    io.open(path, 'w', encoding='utf-8').write(json.dumps(items, ensure_ascii=False, indent=1))


# ------------------------------------------------------------------ 题库
def topic_prompt(skeleton, name, seeds):
    return (
        "你在为一个中文思辨训练系统出题。议题骨架是「{0}」（{1}）。\n"
        "请围绕这些方向出 3 道**具体的中文议题**：{2}\n"
        "要求每道题都是真实社会争议（不是抽象哲学题），正反双方都有像样的理由。\n"
        "严格只输出 JSON 数组（不要 markdown 围栏、不要解释）：\n"
        '[{{"t":"议题标题（一问句或争议命题，25字内）","s":"一句话背景或延伸问法（35字内）",'
        '"pro":["正方论点1（35-60字，给机制或证据方向）","正方论点2","正方论点3"],'
        '"con":["反方论点1（35-60字）","反方论点2","反方论点3"],'
        '"ask":["一个直击要害的追问（25字内）"],'
        '"type":"balance|attribution|solution|impact 之一",'
        '"skeleton":"{0}","domain":"教育|医疗|住房|科技伦理|经济与就业|法律与权利|环境与气候|家庭与代际|职场与组织|国际与治理 之一"}}]\n'
        "注意：pro/con 各 3 条，每条都要有具体机制（谁获利、谁受损、什么条件下成立），不要空喊口号。"
    ).format(name, skeleton, seeds)


def gen_topics(skeleton, name, seeds):
    raw = ai_gen._chat(topic_prompt(skeleton, name, seeds), max_tokens=2600, timeout=120)
    r = ai_gen._extract_json(raw)
    if isinstance(r, dict):
        r = [r]
    if not isinstance(r, list):
        return []
    out = []
    for x in r:
        if not isinstance(x, dict):
            continue
        pro = [str(v).strip() for v in (x.get('pro') or []) if str(v).strip()]
        con = [str(v).strip() for v in (x.get('con') or []) if str(v).strip()]
        if len(pro) < 3 or len(con) < 3 or len(str(x.get('t') or '')) < 6:
            continue
        out.append({
            't': str(x['t']).strip(),
            's': str(x.get('s') or '').strip(),
            'pro': pro[:3], 'con': con[:3],
            'ask': [str(v).strip() for v in (x.get('ask') or []) if str(v).strip()][:2],
            'type': x.get('type') if x.get('type') in ('balance', 'attribution', 'solution', 'impact') else '',
            'skeleton': skeleton,
            'domain': str(x.get('domain') or '').strip(),
        })
    return out


# ------------------------------------------------------------------ 工具 / 谬误
def tools_prompt(names):
    return (
        "为中文思辨训练系统写「思维工具」词条，每个工具 3-4 段：\n"
        + "\n".join("  {0}. {1}".format(i + 1, n) for i, n in enumerate(names)) +
        "\n严格只输出 JSON 数组：\n"
        '[{"t":"工具名：副标题","s":"一句话说明它能解决什么问题（30字内）",'
        '"b":["第1段：是什么与关键结构（100-140字）",'
        '"第2段：怎么用（步骤，100-140字）",'
        '"第3段：一个具体争议/场景的例子（100-140字）",'
        '"第4段：常见误用或边界（60-100字）"],'
        '"links":["延伸名词1","延伸名词2","延伸名词3"]}]\n'
        "禁止出现「工具名」「副标题」「延伸名词」这类占位词。"
    )


def fallacies_prompt(names):
    return (
        "为中文思辨训练系统写「逻辑与统计谬误」词条，每个 3 段：\n"
        + "\n".join("  {0}. {1}".format(i + 1, n) for i, n in enumerate(names)) +
        "\n严格只输出 JSON 数组：\n"
        '[{"t":"谬误名：一句话特征","s":"一句话说明它怎么骗人（30字内）",'
        '"b":["第1段：定义与识别特征（80-120字）",'
        '"第2段：一个具体的中国语境例子（100-140字，含原话）",'
        '"第3段：破解方法（80-120字）"],'
        '"links":["延伸名词1","延伸名词2","延伸名词3"]}]\n'
        "禁止出现占位词。"
    )


def valid_simple(x, min_b=3):
    if not isinstance(x, dict):
        return None
    b = [str(v).strip() for v in (x.get('b') or []) if str(v).strip()]
    if len(str(x.get('t') or '')) < 4 or len(b) < min_b:
        return None
    return ai_gen._strip_placeholders({
        't': str(x['t']).strip(), 's': str(x.get('s') or '').strip(), 'b': b[:5],
        'links': [str(v).strip() for v in (x.get('links') or []) if str(v).strip()][:4]})


def gen_simple(prompt_fn, batch, existing):
    raw = ai_gen._chat(prompt_fn(batch), max_tokens=2800, timeout=120)
    r = ai_gen._extract_json(raw)
    if isinstance(r, dict):
        r = [r]
    if not isinstance(r, list):
        return []
    out, have = [], {norm_title(t) for t in existing}
    for x in r:
        v = valid_simple(x)
        if not v:
            continue
        nt = norm_title(v['t'])
        if nt in have or any(difflib.SequenceMatcher(None, nt, h).ratio() > 0.85 for h in have):
            continue
        have.add(nt)
        out.append(v)
    return out


def expand_topics():
    items = load_list(TOPICS_FILE)
    have = {norm_title(x.get('t')) for x in items}
    import app.thinking_coach as coach  # noqa: E402
    added = 0
    for sk, seeds in SEEDS.items():
        name = coach.skeleton_name(sk)
        got = []
        for attempt in (1, 2):
            try:
                got = gen_topics(sk, name, seeds)
            except Exception as e:  # noqa: BLE001
                print('  [{0}] 批次异常: {1}'.format(sk, e))
                got = []
            if len(got) >= 2:
                break
            time.sleep(2)
        for g in got:
            nt = norm_title(g['t'])
            if nt in have:
                continue
            have.add(nt)
            items.append(g)
            added += 1
        print('  [{0}] 新增 {1} 题（累计 {2}）'.format(name, len(got), len(items)))
        time.sleep(1)
    if added:
        save_list(TOPICS_FILE, items)
    return added, len(items)


def expand_simple(path, seeds, prompt_fn, label, batch_size=4):
    items = load_list(path)
    have = {x.get('t') for x in items}
    todos = [s for s in seeds if s not in have]
    added = 0
    for i in range(0, len(todos), batch_size):
        batch = todos[i:i + batch_size]
        got = []
        for attempt in (1, 2):
            try:
                got = gen_simple(prompt_fn, batch, have)
            except Exception as e:  # noqa: BLE001
                print('  [{0}] 批次异常: {1}'.format(label, e))
                got = []
            if got:
                break
            time.sleep(2)
        for g in got:
            items.append(g)
            have.add(g['t'])
            added += 1
        print('  [{0}] 本批 +{1}（累计 {2}）'.format(label, len(got), len(items)))
        time.sleep(1)
    if added:
        save_list(path, items)
    return added, len(items)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--topics', action='store_true')
    ap.add_argument('--tools', action='store_true')
    ap.add_argument('--fallacies', action='store_true')
    ap.add_argument('--all', action='store_true')
    a = ap.parse_args()
    do = {'topics': a.topics or a.all, 'tools': a.tools or a.all,
          'fallacies': a.fallacies or a.all}
    if not any(do.values()):
        do = {'topics': True, 'tools': True, 'fallacies': True}

    t0 = time.time()
    if do['topics']:
        print('=== 扩议题题库 ===')
        n, total = expand_topics()
        print('题库新增 {0} 题，共 {1} 题'.format(n, total))
    if do['tools']:
        print('=== 扩思维工具 ===')
        n, total = expand_simple(TOOLS_FILE, TOOLS_SEEDS, tools_prompt, 'tools')
        print('工具新增 {0} 条，共 {1} 条'.format(n, total))
    if do['fallacies']:
        print('=== 扩谬误库 ===')
        n, total = expand_simple(FALL_FILE, FALLACY_SEEDS, fallacies_prompt, 'fallacies')
        print('谬误新增 {0} 条，共 {1} 条'.format(n, total))
    print('\n总耗时 %.0f 秒' % (time.time() - t0))


if __name__ == '__main__':
    main()
