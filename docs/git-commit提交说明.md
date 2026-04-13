# Git Commit 提交规范

> 本 Workspace 使用 Conventional Commits 格式：`type(scope): summary`
> 
> 参考：[git-commit-governance](../skills/git-commit-governance/SKILL.md)

---

## 基本格式

```
type(scope): summary
```

| 元素 | 规范 |
|------|------|
| **type** | 英文小写，固定前缀（见下方清单） |
| **scope** | 本次提交的主域名，单一小写名词 |
| **summary** | 中文描述，简洁说清楚改了什么 |

---

## type 清单

| type | 使用场景 |
|------|---------|
| `feat` | 新增能力、功能模块、Skill、脚本 |
| `fix` | 修复问题、错误逻辑 |
| `refactor` | 重构代码/逻辑，不改功能 |
| `docs` | 仅文档更新（README、说明文档等） |
| `chore` | 仓库维护（配置、CI、依赖） |
| `perf` | 性能优化 |
| `test` | 测试相关 |

---

## scope 清单（按领域）

| scope | 适用场景 |
|-------|---------|
| `skill` | Skill 的新增、编排、引用方式 |
| `cron` | 定时任务配置、模板 |
| `nutrition` | 营养数据库查询、扩展 |
| `memory` | MEMORY.md、记忆沉淀 |
| `language-en` | 英语学习相关（翻译、复习、难点） |
| `tasks` | 标准库 tasks/ 目录下的任务域 |
| `news` | News 类报告（日报、简报） |
| `inventory` | 库存管理、多维表格 |
| `repo` | 仓库治理（.gitignore、workflows） |

---

## scope 选择原则

1. **先看感知层**：这次变化用户首先感知到的是什么？（能力→skill，记忆→memory，任务→tasks）
2. **一次只选一个**：多条改动线 → 分成多次提交
3. **优先产品域**：用 `nutrition`、`inventory` 而非 `database`
4. **仓库级维护用 `repo`**：.gitignore、CI 配置、submodule 管理

---

## summary 写法要求

- 简洁，一行说清楚改了什么
- 避免：`*修复问题*`、`*调整逻辑*`、`*优化*`
- 推荐：`*新增荷兰豆营养数据*`、`*修复 cron timeout 配置*`、`*补充 memory 更新规则*`
- 使用中文句号 "。" 结尾

---

## 不推荐

- `chore: 修复了一些问题` → 应写具体修复了什么
- `feat: 更新功能` → 应写更新了什么功能
- 一次提交混多个域 → 应拆分

---

## 示例

```
feat(skill): 新增 git-commit-governance skill
fix(cron): 修复 agents-radar 任务缺少 sessionTarget 配置
docs(news): 新增午间新闻任务说明文档
chore(repo): 同步 glance_brief 仓库 symlink
feat(nutrition): 补充 5 种肉类 USDA 数据
refactor(inventory): 重构库存读取流程，统一字段校验
```

---

## 反例

```
feat: 更新了一些东西
fix: 修复问题
chore: 调整
docs: 文档更新
```

更好的写法应落到具体 scope 和变更内容。
