# MEMORY.md

## 使用边界

- 用户基础资料、日常偏好、表达风格放在 `USER.md`；这里只保留跨会话的长期决策和不该遗忘的规则。

## 长期规则

- 涉及 OpenClaw 时优先使用官方术语：multi-agent、session、bindings、hook 等（2026-02-21）
- 2026-04-03：workspace submodule 管理规范——优先用 GitHub URL，不走 `/tmp` 等临时路径；先用 `git submodule add <GitHub-URL>` 直连，走不通再配 `credential.helper`
- 2026-04-04：clawhub skill 安装行为规范：
  - `clawhub inspect <slug>` 只用 slug（不用 owner/ 前缀）
  - 免费版 rate limit 约 180次/小时，单文件请求需 2 秒间隔
  - clawhub 安装的 skill 带内部 `.git` 时，需要 `git rm --cached` + 删除 `.git` 后再 `git add`（否则报 embedded git repository 警告）
- 2026-04-04：git submodule 提交顺序：先在子模块内部 `git commit`，再回主仓库 `git add <子模块目录>` 更新引用
- 飞书图片读取规则（2026-03-14）：飞书图片默认先去 `/root/.openclaw/media/inbound/` 找真实本地文件，再做 OCR / vision；不要再根据 `message_id` 猜远程 URL
- 2026-04-15：项目 git 提交规范——**用项目自身的规范**，不是 workspace 的规范

## 当前长期方向
打造 3 个可持续迭代的助手系统：
1) 英语学习（翻译、难点沉淀、复习）
2) 库存管理（菜谱、营养、临期提醒）
3) 记账预算（快速记账、预算跟踪、复盘）

## 营养数据库（双层结构）
- 路径：`tasks/nutrition/`
  - `nutrients_core.json` — 核心层 **488 条**（常用食材，懒加载 ~8ms）
  - `nutrients.json` — 完整层 **6,124 条**（`--full`，~85ms）
  - `lookup.py` — 查询脚本（双层搜索）
- 每100g可食部数据，来源优先级：国家食物与营养咨询委员会 > 中国食物成分表/薄荷 bohee > USDA > 估算
- 查询：`python3 tasks/nutrition/lookup.py <食材名> [重量g]`
- 扩展：`--full`（完整层）、`--stats`（统计）、`--list`（列清单）
- ⚠️ bohee scraper 已知问题：fat>200 条目为不可逆错位（已全部移除）

## 图片理解规范（用户偏好）
- 入库/库存/菜谱等场景的图片理解，统一用 `mcporter call minimax.understand_image`，不用内置 `image` 工具
- 内置 `image` 工具仅作为备用方案

## 维护项目（GitHub）

### glance_brief
- **仓库**：https://github.com/Unitary-orz/glance_brief
- **本地路径**：`/root/projects/glance_brief/`
- **定位**：一眼就能扫完的简短新闻/日报 skills 集合
- **内容**：
  - `skills/agents-report/` — 每日 OpenClaw 生态日报（cron: 每日 10:00）
  - `skills/noon-news/` — 每日午间热点简报（cron: 每日 12:30）
- **workspace 接入**：`skills/` 下通过 symlink 指向仓库对应目录
- **命名规范**：snake_case（如 `glance_brief`）

---

## 搜索约定（2026-04-13）

- **首选搜索工具：Agent Reach**（路径 `/root/.openclaw/tools/Agent-Reach/agent_reach/skill/SKILL.md`）
- 支持 17 个平台：搜索/读网页、Twitter、Reddit、小红书、微博、B站、GitHub、YouTube、LinkedIn 等
- 路由表：search / social / dev / web / video / career
- 备用搜索：仅在 Agent Reach 覆盖不到时使用 `minimax-cp.web_search` 或 `web-search-prime`
- TOOLS.md 已同步更新

## 已确认机制
- 标准库采用轻量结构：`tasks/` 下 3 个主题文件 + `_index.md`
- 先不拆子目录，达到复杂度阈值再拆
- 规则迭代走 git 留痕（可回滚）

## Cron 任务配置（重要）

### agents-radar 日报
- **Job ID**: `ed0ceb97-cf5e-4afb-87c5-9148199e3181`
- **Schedule**: `0 10 * * *`（每日 10:00 Asia/Shanghai）
- **发送目标**: 飞书群 `oc_76b918a1da88e33c679d6543d1ebfbe7`
- **关键字段**：
  - `sessionTarget: "isolated"` — 必须在独立会话运行
  - `wakeMode: "now"`
  - `payload.model: "minimax-cn/MiniMax-M2.5"`
  - `payload.timeoutSeconds: 600`
  - `delivery.mode: "none"`
  - 发送参数必须含 `accountId=main`

