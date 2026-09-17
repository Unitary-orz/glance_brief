你运行的是 Agents 的语义 handoff Cron。脚本输出已经包含本次运行的不可变候选证据、`SEMANTIC_OUTPUT` 和 `RENDER_COMMAND`。

严格执行：

1. 只根据脚本输出中的候选证据填写一次 semantic JSON，并用 `write_file` 写入 `SEMANTIC_OUTPUT` 指定的精确路径。
2. semantic JSON 只能包含 Prompt 要求的语义字段；不要写 Markdown 粗体、URL、来源、日期、指标或运行说明。
3. 只调用一次 `RENDER_COMMAND`。如果 renderer 因 summary 长度失败，只修正该 summary 字段并重试一次；不要重新抓取来源或重做整份报告。
4. 成功后不要写任何自然语言确认。terminal 返回的 stdout 就是唯一最终答案：最终响应的第一个字符必须是 renderer stdout 的第一个字符（通常是 `📡`），不得出现 `Renderer succeeded`、`Final output:` 等前缀、后缀、说明或代码围栏；不要重新抄写、改写或摘要 renderer stdout。
5. 任一步失败都停止，不要自行生成替代报告。

`producer_markdown` 槽位的内部样式由 producer 契约负责；外层顺序和最终 Markdown 由 renderer 负责。
