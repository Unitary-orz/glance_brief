# Git Commit 提交规范

> 本项目使用 Conventional Commits 格式：`type(scope): summary`
>
> 参考：[git-commit-governance](../skills/git-commit-governance/SKILL.md)

---

## 格式

```
type(scope): summary
```

| 元素 | 规范 |
|------|------|
| **type** | 英文小写，见 type 清单 |
| **scope** | 主域名，单一小写名词 |
| **summary** | 中文，简洁说清楚改了什么，句号结尾 |

---

## type 清单

| type | 使用场景 | 示例 |
|------|---------|------|
| `feat` | 新增能力、功能、Skill、脚本 | `feat(news): 新增午间简报 skill` |
| `fix` | 修复错误逻辑、配置、路径 | `fix(cron): 修复 sessionTarget 缺失` |
| `refactor` | 重构逻辑，不改功能 | `refactor(inventory): 统一字段校验` |
| `docs` | 仅文档更新 | `docs(skill): 补充安装步骤` |
| `chore` | 仓库维护（配置、依赖、CI） | `chore(ci): 添加 GitHub Actions` |
| `perf` | 性能优化 | `perf(nutrition): 加速核心层查询` |
| `test` | 测试相关 | `test(skill): 添加集成测试` |
| `rm` | 删除文件、功能、依赖 | `rm(skill): 移除废弃脚本` |
| `sync` | 与外部源同步（GitHub→本地） | `sync(skill): 更新 agents-report` |
| `release` | 版本发布、打 tag | `release(v1): 发布首个正式版本` |
| `style` | 格式化、空格、缩进，不改逻辑 | `style(docs): 统一代码块格式` |

---

## scope 清单

| scope | 适用场景 |
|-------|---------|
| `skill` | Skill 的定义、引用、路由、边界 |
| `cron` | 定时任务配置、模板、调度 |
| `news` | News 类报告（日报、简报） |
| `install` | 安装流程、INSTALL 文档 |
| `format` | 输出格式、写作规范、结构 |
| `prompt` | Prompt 模板、内容约束 |
| `publish` | clawhub / GitHub 发布 |
| `sync` | 外部仓库同步 |
| `repo` | 仓库治理（.gitignore、分支策略） |
| `ci` | CI/CD 流水线 |
| `deps` | 依赖安装、版本升级 |
| `docs` | 文档本身（README、说明） |

---

## scope 选择判定树

```
这次变更首先影响什么？

├── Skill 的定义/引用/调用方式  → skill
├── 定时任务的配置/模板/调度    → cron
├── News 报告的结构/格式/规范    → news
├── 安装流程/INSTALL 文档       → install
├── Prompt 模板/内容约束         → prompt
├── 输出格式/写作规范            → format
├── clawhub/GitHub 发布         → publish
├── 外部仓库同步                → sync
├── .gitignore/CI/分支管理      → repo
├── 依赖安装/版本               → deps
├── 仅 README/说明文档          → docs
└── 其他                        → 选最贴近的主域
```

---

## 判定原则

**一次一 scope**：多条改动线 → 拆成多次提交

**先感知层后实现层**：用户先感知到什么，就用什么 scope
- `fix(skill)` 而非 `fix(scripts)`
- `docs(news)` 而非 `docs(files)`

**产品域优先于技术层**：
- ✅ `feat(nutrition)`、`fix(inventory)`
- ❌ `feat(database)`、`fix(json)`

---

## summary 写法

| 要求 | 说明 |
|------|------|
| 简洁 | 一行，不超过 50 字 |
| 具体 | 写清楚改了什么，不写「调整」「优化」 |
| 句号 | 句号结尾 |
| 中文 | 默认中文 |

### 写作模板

```
feat(scope): 新增 [具体内容]
fix(scope): 修复 [具体问题]
refactor(scope): 重构 [原逻辑] → [新逻辑]
docs(scope): [动作] [文档名/范围]
chore(scope): [维护内容]
sync(scope): 从 [外部源] 同步 [内容]
rm(scope): 删除 [废弃内容]
```

---

## 示例

```
feat(skill): 新增 agents-report skill
feat(news): 新增午间新闻定时任务

fix(cron): 修复 agents-report 缺少 sessionTarget 配置
fix(skill): 修复 prompts 路径与实际文件不匹配

refactor(format): 重构 news-brief 模板结构
refactor(install): 重构安装流程为 sparse-checkout 方式

docs(skill): 新增 INSTALL.md 安装指南
docs(format): 补充 GitHub Trending 分类合并规则

chore(repo): 添加 .gitignore
chore(ci): 配置 GitHub Actions 测试
chore(deps): 升级 feedparser 版本

sync(skill): 从 glance_brief 同步最新 prompt 模板
rm(skill): 移除废弃的 v1 模板
rm(docs): 删除重复的格式说明文档

publish(skill): 首个正式版本发布
release(v1): v1.0.0 发布，标记 milestone
```

---

## 反例

```
feat: 新增功能
fix: 修复问题
docs: 更新文档
chore: 调整一些东西
refactor: 重构代码
sync: 同步更新
```

---

## 提交前自检

- [ ] 格式：`type(scope): summary` ？
- [ ] type 在清单中？
- [ ] scope 在清单中或已判断选择？
- [ ] summary 具体说明了改了什么？
- [ ] 多个改动 → 拆成多次提交？

