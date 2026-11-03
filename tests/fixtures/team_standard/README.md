# Team Standard 编码演练

这里用具体任务检查规范是否帮助编码者选对已有能力、保留行为契约并处理失败。[演练项目的 Team Standard](validation/modus/knowledge/constraint/team-standard.md)展示稳定入口、场景导航、准确复用和例外说明。

## 目录与验证范围

`tuning/` 保存用于调整表达的样稿；`validation/` 分别保存任务输入、已有 API、实现草稿和行为检查。任务契约决定预期行为，不以样稿措辞、类名或输出长度判断通过。

| 样本 | 输入与任务 | 核验方式 |
| --- | --- | --- |
| 调优 Java | [样稿](tuning/team-standard.md)：集合校验、共享池、配置快照 | 用于调整内容，不计验证样本 |
| Java 后端 | [任务](validation/java/TASK.md)、已有 Kit API；按配置执行有界批量条件更新 | 编译实际 solution；检查输入无副作用、顺序、失败原因、拒绝、超时、中断、准入上限与共享池存活 |
| TS 浏览器与 Node Worker | [任务](validation/typescript/TASK.md)、已有 ports；共享纯函数与两种执行入口 | 分别按 DOM/纯 ES 类型环境编译；检查旧成功/旧错误隔离、停止、稀疏输入、单次快照、有界复用与部分失败 |
| Kotlin 客户端、混合与未知技术 | [任务与回读](validation/review.md) | 检查修改草稿的平台/版本、取消、存储、冲突与降级；不计编译通过 |

这些是人工编写的行为回归夹具，不是独立模型盲测或统计评测。项目 API 由本目录定义；Store/HTTP 替身不证明真实 Spring、Apollo、React、Android 或数据库集成，也不证明生产容量。需要评估生成质量时，应另保留未用于调优的新任务。

## 本地复现

在仓库已安装测试依赖的环境中运行：

```bash
uv run --locked --extra test pytest -q tests/test_team_standard_examples.py
```

Java 需要 JDK 8 或更高版本；编译器使用 Java 8 目标和显式 UTF-8 编码。TypeScript 需要 Node 与 `tsc`，也可指定编译器的绝对路径：

```bash
MODUS_TEST_TSC=/path/to/typescript/lib/tsc.js \
  uv run --locked --extra test pytest -q tests/test_team_standard_examples.py -k typescript
```

输入契约采用 TypeScript 5.6 / ES2020 与 Node 20。检查隔离宿主的 ambient types，避免已有 `@types/node` 意外放宽共享包的运行环境。CI 的 DSH 任务复用其锁定 TypeScript 编译器执行演练，无需新增 npm 依赖；这项检查不替代目标版本验证。

缺少工具时 pytest 明确报告 skip；配置了编译器但编译或运行失败时测试失败。Kotlin 与未知技术仅有人工回读，没有相应工具链时不可报告为运行通过。
