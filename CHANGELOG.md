# Changelog

## Unreleased

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
