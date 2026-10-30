import type { Context } from '@deepseek-ai/cordis'
import type { ToolRunContext } from '@deepseek-ai/dsh-tools'
import type { ShellRunResult } from '@deepseek-ai/dsh-shell'
import type {} from '@deepseek-ai/dsh-agent'
import type {} from '@deepseek-ai/dsh-sandbox-policy'
import type {} from '@deepseek-ai/dsh-shell-env'
import type {} from '@deepseek-ai/dsh-working-directory'

import type { ResolvedConfig } from './config.js'
import { assertCompatibleVersion, parseReport } from './protocol.js'
import type { ModusCommand, ModusReport } from './protocol.js'

export type ModusRunner = (execution: ToolRunContext, command: ModusCommand) => Promise<ModusReport>
type CompletedResult = ShellRunResult & { exitCode: number }

/** ctx.shell 是 Bash 协议；每个参数独立引用，模型文本永不成为命令语法。 */
export function quoteArgument(value: string): string {
  if (value.includes('\0')) throw new Error('Modus 参数不能包含 NUL。')
  return `'${value.replaceAll("'", "'\\''")}'`
}

function assertComplete(result: ShellRunResult): asserts result is CompletedResult {
  if (result.aborted) throw new Error('Modus 调用已取消。')
  if (result.timedOut) throw new Error('Modus 调用超时；缩小任务范围后重试。')
  if (result.sandbox?.denied || result.sandbox?.runnerFailed) {
    throw new Error('DSH 沙箱拒绝或未能执行 Modus；请检查当前会话的执行策略。')
  }
  if (result.signal !== null || result.exitCode === null) {
    throw new Error('Modus 进程被终止，结果不完整。')
  }
  if (result.stdout.truncated) {
    throw new Error('Modus 输出超过上限；请缩小查询范围，不能把截断结果当成完整证据。')
  }
}

/** 所有 I/O 交给 DSH 的执行环境，不在插件进程中读取项目或启动本地子进程。 */
export function createRunner(ctx: Context, config: ResolvedConfig): ModusRunner {
  return async (execution, command) => {
    const { root, args, reportExitCodes } = command
    if (!execution.agent) throw new Error('Modus 工具需要 DSH 会话，无法猜测项目目录。')
    if (!root.trim()) throw new Error('Modus root 不能为空。')
    // 先检查全部参数；非法模型输入不能触发版本探测或其他 Shell 调用。
    const commandLine = [config.executable, '-C', root, ...args].map(quoteArgument).join(' ')
    execution.signal.throwIfAborted()
    const workdir = await ctx.workingDirectory.ensure(execution.agent, execution.signal)
    const policy = ctx.get('sandboxPolicy')
    if (ctx.shell.sandboxMode !== undefined && policy === undefined) {
      throw new Error('DSH shell 已启用沙箱，但缺少 sandboxPolicy 服务。')
    }
    const sandboxPolicy = policy?.resolve({ session: execution.agent.session })
    const dshEnv = ctx.shellEnv.collect(execution)
    const run = async (commandLine: string): Promise<CompletedResult> => {
      execution.signal.throwIfAborted()
      const spec = ctx.shell.resolve({
        command: commandLine,
        workdir,
        signal: execution.signal,
        timeoutMs: config.timeoutMs,
        onExpiry: 'kill',
        stdoutMaxBytes: config.maxOutputBytes,
        dshEnv,
        sandboxPolicy,
      })
      const handle = await ctx.shell.execute(spec)
      // 等待执行服务回收进程后再检查取消，避免工具结束后遗留执行。
      const result = await handle.result()
      execution.signal.throwIfAborted()
      assertComplete(result)
      return result
    }
    // 每次在当前执行环境核验，切换会话/远程后端不会复用宿主上的版本缓存。
    const version = await run(`${quoteArgument(config.executable)} '--version'`)
    if (version.exitCode !== 0) {
      throw new Error(`无法运行 Modus（exit ${version.exitCode}）；请检查执行环境中的 executable。${version.stderr.text || version.stdout.text}`)
    }
    assertCompatibleVersion(version.stdout.text)
    const result = await run(commandLine)
    if (!reportExitCodes.includes(result.exitCode)) {
      throw new Error(`Modus 执行失败（exit ${result.exitCode}）：${result.stderr.text || result.stdout.text}`)
    }
    // 非零核验/冲突码与完整报告同时保留，不能把工具传输成功当成知识 clean。
    return { exitCode: result.exitCode, result: parseReport(result.stdout.text) }
  }
}
