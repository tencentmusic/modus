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
│   ├── team-standard.md
│   └── team-standard/<topic>.md       # 按真实复杂度增加，人工所有
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

Team Standard 的入口与可选专题遵循[团队规范合同](deliverables/team-standard.md)，共享声明身份及人工保护；内置规范模块不是项目产物目录模板。

六专题根文件始终是稳定入口。事实密度确实影响导航时，`api.md` 与 `object.md` 可以增加同名一级分片目录；按调用目的、所有权、生命周期或稳定表示族分组，不按单个接口、DTO、类或源码文件分片。

根概览、Domain、专题和 Module 属于生成正文。`constraint/` 与 `business/` 默认人工所有；初始化种子不把文件永久冻结为固定字节。结构变化先创建新落点并修复入站链接，最后按读时哈希删除已证明退役的生成文件。人工文件只有明确授权时才修改，结构确认最多授权最小链接修复，不授权删除或重写周围语义。

生成正文默认以普通 Markdown 服务开发者阅读。源码位置属于可验证元数据，不属于读者叙事：根概览、Domain、六专题及分片和 Module 需要源码追溯时，统一按本页关键事实在 frontmatter 的 `anchors.locations` 中记录位置；正文不得出现仓库源码路径、行号或“证据：path#L”清单。正文可以使用对理解和修改确有帮助的业务名称、协议身份与限定符号，但必须解释它们怎样参与任务，不能让读者通过打开源码自行补全含义。

frontmatter 不是隐藏论证仓库。每个位置应代表术语定义、公开入口、关键判定、权威写入、完成/失败或恢复之一，多个结论由同一位置支撑时复用，不能把调查读取过的所有文件逐项搬入。配置、SQL 或项目材料等文件级依据可用已有 `anchors.paths` 记录仓库相对路径，不为没有源码符号的材料虚构 `anchors.locations`。删除 frontmatter 后，正文仍须完整说明行为、边界、失败恢复和修改验证；只看 frontmatter 也不能替代正文。

成稿和局部修订时，从本页已解释的关键事实反查来源：API 对应声明、注册及关键实现，Object 对应定义与映射，Rule/State 对应判定、转换与写入，Downstream/Infrastructure 对应交接、装配或资源配置，Module 对应场景入口、核心执行和恢复。按实际事实补足关联，不限定数量、不穷举内部方法，也不把专题锚点全部复制到 Module。人工业务材料没有源码依据时不强加锚点。

`locations` 沿用 `path`、`symbol`、`startLine` 和可选 `endLine`：路径以当前仓库为准，符号使用可核验的限定名；重载有歧义时带签名，行号从实际声明读取。需要方法体或多行定义时补充经过核实的范围，不把整文件范围当作方法范围。已有 N 层位置是取证线索，最终以回读的当前源码为准；声明可达不等于正文事实或入口覆盖完整。无法唯一对应时保留缺口，不猜测位置或新增关联字段。
