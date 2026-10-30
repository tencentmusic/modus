// 此文件复制到隔离目录运行，导入只能解析到已安装的产物与宿主依赖。
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import { Context } from '@deepseek-ai/cordis'
import { loadOverlayPatches, composeEntries } from '@deepseek-ai/dsh-app-boot'
import SystemPrompt from '@deepseek-ai/dsh-system-prompt'
import Tools from '@deepseek-ai/dsh-tools'
import * as plugin from '@modus-ai/modus'

const packageRoot = new URL('./node_modules/@modus-ai/modus/', import.meta.url)
const manifest = JSON.parse(await readFile(new URL('package.json', packageRoot), 'utf8'))
assert.equal(manifest.engines.dsh, '0.2.1-rc.3 || 0.2.2-alpha.2')
for (const hook of ['preinstall', 'install', 'postinstall', 'prepare']) {
  assert.equal(manifest.scripts?.[hook], undefined, `安装不应依赖 ${hook}`)
}
const patchPath = fileURLToPath(new URL(manifest.dsh.bundle.patch, packageRoot))
const patches = loadOverlayPatches('dsh', patchPath)
assert.ok(patches.length > 0)
assert.equal(composeEntries([patches])[0].name, '@modus-ai/modus')

const ctx = new Context()
const fibers = []
try {
  fibers.push(await ctx.plugin(SystemPrompt, {}))
  fibers.push(await ctx.plugin(Tools))
  fibers.push(await ctx.plugin({
    apply(host) {
      host.provide('shell', {})
      host.provide('shellEnv', {})
      host.provide('workingDirectory', {})
    },
  }))
  const fiber = await ctx.plugin(plugin, {})
  fibers.push(fiber)
  assert.equal(ctx.tools.schemas().length, 4)
  await fiber.dispose()
  assert.equal(ctx.tools.schemas().length, 0)
} finally {
  for (const fiber of fibers.reverse()) await fiber.dispose()
}
console.log('隔离安装通过：DSH patch 已解析，四个工具已注册并释放。')
