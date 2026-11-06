import type { Context } from '@deepseek-ai/cordis'
import { defineTool } from '@deepseek-ai/dsh-tools'
import type { ModusRunner } from './runner.js'

const rootParameter = {
  type: 'string',
  description: 'Modus 项目根目录，绝对路径或相对当前会话目录；省略表示当前目录。位于子目录时请明确指定项目根。',
} as const
const pathsParameter = {
  type: 'array', items: { type: 'string' },
  description: '相对 Modus 项目根的源码路径；不得把会话开始前或其他人的修改归为本次任务。',
} as const
const reportOutput = {
  schema: { type: 'json' },
  render: (_args: unknown, value: unknown) => [{ type: 'text' as const, text: JSON.stringify(value) }],
} as const

/** 工具拥有参数、CLI 映射与业务退出码；所有 I/O 通过同一个执行边界。 */
export function registerTools(ctx: Context, run: ModusRunner): void {
  ctx.tools.register(defineTool({
    name: 'modus_status',
    description: '只读检查当前项目的 Modus 接入、平台和知识状态。',
    parameters: { root: rootParameter },
    output: reportOutput,
    async execute(args, exec) {
      return run(exec, { root: args.root ?? '.', args: ['status', '--json'], reportExitCodes: [0] })
    },
  }))
  ctx.tools.register(defineTool({
    name: 'modus_context',
    description: '从正式 Markdown、业务约束与当前源码只读检索项目证据，返回来源和缺口；不会重跑初始化分析。',
    parameters: {
      request: { type: 'string', required: true, description: '需要理解、修改或排障的具体任务。' },
      root: rootParameter,
      paths: pathsParameter,
      forChange: { type: 'boolean', description: '任务是否用于代码变更。' },
    },
    output: reportOutput,
    async execute(args, exec) {
      const argv = ['context', 'resolve', '--scope=project-read', '--format=json']
      if (args.forChange) argv.push('--purpose=change')
      for (const path of args.paths ?? []) argv.push(`--path=${path}`)
      argv.push('--', args.request)
      return run(exec, { root: args.root ?? '.', args: argv, reportExitCodes: [0] })
    },
  }))
  ctx.tools.register(defineTool({
    name: 'modus_knowledge_impact',
    description: '根据本任务实际变更只读检查受影响的知识和锚点，返回候选、冲突及验证状态，供知识维护工作流判断。',
    parameters: {
      root: rootParameter,
      changedFiles: { ...pathsParameter, required: true },
      validation: { type: 'string', enum: ['passed', 'failed'], required: true, description: '本次实现是否已通过验证；未验证使用 failed，不推定成功。' },
    },
    output: reportOutput,
    async execute(args, exec) {
      const argv = ['knowledge', 'sync', `--validation=${args.validation}`]
      for (const path of args.changedFiles) argv.push(`--changed-file=${path}`)
      return run(exec, { root: args.root ?? '.', args: argv, reportExitCodes: [0, 1] })
    },
  }))
  ctx.tools.register(defineTool({
    name: 'modus_verify_knowledge',
    description: '只读核验知识结构、链接和源码锚点；保留完整发现与非零核验码，不自动修复。',
    parameters: {
      root: rootParameter,
      domain: { type: 'string', description: '可选的领域标识。' },
      member: { type: 'string', description: '已配置的工作区成员 ID；需 publication，root 指向工作区根。' },
      publication: { type: 'boolean', description: '是否执行更严格的发布核验。' },
    },
    output: reportOutput,
    async execute(args, exec) {
      const argv = ['knowledge', 'verify', '--json']
      if (args.domain !== undefined) argv.push(`--domain=${args.domain}`)
      if (args.member !== undefined) argv.push(`--member=${args.member}`)
      if (args.publication) argv.push('--publication')
      return run(exec, { root: args.root ?? '.', args: argv, reportExitCodes: [0, 4] })
    },
  }))
}
