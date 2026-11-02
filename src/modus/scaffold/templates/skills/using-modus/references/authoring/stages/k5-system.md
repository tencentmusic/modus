# K5：系统组装

根作者用已经验收的领域正文组装系统级知识，核对跨域事实是否在各落点一致。跨域调查从 K1/K2 就开始，不能等到此时才发现关联。

## 输入与必读

- 输入：全部领域成稿、逐篇验收结果、执行卡中的跨域交接与未决项。
- 读取[跨域协作](../cross-domain.md)、[根概览](../framework/deliverables/root.md)、[团队规范](../framework/deliverables/team-standard.md)、[业务材料](../framework/deliverables/business.md)、[发布合同](../publication.md)。
- 首次提炼 Team Standard 时联读 [constraint extraction](../../../../modus-init/references/constraint-extraction.md)；只处理合同允许的 missing/framework-seed，不覆盖已有人工规范。

## 执行

1. 按[机器消费路线](../evidence/machine-packet.md#六阶段消费与可恢复记录)复用或定向展开 serviceRelation，与当前源码对照后反查双方最终正文，检查未进入交接表的关系并记录处置。逐条核对跨域交接：调用方向、对象与状态所有者、字段映射、术语、已提交事实、完成信号、失败与恢复责任。在提供方与使用方的实际最终正文中双向核对，不能只看 handoff 或域名列表。
2. 冲突回到所属 K3/K4 修复并重验受影响页、图和案例；变更传播按跨域合同执行，不能用根概览中的模糊说法掩盖下层差异。
3. 按根概览合同编写系统目的、能力关系、运行架构、导航和开发排障入口。多 Domain 或多运行单元项目提供系统关系/运行图及交接表，清楚解释方向、所有者和完成信号。
4. init 按合同初始化缺失团队规范；reinit 保留已有人工规范与 business。每个新增 Domain 使用一次 `modus knowledge seed-business --domain <slug> --json` 创建缺失索引，不手写 business 种子或在错误层级建目录。
5. 结构迁移先建立新落点、完成语义回读、修复全部生成正文入链与导航，再按原哈希删除旧生成文件。未证明退役不删，人工内容沿所有权规则保护。

## 产出与出口

系统概览、共享规范和跨域交接可复核且无待修冲突后，进入 [K6 核验发布](k6-publish.md)。reinit 中未变的正文与主图跳写；仅锚点或编辑偏好变化不能触发全库重排。
