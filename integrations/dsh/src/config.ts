/** 配置在插件激活时解析一次；调用过程中不再读取或修改宿主配置。 */
export interface Config {
  /** DSH 执行环境中的程序名或 Bash 绝对路径，不接受命令片段。 */
  executable?: string
  /** 每个 CLI 进程的超时，包括版本检查。 */
  timeoutMs?: number
  /** 每个 CLI 进程可返回的 stdout 字节上限。 */
  maxOutputBytes?: number
}

export type ResolvedConfig = Readonly<Required<Config>>

export function resolveConfig(config: Config = {}): ResolvedConfig {
  const executable = config.executable ?? 'modus'
  if (
    typeof executable !== 'string'
    || !executable.trim()
    || /[\0\r\n]/u.test(executable)
    || (!executable.startsWith('/') && /[\\/\s]/u.test(executable))
  ) {
    throw new Error('Modus executable 必须是程序名或 Bash 绝对路径，不能是相对路径或命令片段。')
  }

  const timeoutMs = config.timeoutMs ?? 60_000
  if (!Number.isInteger(timeoutMs) || timeoutMs < 100 || timeoutMs > 300_000) {
    throw new Error('Modus timeoutMs 必须在 100–300000 之间。')
  }

  const maxOutputBytes = config.maxOutputBytes ?? 2 * 1024 * 1024
  if (!Number.isInteger(maxOutputBytes) || maxOutputBytes < 1024 || maxOutputBytes > 16 * 1024 * 1024) {
    throw new Error('Modus maxOutputBytes 必须在 1024–16777216 之间。')
  }

  return Object.freeze({ executable, timeoutMs, maxOutputBytes })
}
