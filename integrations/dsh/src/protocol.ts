import { snapshotJsonValue } from '@deepseek-ai/dsh-util-values'
import type { JsonValue } from '@deepseek-ai/dsh-util-values'

/** 参数与可交付报告的退出码由工具声明；执行器只负责执行与完整性。 */
export interface ModusCommand {
  readonly root: string
  readonly args: readonly string[]
  readonly reportExitCodes: readonly number[]
}

export type ModusReport = {
  readonly exitCode: number
  readonly result: Record<string, JsonValue>
}

export function assertCompatibleVersion(output: string): void {
  const match = /^(?:modus\s+)?(\d+)\.(\d+)\.(\d+)\s*$/iu.exec(output.trim())
  if (!match || Number(match[1]) !== 0 || Number(match[2]) !== 0 || Number(match[3]) < 5) {
    throw new Error('此插件要求执行环境安装 openmodus >=0.0.5,<0.1.0；请检查配置的可执行文件。')
  }
}

/** 只验证传输形状与 JSON 值，业务 findings 由 CLI 报告保留。 */
export function parseReport(output: string): Record<string, JsonValue> {
  let value: JsonValue | undefined
  try {
    value = snapshotJsonValue(JSON.parse(output))
  } catch (cause) {
    throw new Error('Modus 未返回有效 JSON；检查 CLI 版本与执行环境。', { cause })
  }
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error('Modus 返回了不兼容的 JSON 结果；预期为报告对象。')
  }
  return value
}
