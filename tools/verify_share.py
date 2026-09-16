# -*- coding: utf-8 -*-
"""分享包出厂校验：新模块/新库/文档是否齐全 + 个人信息是否抹净。"""
import io
import json
import os
import zipfile

ZIP = r'C:\Users\lenovo\Desktop\压缩包\MorningBoard_分享版_一键安装.zip'
z = zipfile.ZipFile(ZIP)
names = z.namelist()
print('文件数:', len(names))
print('体积: {0} KB'.format(round(os.path.getsize(ZIP) / 1024, 1)))

print('\n--- 必须包含（本次新增的功能与库）---')
need = [
    'MorningBoard_Share/app/expression_coach.py',
    'MorningBoard_Share/app/thinking_coach.py',
    'MorningBoard_Share/app/practice_bridge.py',
    'MorningBoard_Share/app/frontier.py',
    'MorningBoard_Share/app/mailer.py',
    'MorningBoard_Share/knowledge/expression.json',
    'MorningBoard_Share/knowledge/expression_practice.json',
    'MorningBoard_Share/knowledge/thinking.json',
    'MorningBoard_Share/knowledge/thinking_system.json',
    'MorningBoard_Share/knowledge/thinking_tools.json',
    'MorningBoard_Share/knowledge/fallacies.json',
    'MorningBoard_Share/docs/表达能力提升方案.md',
    'MorningBoard_Share/docs/思辨训练方案.md',
    'MorningBoard_Share/docs/前沿速报使用指南.md',
    'MorningBoard_Share/tools/expand_expression_kb.py',
    'MorningBoard_Share/tools/expand_thinking_kb.py',
    'MorningBoard_Share/一键安装.bat',
    'MorningBoard_Share/README.md',
]
for n in need:
    print('  ', ('OK  ' if n in names else 'MISS'), n.replace('MorningBoard_Share/', ''))

print('\n--- 必须排除（隐私/无用）---')
bad = {
    '个人缓存 cache/': [n for n in names if '/cache/' in n],
    'git 仓库': [n for n in names if '/.git/' in n],
    '开发备份 .bak*': [n for n in names if '.bak' in n],
    '日志 .log': [n for n in names if n.endswith('.log')],
}
for k, v in bad.items():
    print('  ', ('OK  ' if not v else 'BAD '), k, ('（{0} 个）'.format(len(v)) if v else ''))

cfg = json.loads(z.read('MorningBoard_Share/config.json').decode('utf-8'))
m = cfg.get('mail') or {}
leak = [k for k in ('sender', 'to', 'auth_code') if m.get(k)]
print('\n--- 邮件配置 ---')
print('   mail.enabled:', m.get('enabled'), '| 密钥泄漏:', leak or '无')
print('   AI 配置:', json.dumps(cfg.get('ai') or {}, ensure_ascii=False)[:120])

# 库条数
for f, label in (('knowledge/expression.json', '表达知识库'),
                 ('knowledge/thinking.json', '思辨题库'),
                 ('knowledge/thinking_tools.json', '思维工具'),
                 ('knowledge/fallacies.json', '谬误库')):
    try:
        d = json.loads(z.read('MorningBoard_Share/' + f).decode('utf-8'))
        items = d if isinstance(d, list) else (d.get('items') or [])
        print('   包内{0}: {1} 条'.format(label, len(items)))
    except Exception as e:  # noqa: BLE001
        print('   包内{0}: 读取失败 {1}'.format(label, e))
