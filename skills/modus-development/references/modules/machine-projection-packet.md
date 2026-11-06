# N5–N6：创作建议、认证证据与有界交付

## 主要所有者

N5：`machine/projection/lifecycle.py`、`proposals.py`、`scope_candidates.py`、`scope_profiles.py`、`community_signal.py`、`views.py`、`publication.py`。能力与权威对象优先，结构社区辅助；明确 needs-split、remainder、覆盖和降级。

N6：`machine/packet/lifecycle.py` 核验/打包；`context_builder.py` 按意图交付；`query.py` 选择并核对当前源码摘要；`cursor.py` 编解码绑定查询的游标。存储由 `machine/store/bundle.py`、`catalog.py`、`bundle_catalogs.py`、`scope_catalog.py`、`catalog_building.py`、`evidence_records.py`、`contracts.py` 拥有，不能各消费者重复认证。

## 公共 API 与协议

消费者使用 `modus.machine` 导出的 `analyze_repository`、`open_analysis`、`query_evidence`、`build_authoring_context`；传 AnalysisOptions、AnalysisIdentity、EvidenceQuery、ContextRequest 等类型。不依赖私有图或 bundle 目录布局。

打开证据必须同时提供 bundleDigest 与 baselineDigest，先认证根及元数据，再读取有界目录页。证据包不可变、内容寻址、完整核验后原子发布。分析失败不能替换已有完整包，但旧包不能冒充本轮成功。

| Schema | Python 契约 |
| --- | --- |
| `schemas/machine/analysis-receipt.schema.json` | `store/contracts.py: AnalysisReceipt` |
| `evidence-page.schema.json` | `EvidencePage` / EvidenceRecord / CoverageGap |
| `authoring-context-packet.schema.json` | `packet/contracts.py: AuthoringContextPacket` |
| `capability-slice.schema.json` | `capability/contracts.py: CapabilitySlice` |

分析包、select 页和 Authoring Context Packet 的 schemaVersion 均为 1；上下文契约随 CLI 与正文模板同步更新，包含 evidence/coverageGaps/expansionQueries；创作执行卡 version 2 是另一个协议。baselineDigest 是分析身份，sourceDigest 是单个见证内容，不能互换。

Context intent 包含 scope-discovery、module-authoring、constraint-extraction、service-boundary、reinit-diff、coverage-audit。module-authoring 至少需要 candidate/capability/path/symbol 之一；boundary 单独不够。回显 requestedScope，不能对 no-match 悄悄扩大到全仓。

查询同时限制正向条目和完整序列化字节；覆盖缺口不占正向条目配额，但仍占字节。页要有实际正向证据或真耗尽，不能让缺口前缀形成不可推进的空页。游标绑定包和规范过滤条件；是否可改变页大小依当前 codec/测试，不把“改页大小”误认为续页。非空游标不是写作完成门槛。

Scope/Module/constraint/coverage 的 path/symbol 和无匹配范围必须保持真实筛选，服务边界需同时返回入边/出边；不同 selector 轴取交集，域并集通过独立请求合并。回包保存来源、缺口、完整代表路径与裁剪后计数。

查询会再次核对当前 sourceDigest，漂移/不可读转为相应缺口或拒绝语义。N5/N6 不能重新解析源码、从快照制造新事实；当前源码摘要安全检查与语义观察是不同职责。

## 调查与验证

候选数量异常先查 N4 uncovered/omission，再查 proposal 分组/结构 remainder，不拿聚类结果直接命名业务领域。缺证据时根据 expansion handle 精确展开；分页耗尽与业务调查完成无关。

测试：`test_evidence_selection.py`、`test_analysis_pipeline.py`、`machine/test_context_builder.py`、`test_projection.py`、`test_public_contracts.py`、`test_store_validation.py`、`test_progress.py`、`test_architecture.py`、`test_sensitive_literals.py`。

重点保护篡改/跨包混用、基线漂移、游标过滤绑定、预算、no-match 范围、schema 一致性、可选投影降级、发布失败保留旧包，以及诊断不泄漏原始字面量或绝对路径。
