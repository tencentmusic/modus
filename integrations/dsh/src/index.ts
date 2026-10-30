import type { Context } from '@deepseek-ai/cordis'
import { resolveConfig } from './config.js'
import type { Config } from './config.js'
import { registerGuidance } from './guidance.js'
import { createRunner } from './runner.js'
import { registerTools } from './tools.js'

export type { Config } from './config.js'
export const name = 'modus-project-knowledge'
export const inject = ['tools', 'shell', 'shellEnv', 'workingDirectory', 'systemPrompt']

/** 注册归属当前 Cordis 作用域，插件卸载时由宿主统一释放。 */
export function apply(ctx: Context, config: Config = {}): void {
  const resolved = resolveConfig(config)
  const run = createRunner(ctx, resolved)
  registerGuidance(ctx, resolved)
  registerTools(ctx, run)
}
