# -*- coding: utf-8 -*-
"""在当前版本上重新应用「补源 + novelty 修复 + 弹窗阈值 70」。

背景：2026-09-12 23:36 另一个会话用其自身副本覆盖了 app/frontier.py，
带回了好功能（reload_terms / all_known_terms 等），但也覆盖掉了本会话的三项改动。
本脚本幂等：已存在则跳过，逐项断言，带时间戳备份。
"""
import io
import os
import shutil
from datetime import datetime

ROOT = r'C:\Users\lenovo\Desktop\压缩包\MorningBoard'
os.chdir(ROOT)
P = 'app/frontier.py'
src = io.open(P, encoding='utf-8').read()
orig = src
done, skipped = [], []


def sub(old, new, label):
    global src
    if new.split('\n')[0] in src and old not in src:
        skipped.append(label)
        return
    n = src.count(old)
    assert n == 1, '[%s] 锚点命中 %d 次' % (label, n)
    src = src.replace(old, new, 1)
    done.append(label)


NEW_S = '''    ("Nature Medicine", "https://www.nature.com/nm.rss", "S", "en", "rss", "medicine"),
    ("Nature Biotechnology", "https://www.nature.com/nbt.rss", "S", "en", "rss", "biology"),
    ("Nature Physics", "https://www.nature.com/nphys.rss", "S", "en", "rss", "physics"),
    ("The Lancet", "https://www.thelancet.com/rssfeed/lancet_current.xml",
     "S", "en", "rss", "medicine"),
    ("NEJM", "https://www.nejm.org/action/showFeed?jc=nejm&type=etoc&feed=rss",
     "S", "en", "rss", "medicine"),
    ("JAMA", "https://jamanetwork.com/rss/site_3/67.xml", "S", "en", "rss", "medicine"),
    ("PNAS", "https://www.pnas.org/action/showFeed?type=etoc&feed=rss&jc=pnas",
     "S", "en", "rss", "biology"),
'''
NEW_A = '''    ("eLife", "https://elifesciences.org/rss/recent.xml", "A", "en", "rss", "biology"),
    ("IEEE Spectrum", "https://spectrum.ieee.org/feeds/feed.rss", "A", "en", "rss", "tech"),
    ("Ars Technica", "https://feeds.arstechnica.com/arstechnica/index",
     "A", "en", "rss", "tech"),
'''
NEW_B = '''    ("Solidot", "https://www.solidot.org/index.rss", "B", "zh", "rss", "tech"),
'''
NEW_SITES = '''    {"name": "Nature Medicine", "url": "https://www.nature.com/nm/"},
    {"name": "Nature Biotechnology", "url": "https://www.nature.com/nbt/"},
    {"name": "Nature Physics", "url": "https://www.nature.com/nphys/"},
    {"name": "The Lancet", "url": "https://www.thelancet.com/"},
    {"name": "NEJM", "url": "https://www.nejm.org/"},
    {"name": "JAMA", "url": "https://jamanetwork.com/"},
    {"name": "PNAS", "url": "https://www.pnas.org/"},
    {"name": "eLife", "url": "https://elifesciences.org/"},
    {"name": "IEEE Spectrum", "url": "https://spectrum.ieee.org/"},
    {"name": "Ars Technica", "url": "https://arstechnica.com/"},
    {"name": "Solidot", "url": "https://www.solidot.org/"},
'''

sub('    ("WHO", "https://www.who.int/rss-feeds/news-english.xml", "S", "en", "rss", "medicine"),\n',
    '    ("WHO", "https://www.who.int/rss-feeds/news-english.xml", "S", "en", "rss", "medicine"),\n' + NEW_S,
    '信源 +S(7)')
sub('    ("Quanta", "https://www.quantamagazine.org/feed/", "A", "en", "rss", None),\n',
    '    ("Quanta", "https://www.quantamagazine.org/feed/", "A", "en", "rss", None),\n' + NEW_A,
    '信源 +A(3)')
sub('     "B", "zh", "juejin", "tech"),\n',
    '     "B", "zh", "juejin", "tech"),\n' + NEW_B,
    '信源 +B(1)')
