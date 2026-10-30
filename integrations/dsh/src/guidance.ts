import type { Context } from '@deepseek-ai/cordis'
import type {} from '@deepseek-ai/dsh-system-prompt'
import type { ResolvedConfig } from './config.js'
import { quoteArgument } from './runner.js'

/** 只注入工作流入口与配置绑定；项目事实在工具调用时按需读取。 */
export function registerGuidance(ctx: Context, config: ResolvedConfig): void {
  ctx.systemPrompt.context({
    name: 'modus:project-knowledge',
    order: 500,
    interpolate: false,
    text: [
      'Modus 提供项目理解、业务约束、当前源码证据与知识维护；DSH 负责执行任务。',
      '涉及项目事实时，按需加载 using-modus，再用 modus_context；保留来源、适用条件和证据缺口，重要结论回读源码。',
      '工具 root 指向已接入 Modus 的项目根；从子目录工作时明确传入 root。未接入时用 modus_status 诊断，不自动初始化。',
      '只有用户明确要求初始化或重建知识时，才加载 /modus-init 或 /modus-reinit。更新知识按 modus-update-knowledge 执行。',
      '完成代码变更前，根据本次任务实际修改和验证结果调用 modus_knowledge_impact；文件变动只是线索，不证明语义变化。',
      '确认职责、业务规则、契约、状态或源码锚点有变化后，加载 modus-sync-knowledge 修订已有主定义并核验。',
      '写入沿用 Modus 读取时哈希与 knowledge update 协议；冲突后重读，保护人工 constraint/ 与 references/business/。',
      `本插件配置的 Modus CLI 是 ${quoteArgument(config.executable)}；执行 Skill 中的 Bash 命令时，用这个可执行文件替换示例中的 modus，避免检索和知识写入使用不同版本。`,
      '知识核验 clean 只证明检查覆盖的结构与锚点，不证明业务结论真实或任务执行成功。',
    ].join('\n'),
  })
}
