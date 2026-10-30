// 将同一组回归导向已安装的 DSH 运行时，包括 Electron ASAR；不修改安装目录。
// 锚点为该运行时 @deepseek-ai/dsh/lib/bin.js 的绝对路径。
import { registerHooks } from 'node:module'
import { isAbsolute } from 'node:path'
import { pathToFileURL } from 'node:url'

const anchor = process.env.MODUS_DSH_RUNTIME_ANCHOR
if (!anchor || !isAbsolute(anchor)) throw new Error('MODUS_DSH_RUNTIME_ANCHOR must be an absolute runtime entry path')
const parentURL = pathToFileURL(anchor).href
registerHooks({
  resolve(specifier, context, next) {
    return next(specifier, specifier.startsWith('@deepseek-ai/') ? { ...context, parentURL } : context)
  },
})