### agents-radar 日报优化（2026-04-15）
- **问题**：脚本全量输出 119+ blocks 超过 exec 工具显示限制（~50KB），导致模型捏造内容
- **修复**：添加 `--sections` 参数按 BLOCK 精确过滤
- **脚本调用**：`python3 scripts/agents-radar-daily.py --sections "ai-agents:3,6,7,8,13-19 ai-trending:6,7"`
- **BLOCK 映射**：
  - ai-agents: BLOCK 3(今日速览), 6(社区热点), 7(Bug), 8(功能请求), 13-19(生态趋势7条)
  - ai-trending: BLOCK 6(GitHub Trending), 7(趋势信号)
- **输出规模**：从 ~50KB 缩减至 ~23KB（13 blocks）
- **硬约束**：prompt 中明确禁止出现 `#` 编号（如 #49971），只保留纯文字描述
- **配置位置**：`/root/.openclaw/cron/jobs.json`（job id: `ed0ceb97-cf5e-4afb-87c5-9148199e3181`）

### 工作日晚餐推荐
- **Job ID**: `dinner-recommend-17761592`
- **Schedule**: `30 17 * * 1-5`（工作日 17:30 Asia/Shanghai）
- **发送目标**: 飞书群 `oc_76b918a1da88e33c679d6543d1ebfbe7`
- **数据来源**: 飞书多维表格（app_token=YsEBbQtjoa0NTEsCGiVcAWSQnMh, table_id=tbln4kVnDo9ytXtE）
- **内容**: 根据库存推荐快手晚餐，优先消耗快过期食材

## 待完善
- 建立 git 规范（.gitignore / 提交规范 / tag 节奏）
- 为三大主题补充每周迭代 checklist
- 将关键决策持续同步到本文件，避免会话丢失

## 库存操作原则（重要）
- 库存新增：信息不全不直接写入，必须先确认完整字段（品名/分类/数量/单位/购入日期/价格/保质期等）再写入飞书多维表格；参考 `tasks/inventory/库存提醒说明文档.md`
- 食用/消耗同步：先查现有记录，再更新状态，不凭空创建新记录
- 大规模更新：先发文档链接，等用户确认后再执行

## 最近更新
- 2026-04-13：新建维护项目 `glance_brief`（GitHub: Unitary-orz/glance_brief）——一眼扫完的简短新闻/日报 skills 集合；通过 `/root/projects/glance_brief/` + workspace symlinks 方式接入 OpenClaw skills/ 目录；仓库含 agents-report（每日生态日报）和 noon-news（午间热点简报）两个 skill。
- 2026-04-13：修复 agents-radar cron 任务卡住问题——根因是缺少 `sessionTarget: "isolated"` 等关键配置；同步更新 jobs.json、ops 文档和 MEMORY.md。
  - 同时发现并修复"每周库存采购提醒"任务——错误原因同样是 `delivery.to` 字段缺失；已恢复并修复，下次运行 2026-04-20 17:00 北京时间。
- 2026-04-09：营养数据库重大升级——81条 → 14,083条（引入薄荷 bohee 开源爬取数据）；上线双层索引结构（核心层 664 条快速搜索 ~11ms / 完整层 ~167ms）；lookup.py 重写支持 `--full`、`--stats`、`--list`；GI 字段异常值（字段偏移导致 gi>110）已清除；README + MEMORY.md 同步更新。
- 2026-04-04：安装 self-improving-agent skill（v3.0.13）；新增 `.learnings/` 目录用于记录纠正、错误、功能请求；更新 clawhub skill 安装行为规范（rate limit、inspect 格式、embedded .git 处理）；补充 git submodule 提交顺序规范。
- 2026-04-04：今日教训——Agent-Reach/（工具本体）vs skills/agent-reach/（skill 封装）的区别，两者缺一不可。
- 2026-03-15：新增夸克网盘资源查询能力：
  - 通过调用公开 API 直接查询分享链接的文件信息（无需登录）
  - 已安装 QuarkPanTool 工具（路径：`/root/.openclaw/tools/QuarkPanTool/`）
  - 用户 Cookie 已保存在 `/root/.openclaw/tools/QuarkPanTool/config/cookies.txt`，可用于转存/下载
  - 新建 skill：`skills/quark-resource-search/SKILL.md`
- 2026-02-27：完成一轮 memory-hygiene，清除长期记忆中的无关噪声并重排结构；新增 L2 汇总文件 `memory/2026-02-27-L2.md`，用于沉淀近几日关键决策与可执行后续。
- 2026-02-26：新增触发约定——用户提到“英语模式”时，先发送 English Mode welcome 文案，再触发 en-read-cycle 单链路流程（文本/图片路由 → 结构化 JSON → 硬规则收口 → format 脚本统一渲染与入库），不走测试/多模型分支。
- 2026-02-26：新增约定——涉及技术设计相关提问，先客观分析再回复。
- 2026-02-26：en-read-cycle 测试文档改写为 subagent session 验证口径：
  - 主会话对子会话仅下发「skill + 英文文本」
  - 验收重点从脚本细节转为：调用指令纯度、会话边界、结果可交付性
  - 新增“具体观察”要求：主会话必须回看 subagent session history（含工具调用）并按时间线记录证据
  - 过程评估新增：多余调用、无用调用、不符合预期调用，并判断是否由 SKILL.md 指令导致
