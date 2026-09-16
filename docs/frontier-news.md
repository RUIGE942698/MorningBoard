# 前沿速报 v2（六维百分制 + 领域配额）

> 对标用户提供的"每日 25 条高质量科技情报筛选方案"落地。
> 输出：**每天 25 条** —— AI 10 / 科技 4 / 物理 3 / 医学 3 / 生物 3 / 数学 2。

## 一、信源分层（实测可达的 36 个源；界面入口 33 个）
| 级别 | 权威分 | 信源 |
|---|---|---|
| **S 一手/权威** | 20 | Nature、Science、Cell、**Nature Medicine、Nature Biotechnology、Nature Physics**、**The Lancet、NEJM、JAMA、PNAS**、arXiv（cs.AI / math.RT / math.GT / quant-ph / astro-ph）、DeepMind 官方博客、WHO |
| **A 优质编译/预印本** | 14 | MIT Technology Review、Quanta、Simons Foundation、**IEEE Spectrum、Ars Technica**、**eLife**、量子位、InfoQ 中文、bioRxiv、medRxiv |
| **B 高信噪比社区/媒体** | 8 | Hacker News、Phys.org、ScienceNews、**Solidot**、雷峰网、极客公园、IT 之家、少数派、掘金 |

> 2026-09-12 增补 11 个源（加粗部分）：此前医学 2 源 / 生物 2 源填不满配额（医学 3 / 生物 3），缺额被 AI 组吸收导致偏科；补源后实测**首次完全命中配额**（AI 10 / 科技 4 / 物理 3 / 医学 3 / 生物 3 / 数学 2），一手占比 28% → **40%**（达标）。单源上限 2 条以防新源刷屏。

预印本（bioRxiv/medRxiv）定为 A 而非 S：未经同行评审，与已发表论文区分开，避免预印本洪流淹没其他内容。

**实测不可达（已放弃）**：OpenAI / Anthropic / Meta 官方博客、Reddit r/MachineLearning、Quanta(HTTP 侧)、FDA、PapersWithCode、Semantic Scholar（429）、机器之心（站点为 JS 空壳，无 RSS）。

## 二、六维百分制
| 维度 | 权重 | 实现 |
|---|---|---|
| 时效 | 30 | `30·e^(−Δt/τ)`，τ 按领域：AI 1.5 天、科技 2.5 天、生物/医学 3 天、数学/物理 5 天 |
| 信源权威 | 20 | S 20 / A 14 / B 8 |
| 含金量 | 20 | 证据分级：代码·数据（≤4）＋随机对照·预注册（≤4）＋方法（≤2）＋结果（≤2）＋原创深度（≤3）＋一手来源（+2）＋引用（≤3） |
| 影响力 | 15 | **真实数据**：OpenAlex 引用数、Hacker News 分数/评论数，另加跨源共识（同题 2 源 +3.5、≥3 源 +6） |
| 新颖性 | 10 | SimHash 标题指纹 vs 近 3 天历史 + 本轮已选，相似度反向计分 |
| 领域相关 | 5 | 领域词表命中强度；另对 AI +5、科技 +2 的**用户偏好加权** |

淘汰线 **50 分**；桌面弹窗阈值 **70 分**（2026-09-12 由 75 下调）。

## 三、去重与事件聚类
- SimHash 相似度 **>0.9 判重复合并**，**0.85–0.9 视为同一事件簇只留最高分**（embedding 服务国内不可用，故用指纹近似）
- 记录 7 天历史（当前保留 3 天窗口参与新颖性判定）

## 四、配额与硬约束（实测达成）
| 约束 | 目标 | 实测 |
|---|---|---|
| 领域配额 | AI 10 / 科技 4 / 物理 3 / 医学 3 / 生物 3 / 数学 2 | ✅ 完全命中 |
| 单源上限 | ≤3 条 | ✅ 15 个源参与，无源超 3 |
| 一手/论文占比 | ≥40%（方案原要求 60%，因未审预印本过多会伤质量而下调） | ✅ 44% |
| 48h 内占比 | ≥70% | ✅ 100% |

