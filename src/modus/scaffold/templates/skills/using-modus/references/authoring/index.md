<!--
索引负责渐进导航，详细规则在目标页面维护，避免复制后漂移。
-->

# 正文知识创作边界

正文知识只有两个规范源，再加一个发布边界：

```text
机器证据、当前源码、用户材料、既有正文
                    │
                    ▼
       evidence/：怎样取得并闭合事实
                    │
                    ▼
       framework/：事实应形成什么知识
                    │
                    ▼
       publication.md：怎样回读并安全发布
```

- [证据消费与事实闭合](evidence/index.md)回答“凭什么这样写”，不规定正文目录。
- [知识生成框架](framework/index.md)回答“写到哪里、为谁回答什么”，不复制机器取证流程。
- [验证与发布](publication.md)区分 Agent 的语义回读、确定性机械检查与安全写入。
- init/reinit 的每个 Domain 生成或恢复前，按[逐域加载与恢复](evidence/scope-modeling.md#逐域加载与恢复)依次读取本域执行卡、对应证据、相关已有正文和写作规范；上下文压缩后使用同一顺序。
- 用户显式授权且宿主支持时，[按 Domain 并行撰写](parallel-domain-authoring.md)约束 worker 的独占路径、handoff 与根作者验收；串行流程不必加载。

`modus-init`、`modus-reinit`、`modus-update-knowledge` 和 `modus-sync-knowledge` 只选择范围并编排这三部分。Python 不生成、扩写或评价自然语言正文；机器 `clean` 也不表示内容专业、充分或正确。
