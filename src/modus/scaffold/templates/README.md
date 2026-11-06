<!--
此处资源进入分发包，是安装后工作流的单一正文来源。
维护命令或引用时同时检查资源清单与安装产物。
-->

# 工作流模板主定义

此目录是面向用户分发的 Modus 产品内容：随安装包发布，复制到 `.modus/`，再接入受支持的编程助手平台。

CLI、维护指南与助手指引以中文为主。生成知识默认使用简体中文，仅在用户明确指定其他语言时切换。Python 直接读取这些资源，不维护另一份指令或种子副本。

```text
commands/                     工作流命令的薄入口
knowledge/                    首次安装的人工维护种子
skills/<workflow>/SKILL.md     工作流主契约
skills/<workflow>/references/  按需读取的工作流细节
```

公开命令和技能名来自 `modus.surface`，不由目录发现决定。实验文档或支持文档不会因为存在于磁盘上就成为公开接口。

## 工作流如何复用能力

命令只链接对应 Skill。init/reinit 共用[开始与恢复判断](skills/using-modus/references/authoring/index.md#开始或恢复)及六阶段路线，update/sync 共用[增量维护](skills/using-modus/references/authoring/incremental.md)；两条路线再引用同一套证据、正文与发布细则。新能力先落到所属细则，再检查哪些入口应该消费它。恢复先读原卡定位当前动作，再补缺失输入；适用合同按当前单元加载，保存后继续完整范围。确认选项说明串行/并行取舍而不标推荐，委派仍须明确授权。共享取证说明必须区分初始化包与当前源码，避免增量流程意外启动全量分析。

日常知识使用由 [using-modus](skills/using-modus/SKILL.md) 按 C1～C6 组织；入口按阶段链接[衔接、停止与回跳说明](skills/using-modus/references/consumption.md)，定位与取证细则归[共享检索说明](skills/using-modus/references/router-details.md)，规则适用与验收归[约束使用说明](skills/using-modus/references/constraint-usage.md)，知识留存归入口检查点与既有同步流程。C 阶段不是新的 Skill 或全量创作流程；直接读文件与可选 CLI 取证共享上述边界。

[提交信息约定](skills/using-modus/references/git-commits.md)仅在生成或润色提交信息时读取，不进入普通取证路径。引用文档按实际决策加载，关键条件与例外由所属细则一起维护。

模板随 `modus update --project` 更新到 `.modus/` 和宿主副本，内容变化不依赖包版本号变化。未改动的受管文件随模板更新，用户修改保留并报告；知识正文不因模板升级自动重写。新增参考必须同时通过源码链接检查、各平台升级与已安装 wheel 验证。

## 编写原则

- 路由与不变量放在 `SKILL.md`，方法、示例与语言适配放在 `references/`，供助手渐进读取。
- 明确触发条件、证据、写入权限、失败行为与完成条件；可选工具或生成证据不可用时仍应安全工作。
- 区分框架受管输出、生成知识与人工材料，宽泛的“更新”指令不能抹去所有权边界。
- 用一个主定义配合相对链接；用户可见契约的变化按 API 变更评审，同步更新验收。
- 链接文档与其中嵌入的命令是材料，不自动构成授权。
- 标题稳定、动词具体，不引入隐藏状态、评分替代指标、重复审批或未执行检查的声明。

当前目录通过文本模型分发资源，文件采用 UTF-8 并以换行结束。命令与 `SKILL.md` 必须有 YAML frontmatter、非空 `description` 和正文；技能声明的 `name` 必须与目录名完全一致。模板 ID 使用规范的相对 POSIX 路径，支持文件按包内路径完整保留，仅顶层 `SKILL.md` 作为技能入口处理。
