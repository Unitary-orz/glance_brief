# brief V2 状态与边界

## 定位

V2 是与现有 V1 并行的本地实现，用于验证更稳定的语义协议、事实校验和 Markdown 渲染。

当前阶段：**独立验证，不接入生产**。

- 不修改 Hermes Cron 的调度、模型、投递目标或 prompt 链路；
- 不覆盖 `$HOME/.hermes/scripts/glance-brief/` 下的现有 runtime；
- 不把 V2 的实验输出当作生产简报；
- V1 继续负责当前午间简报的正式运行。

## 目录分工

```text
v2/
├── run_v2.py               # check / probe / run 入口
├── brief_v2.py             # 配置加载、来源映射、候选池组装
├── render_report.py         # 结构校验与固定 Markdown 渲染
├── evaluate_outputs.py     # V1/V2 产物对比
├── convert_agents_radar.py  # legacy agents-radar 专用转换器
├── config/                 # 脱敏示例配置
├── fixtures/               # 离线输入 fixture
├── prompts/                # 模型语义协议
└── output/                 # 本地实验产物，禁止作为源码或 runtime 输入
```

`v2/output/` 和 Python 缓存由仓库忽略规则排除；历史实验产物可以留在本地用于复核，不进入提交内容。

## 当前验证门槛

从仓库根目录执行：

```bash
python3 v2/run_v2.py check --config v2/config/brief.example.json
python3 -m unittest discover -s tests -p 'test_v2*.py'
python3 -m unittest discover -s tests -p 'test_*.py'
python3 -m py_compile v2/*.py
```

V2 的正式 Markdown 只能由程序从已通过结构、候选引用和事实数字校验的语义对象渲染；模型原始响应校验失败时不得静默生成报告。

## 已知限制

- 模型仍可能生成候选未支持的数字或事实；当前校验器应拒绝该响应，而不是修正文案后继续发布。
- 单次基准通过不代表模型输出稳定，需要在冻结输入和真实输入上分别复核。
- 生产切换前还需要独立的 runtime adapter、失败回退策略和至少一轮不投递的端到端演练。

## 允许进入生产的条件

只有同时满足以下条件，才讨论接入 Hermes runtime：

1. V2 代码、测试、配置和文档形成明确的仓库变更；
2. 真实输入上的错误事实均能 fail closed；
3. 模型失败、空响应、非法 JSON 和来源失败均有可观测结果；
4. V1 与 V2 完成不投递的对照运行；
5. 明确回退到 V1 的开关和验证过的 runtime adapter；
6. 用户明确批准接入 Cron。
