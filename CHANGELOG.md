# Changelog

## Unreleased

- 细化性价比绝对价格阶梯：新增 `$1/$3/$5+` 档位，避免高价模型只因 IQ 略高就压过低价模型。
- 增加真实候选组合的回归测试，并同步仓库示例配置与运行侧配置。

## 0.2.4 — 2026-08-26

- 同步 noon-news 标题规则：英文原文标题后使用“中文对照翻译”，并与事实描述保持分离；更新 active Prompt、输出契约、Skill 说明与契约测试。

## 0.2.3 — 2026-08-25

- 性价比 Top3 改为使用绝对价格阶梯系数：价格不超过 $0.30、$0.50 和更高档位分别使用 1.00、0.98、0.90；不再用连续的价格幂指数放大低价差异。
- 同步更新 CodexRadar 排名配置、runtime 脚本和回归测试；保留旧价格指数配置的兼容读取。

## 0.2.2 — 2026-08-10

午间简报（noon-news）来源样式优化：

- 来源不再独立成行或并入事实句，改为单独一行引用块（`> 来源：`）呈现；链接以 Markdown 嵌入，正文不显示 URL 明文。
- 所有来源统一用 `•` 连接；同渠道去重（渠道只写一次，媒体 `•` 连接）。
- 每条新闻最多 2 个渠道，来源渠道超过 2 个时只保留前 2 个并在行末加 `+N`。
- 来源链接文字内冒号一律替换为 `•`（内容保留，如 `X：Boris Cherny` → `X•Boris Cherny`）；`公众号` 统一替换为 `WX`。
- 同步更新 `news-brief-v2.md`、`docs/output-contracts.md`、`skills/noon-news/SKILL.md` 与契约测试。

## 0.2.1 — 2026-08-10

- 新增 `install/install.py doctor`：组件完整性检查（入口、lib 哈希、配置），面向安装/更新 Agent，输出按组件分组；状态分 `ok` / `warn`（可选提示）/ `error`（安装损坏），仅存在 `error` 时退出码为 1。
- doctor 可选提示覆盖：外部 skill 缺失、Python 依赖缺失、Cron 接线缺失、job 上次状态异常、投递目标未配置（指导 Agent 询问用户投递方式）、model 未设置、最近产物过期。
- `INSTALL.md` 增加 Doctor 章节，说明检查项与状态语义。

## 0.2.0 — 2026-08-10

新增 Agent 安装链路，把"安装"从开发环境初始化收敛为可幂等执行、可验证、可卸载的正式流程：

- 新增根目录 `INSTALL.md`：面向 Agent 的安装契约（发现 → 询问 → 确认 → 执行 → 验证），明确安装/更新/卸载语义与不破坏的不变量。
- 新增 `install/install.py`（仅标准库）：`install` / `verify` / `uninstall` 三个动作；安装幂等，重复执行即更新项目文件并保留用户配置；卸载只删除 manifest 拥有物并报告待摘除的 Cron 任务。
- 新增 `install/install-manifest.json`：组件、外部依赖与 Hermes 运行时路径声明。
- 修正 `adapters/hermes/INSTALL.md` 与 `jobs.example.json`：任务脚本路径改为运行时相对路径（`glance-brief/*.py`），去掉 `data/brief` 和外部 agents-radar 目录假设。
- README 与两个 Skill 安装说明增加"使用 Agent 安装（推荐）"入口，手工安装降为备选。
- 更新 Hermes 示例任务契约测试：校验任务脚本格式与安装清单声明一致。
- 回灌生产版 CodexRadar 性价比公式：按 `IQ / price^0.25` 排序，阻止非 Sol 榜单回退到 Sol，并确保免费配置仍输出标准 JSON。
- 保留 agents-radar 来源中的 HTTP(S) Markdown 锚点；最终项目检查默认只接受 `https://github.com/` 前缀，并拒绝其他协议或仓库前缀。
- 将 `agents_radar.open_source_quality` 纳入数据契约，并补充报告首行、项目链接和数量检查。
- 收敛来源与事实边界：单来源不凑数；来源明确的预测保留预测属性，禁止模型自行推演。
- 保持当前报告标题、章节顺序、来源行位置和可见版式不变。

## 0.1.0 — 2026-08-06

首次建立可复用的开源项目基线：

- 统一 agents-report 和 noon-news 的脚本、Prompt、配置和参考文档结构。
- 同步 Agents、AI HOT、CodexRadar 和午间新闻的当前运行版逻辑。
- 预取脚本增加 `schema_version: 1`，明确中间 JSON 数据契约。
- 去除脚本对 `/root/.hermes` 和 `/root/.openclaw` 的硬编码，改用环境变量和运行时适配层。
- 增加 Hermes / OpenClaw 适配说明和示例任务模板。
- 增加离线 fixtures、脚本测试和输出格式契约文档。
- 修正 CodexRadar 原样插入时的标题重复风险，并补充 noon-news 当前要点长度约束。
- 修正 Hermes adapter 示例脚本路径，补充模板路径回归测试。
- 强化 noon-news 子进程启动、超时、空输出和错误 JSON 的结构化失败降级；补齐预取 fixture 契约。
- 增加 CodexRadar 数据时间戳缺失告警、最小依赖清单，并清理历史参考文档中的失效路径和过期规则。
- 保留当前已验证的报告排版；本版本不进行可见报告样式重设计。
- 发布审查修正两个 Skill 的仓库根目录安装/验证路径，并补足 AI HOT `curl` 启动失败的结构化降级。
