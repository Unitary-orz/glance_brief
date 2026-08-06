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
| `repo` | 仓库治理、分支、CI、依赖 |
| `docs` | 文档本身（README、说明文档） |
| `publish` | clawhub / GitHub 发布 |

---

## scope 选择判定树

```
这次变更首先影响什么？

├── Skill 的定义/引用/调用方式   → skill
├── 定时任务的配置/模板/调度     → cron
├── News 报告的结构/格式/规范   → news
├── 仓库治理/CI/分支/依赖       → repo
├── 仅 README/说明文档          → docs
├── clawhub/GitHub 发布         → publish
└── 其他                        → 选最贴近的主域
```

---

## 判定原则

**一次一 scope**：多条改动线 → 拆成多次提交

**先感知层后实现层**：用户先感知到什么，就用什么 scope
- `fix(skill)` 而非 `fix(scripts)`
- `docs(news)` 而非 `docs(files)`

**产品域优先于技术层**：
- ✅ `feat(news)`、`fix(cron)`
- ❌ `feat(database)`、`fix(config)`

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
feat(news): 新增午间简报定时任务

fix(cron): 修复 agents-report 缺少 sessionTarget 配置
fix(skill): 修复 prompts 路径与实际文件不匹配

refactor(news): 重构简报输出格式
docs(repo): 完善 git commit 规范

chore(repo): 添加 .gitignore
chore(ci): 配置 GitHub Actions
build(deps): 升级 feedparser 版本

test(skill): 添加集成测试
revert(cron): 回退 timeout 配置变更
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

