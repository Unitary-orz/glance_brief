# Changelog

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