配额未满时按 **AI → 科技 → 物理 → 医学 → 生物 → 数学** 的优先级补足，保证 AI/科技为主。

## 五、管线与耗时
采集 25 源（约 500 条/天）→ 领域判定 → 六维打分 → 前 12 条查真实影响力 → 去重聚类 → 配额选条 → 英文条目 AI 生成中文标题与摘要（按 URL 缓存）→ 写 `cache/frontier.json`。
实测单次 **约 50 秒**（远低于方案的 30–40 分钟，因为源量与 NLP 环节更轻）。

## 六、与方案的差异（务实取舍）
| 方案要求 | 落地情况 |
|---|---|
| S/A/B/C 四级 + 引用尖峰信号 | C 级仅保留 OpenAlex 引用数；Google Scholar / Semantic Scholar 不可达 |
| embedding 语义聚类 0.85 | 无可用 embedding 服务 → SimHash 指纹近似 |
| 2000–5000 条/日采集 | 约 500 条/日（国内可达源上限） |
| 30 条候选 → 人工复核砍到 25 | 未做人工复核环节（可后续加"待复核"视图） |
| 点击率/漏报率反馈闭环 | 未实现（需界面埋点 + 每周回归，可作为下一步） |

## 七、常用命令
```powershell
python -m app.frontier --refresh --dump   # 抓取并打印六维明细
python -m app.frontier --check            # 看值得推送的新条目
python frontier_watch.py --once           # 跑一次检查（≥70 分才弹窗）
```
调参位置：`app/frontier.py` 顶部（QUOTA / MIN_SCORE / PUSH_MIN_SCORE / TAU_DAYS / DOMAIN_BOOST / 各约束阈值）。

## 八、2026-09-12 修复与调整记录

| 变更 | 原因 | 效果（实测） |
|---|---|---|
| **信源 25 → 36**（+11：Nature Medicine / Nature Biotechnology / Nature Physics / The Lancet / NEJM / JAMA / PNAS / eLife / IEEE Spectrum / Ars Technica / Solidot） | 医学 2 源、生物 2 源填不满配额（各需 3），缺额被 AI 组吸收导致偏科 | **首次完全命中配额**（ai10/tech4/physics3/med3/bio3/math2）；一手占比 28% → 40% |
| 入口 22 → 33（新源官网首页） | 与信源同步 | 界面「信源入口 ▾」 |
| 新源单源上限 2 条（SOURCE_MAX） | 防新源刷屏 | 单源最多 2–3 条 |
| NOISE_WORDS 补期刊样板字（audio highlights / in this issue / correction / retraction…）+ 社会案件事故类（被捕/警方/审判/事故…） | NEJM/PNAS 常带非内容条目；Waymo 类社会新闻混进科技组 | 噪声条目被扣分淘汰 |
| **弹窗阈值 75 → 70** | 用户要求更易触发 | 达标条目即可弹 |
| **修复 novelty 自我惩罚 BUG** | 每次构建都会把入选条目写入历史（`save_history`），同日二次构建时条目命中**自己**的指纹（sim=1.0）→ 新颖性归零、分数被砍最多 10 分。实测同一批内容 71.8 → 70.0 → 68.3 持续下滑，导致**弹窗阈值永远无法达到** | 新颖性只与"更早日期"历史比对（跨天去重本意保留）。修复后同日最高分 68.3 → **78.3**，弹窗恢复触发（23:35 实测推送 2 条） |

**已知副作用**：信源增至 36 个后，单次全量检查耗时从约 50 秒升至 **1.5–6 分钟**（视网络与源响应波动），后台每小时一次无感，但界面"缓存超 30 分钟自动刷新"会有明显等待。可调 `ENRICH_LIMIT` / `TRANSLATE_LIMIT` 或改增量抓取。