sub('    {"name": "Hacker News", "url": "https://news.ycombinator.com/"},\n]',
    '    {"name": "Hacker News", "url": "https://news.ycombinator.com/"},\n' + NEW_SITES + ']',
    '入口 +11')
sub('              "arXiv quant-ph": 1, "arXiv astro-ph": 1}',
    '              "arXiv quant-ph": 1, "arXiv astro-ph": 1,\n'
    '              "The Lancet": 2, "NEJM": 2, "JAMA": 2, "PNAS": 2,\n'
    '              "Nature Medicine": 2, "Nature Biotechnology": 2,\n'
    '              "eLife": 2, "IEEE Spectrum": 2, "Ars Technica": 2, "Solidot": 2}',
    'SOURCE_MAX')
sub('PAPER_SOURCES = {"arXiv cs.AI", "bioRxiv", "medRxiv", "Cell", "Nature", "Science",\n'
    '                 "Simons Foundation"}',
    'PAPER_SOURCES = {"arXiv cs.AI", "bioRxiv", "medRxiv", "Cell", "Nature", "Science",\n'
    '                 "Simons Foundation", "Nature Medicine", "Nature Biotechnology",\n'
    '                 "Nature Physics", "The Lancet", "NEJM", "JAMA", "PNAS", "eLife"}',
    'PAPER_SOURCES')
sub('    "玄学", "道统", "紫微", "风水", "占卜", "八字", "预言",\n]',
    '    "玄学", "道统", "紫微", "风水", "占卜", "八字", "预言",\n'
    '    # 期刊样板条目（非内容）\n'
    '    "audio highlights", "in this issue", "correction", "erratum", "retraction",\n'
    '    "call for papers", "editorial board", "author correction", "table of contents",\n'
    '    # 社会案件/事故类（避免伪装成科技新闻混入）\n'
    '    "被捕", "警方", "审判", "判决", "量刑", "事故", "坠机", "车祸", "失火",\n]',
    'NOISE_WORDS')
sub('    hist = load_history()\n'
    '    cutoff = (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d")\n'
    '    hist_hashes = [h.get("h") for h in hist\n'
    '                   if h.get("h") and (h.get("date") or "") >= cutoff]',
    '    hist = load_history()\n'
    '    cutoff = (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d")\n'
    '    today_str = datetime.now().strftime("%Y-%m-%d")\n'
    '    # 只与"更早日期"的历史比对：同一天重复构建时，条目会命中自己刚写入历史的\n'
    '    # 指纹（sim=1.0）导致新颖性归零、分数持续下滑（实测 71.8 -> 70.0 -> 68.3，\n'
    '    # 使弹窗阈值永远无法达到）。跨天去重的本意不变。\n'
    '    hist_hashes = [h.get("h") for h in hist\n'
    '                   if h.get("h") and cutoff <= (h.get("date") or "") < today_str]',
    'novelty 自我惩罚修复')
sub('PUSH_MIN_SCORE = 75.0       # 桌面弹窗阈值',
    'PUSH_MIN_SCORE = 70.0       # 桌面弹窗阈值（2026-09-12 由 75 下调）',
    '弹窗阈值 70')

if src != orig:
    stamp = datetime.now().strftime('%m%d-%H%M')
    shutil.copy2(P, '%s.bak_reapply_%s' % (P, stamp))
    io.open(P, 'w', encoding='utf-8').write(src)
    print('已写入；备份 -> %s.bak_reapply_%s' % (P, stamp))
else:
    print('无需修改（全部已存在）')
print('应用:', done)
print('跳过（已存在）:', skipped)

import py_compile  # noqa: E402
py_compile.compile(P, doraise=True)
import sys  # noqa: E402
sys.path.insert(0, os.getcwd())
import app.frontier as fr  # noqa: E402
print('\n复验 -> SOURCES:', len(fr.SOURCES), '| SITES:', len(fr.SITES),
      '| 阈值:', fr.PUSH_MIN_SCORE)
from collections import Counter  # noqa: E402
print('按领域:', dict(Counter(s[5] or '通用' for s in fr.SOURCES)))
