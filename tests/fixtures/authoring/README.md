# 知识库写作标杆

本目录提供两套可回查事实的完整领域样稿，用于校准 Modus 的内容深度、行文排版和图文分工。它们是明确的教学项目，不来自真实企业项目，也不代表 Modus 提供预约或联系人导入能力。示例人物、时间、编号和邮箱均为虚构数据。

| 样稿 | 从哪里开始 | 重点阅读 |
| --- | --- | --- |
| 普通域：同步会议室预约 | [使用说明](simple-reservation/README.md)、[领域入口](simple-reservation/modus/knowledge/domain/reservation/SKILL.md) | [创建预约](simple-reservation/modus/knowledge/domain/reservation/references/modules/create-reservation.md)、[取消预约](simple-reservation/modus/knowledge/domain/reservation/references/modules/cancel-reservation.md) |
| 复杂域：批量导入联系人 | [使用说明](async-import/README.md)、[领域入口](async-import/modus/knowledge/domain/contact-import/SKILL.md) | [提交与查询](async-import/modus/knowledge/domain/contact-import/references/modules/submission-query.md)、[执行与恢复](async-import/modus/knowledge/domain/contact-import/references/modules/execution-recovery.md) |

每套样稿包括领域路由、六专题和两个模块手册，保留 canonical 知识目录。模块提供贯穿案例与流程图，状态和协作专题分别解释迁移与责任交接；其他图表按实际关系选用。样稿是表达参照，不能要求所有业务具有相同接口数、状态、篇幅或目录内标题。

## 事实与样稿的关系

各案例的 Python 文件是可执行教学实现，`evidence.md` 记录调查范围、关键结论与定位依据，`reader-tasks.md` 保存预先准备的读者问题及审核答案。正式知识正文使用自然语言和知识链接，源码位置只放现有 frontmatter 锚点；维护者说明与事实底稿可以直接链接源码。

教学实现均为单进程内存模型。普通域演示同步判断和取消，复杂域演示手动驱动的排队、逐行处理和有条件恢复。没有实现的鉴权、持久化、多进程并发、后台调度和崩溃恢复不写成能力。内存任务有业务状态，与 Modus 自身的创作状态机无关。

在 Modus 仓库根目录可以执行现成的样例自验：

```bash
python tests/fixtures/authoring/simple-reservation/reservation_source.py
python tests/fixtures/authoring/async-import/import_source.py
```

这些自验检查样稿所依据的成功、拒绝、幂等或恢复场景，不证明文字易读，也不是对真实业务项目运行 `/modus-init` 的验收。修改教学实现后，先更新事实底稿和受影响正文，再复核相邻主定义、图、案例与源码锚点。

## 怎样评审样稿

先隐藏 frontmatter，读完整领域路由、六专题与模块。检查读者能否说明目标、输入、关键条件、数据变化、完成信号和失败处置；再对照教学实现与事实底稿确认结论。长表是否易查、图的分工是否合理需要单独阅读，不以字数或 Mermaid 数量评分。

独立读者只接收成稿、知识链接和问题部分，不接收审核答案、源码或作者解释；读者回答应指向正文依据。评审者再根据事实核对。真正做模型对照时，在隔离工作目录只提供所需输入，不能让生成者读取本目录里的参考稿和答案；单纯把答案写到另一个文件不构成隔离。

实际页面效果应在目标阅读器里查看。源码自验、Markdown 链接检查、图代码存在均不等于渲染验收。本批不提供渲染工具或真实项目质量结论；后续可以使用现有预览工具记录环境、文件、发现的问题和修订结果。

## 随包示例与维护者基准

[编辑合同](../../../src/modus/scaffold/templates/skills/using-modus/references/authoring/framework/editorial.md)定义稳定表达要求，[成对反例](../../../src/modus/scaffold/templates/skills/using-modus/references/authoring/framework/examples.md)摘取本目录的少量片段，展示问题稿、改进稿及理由。[执行策略](../../../src/modus/scaffold/templates/skills/using-modus/references/authoring/execution-strategy.md)负责组织上下文、写作和评审，不改变质量要求。

随包样例只包含自足的 Markdown 片段，不依赖用户安装目录中不存在的本目录。更新片段时按案例编号核对完整样稿，避免摘录事实漂移。完整教学源码、参考稿和审核答案留在维护者 fixtures 中，不进入用户技能；按当前打包规则会随源码包发布。

这两套是已知标杆，可用于学习和调优，不能冒称保留测试集。后续评估模型或策略升级时，应补入未参与调优的样本，在同一源码快照与范围下比较具体事实缺陷、读者任务结果、页面问题、修订成本与耗时。运行输出可存入已忽略的 `.benchmark-state/authoring/`，不在执行卡之外另建生产质量状态。
