<!--
路径参与检索、身份和所有权判断，重命名需要同步所有消费者。
目录示例描述归属，不能作为自动覆盖已有文件的授权。
-->

# 稳定布局与所有权

路径是检索、身份和所有权协议，应保持稳定；标题与篇幅是表达选择。

修订已有正文时保持目录、标题层级、元数据和有价值的人工内容，在既有章节内改善叙述与信息分块；只有真实内容归属变化才按迁移规则调整结构。[编辑合同](editorial.md)负责阅读排版，本文件不规定阅读器字号、主题或 CSS。

```text
modus/knowledge/
├── architecture-overview.md
├── constraint/
│   ├── global-standard.md
│   └── team-standard.md
└── domain/<domain>/
    ├── SKILL.md
    └── references/
        ├── api.md
        ├── object.md
        ├── rule.md
        ├── state_machine.md
        ├── downstream.md
        ├── infrastructure.md
        ├── modules/<module>.md
        └── business/
            ├── index.md
            ├── meta/index.md
            ├── experience/index.md
            └── scenario/index.md
```

六专题根文件始终是稳定入口。事实密度确实影响导航时，`api.md` 与 `object.md` 可以增加同名一级分片目录；按调用目的、所有权、生命周期或稳定表示族分组，不按单个接口、DTO、类或源码文件分片。

根概览、Domain、专题和 Module 属于生成正文。`constraint/` 与 `business/` 默认人工所有；初始化种子不把文件永久冻结为固定字节。结构变化先创建新落点并修复入站链接，最后按读时哈希删除已证明退役的生成文件。人工文件只有明确授权时才修改，结构确认最多授权最小链接修复，不授权删除或重写周围语义。

生成正文默认以普通 Markdown 服务开发者阅读。源码位置属于可验证元数据，不属于读者叙事：根概览、Domain、六专题和 Module 需要源码追溯时，统一把少量代表性位置写入 frontmatter 的 `anchors.locations`；正文不得出现仓库源码路径、行号或“证据：path#L”清单。正文可以使用对理解和修改确有帮助的业务名称、协议身份与限定符号，但必须解释它们怎样参与任务，不能让读者通过打开源码自行补全含义。

frontmatter 不是隐藏论证仓库。每个位置应代表术语定义、公开入口、关键判定、权威写入、完成/失败或恢复之一，多个结论由同一位置支撑时复用，不能把调查读取过的所有文件逐项搬入。支撑术语解释的代表性项目文档可用已有 `anchors.paths` 记录仓库相对文件路径，不为没有源码符号的材料虚构 `anchors.locations`。删除 frontmatter 后，正文仍须完整说明行为、边界、失败恢复和修改验证；只看 frontmatter 也不能替代正文。
