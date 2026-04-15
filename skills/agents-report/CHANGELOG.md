# Changelog

All notable changes to this project will be documented in this file.

## [1.1.0] - 2026-04-15

### Fixed
- **输出截断问题**：全量输出 119+9 blocks 超过 exec 工具显示限制（~50KB），导致模型捏造内容
  - 修复：添加 `--sections` 参数按 BLOCK 精确过滤
  - 输出从 ~50KB 缩减至 ~23KB（13 blocks）
- **编号问题**：模型生成的报告出现 `#49971`、`PR #123` 等技术编号
  - 修复：在 prompt 中添加硬约束，禁止 `#` 编号

### Changed
- 脚本调用方式：`python3 script.py --sections "ai-agents:3,6,7,8,13-19 ai-trending:6,7"`
- BLOCK 映射：
  - ai-agents: 3(今日速览), 6(社区热点), 7(Bug), 8(功能请求), 13-19(趋势)
  - ai-trending: 6(Trending), 7(趋势信号)

## [1.0.0] - 2026-04-13

### Added
- Initial release
- `agents-report` skill: daily OpenClaw ecosystem report
- RSS source: agents-radar feed (ai-agents, ai-cli, ai-trending)
- Report structure: Agents生态趋势 / OpenClaw专项 / 开源趋势信号 / GitHub Trending
- GitHub Trending classification rules (★/day merging logic)
- OpenClaw internal section format (optional chapters, comma-separated)