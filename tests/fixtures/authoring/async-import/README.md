---
name: async-import-authoring-fixture
anchors:
  locations:
    - path: import_source.py
      symbol: ContactImporter
      startLine: 42
      endLine: 192
    - path: import_source.py
      symbol: demonstrate
      startLine: 195
      endLine: 254
---

# 联系人批量导入：复杂域写作教学夹具

这是一套可以运行、可以回查、可以让陌生读者测试的教学材料。它示范怎样把“有接口、有状态、有重试”展开为业务手册：调用成功到底完成了什么，部分成功怎样统计，重复提交为什么不等于重复执行，恢复又从哪里继续。

**所有联系人、租户和业务记录都是示例数据。** 这里的实现是独立教学项目，不代表 Modus 提供联系人服务、消息队列或生产级恢复能力。执行器采用单进程内存字典和队列；没有数据库、后台线程、网络协议、权限系统、进程重启恢复或并发安全保证。

## 从哪个入口开始

| 阅读目的 | 入口 |
| --- | --- |
| 判断领域边界与完成口径 | [联系人导入领域](modus/knowledge/domain/contact-import/SKILL.md) |
| 看提交、查进度和纠正坏行 | [提交与查询手册](modus/knowledge/domain/contact-import/references/modules/submission-query.md) |
| 看部分写入后的恢复 | [执行与恢复手册](modus/knowledge/domain/contact-import/references/modules/execution-recovery.md) |
| 复核事实与图中的关系 | [证据底稿](evidence.md) |
| 检查陌生读者能否完成任务 | [读者任务与参考答案](reader-tasks.md) |

在本案例目录运行以下命令，只需 Python 标准库：

```bash
python3 import_source.py
```

程序先运行带断言的示例，再打印受理、部分成功、恢复前后、耗尽尝试次数和全量坏行的 JSON 快照。任何断言失败都会让命令以错误退出；成功输出只是这个教学实现的运行证据，不能证明每篇文字或图表都正确。已执行的核心案例、补充检查和检查范围保存在[验收结果](verification-results.json)中。

## 怎样使用这套样稿

先读一篇模块手册，再运行对应案例，最后从专题查规则和字段。每个模块可以独立解释一个完整任务；六份专题各自拥有共享定义，模块通过链接复用，避免多处维护同一字段字典。

这套样稿有意保留容易写错的细节：邮箱归一化发生在执行时，幂等比较发生在提交时；两次有效行写入可能只产生一个联系人；失败任务可能已经写入部分联系人；恢复成功不会重新执行已有结果的行；没有后台执行就不会因为反复查询而前进。

图表的 Mermaid 源码与文字一起交付。实际渲染情况以随包验收记录为准；不能从代码块存在、语法看起来正确或业务断言通过，推断图在目标阅读界面已验收。

## 迁移到真实项目时

保留问题和表达方式，替换业务事实、接口、对象、规则、完成信号及证据。不要把本例的两个模块、五个状态、两个配置项或重试次数当成真实项目必须具备的结构。真实项目没有的机制，应明确说明不适用或调查缺口。
