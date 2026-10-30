import { Context } from '@deepseek-ai/cordis'
import Tools from '@deepseek-ai/dsh-tools'
import SystemPrompt from '@deepseek-ai/dsh-system-prompt'
import * as plugin from '@modus-ai/modus'

export const success = (text, extra = {}) => ({
  exitCode: 0, signal: null, aborted: false, timedOut: false, timeoutMs: 60_000,
  stdout: { text, truncated: false }, stderr: { text: '', truncated: false }, ...extra,
})

// 使用真实 Cordis 生命周期、工具注册与参数校验；只替换外部执行环境。
export async function createHarness(t, { execute, config, policy = true, sandboxMode } = {}) {
  const ctx = new Context()
  const calls = []
  const fibers = []
  t.after(async () => {
    for (const fiber of fibers.reverse()) await fiber.dispose()
  })
  fibers.push(await ctx.plugin(SystemPrompt, {}))
  fibers.push(await ctx.plugin(Tools))
  fibers.push(await ctx.plugin({
    name: 'test-execution-world',
    apply(host) {
      host.provide('shell', {
        sandboxMode,
        resolve(request) { return request },
        async execute(spec) {
          calls.push(spec)
          return { result: async () => execute
            ? execute(spec)
            : success(spec.command.includes("'--version'") ? '0.0.5\n' : '{"status":"clean"}') }
        },
      })
      host.provide('workingDirectory', { ensure: async agent => agent.session.cwd })
      host.provide('shellEnv', { collect: exec => ({ DSH_SESSION_ID: exec.agent.session.id }) })
      if (policy) host.provide('sandboxPolicy', {
        resolve: ({ session }) => ({ mode: 'read-only', workspaceRoot: session.cwd }),
      })
    },
  }))
  const fiber = await ctx.plugin(plugin, config ?? {})
  fibers.push(fiber)
  const exec = {
    signal: new AbortController().signal,
    agent: { session: { id: 'one', cwd: '/remote/项目 one' } },
  }
  return {
    ctx, calls, exec, fiber,
    call: (name, args = {}, execution = exec) => ctx.tools.get(name).execute(args, execution),
  }
}

