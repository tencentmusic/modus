import assert from 'node:assert/strict'
import { execFile } from 'node:child_process'
import { copyFile, cp, mkdir, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { parseArgs, promisify } from 'node:util'
import { createInstallProfile } from './package-profile.mjs'

const execute = promisify(execFile)
const npm = process.env.npm_execpath
assert.ok(npm, 'Run through npm run smoke:package or npm run smoke:registry')
const { values, positionals } = parseArgs({
  options: { registry: { type: 'boolean', default: false } },
  allowPositionals: true,
})
const packageSpec = positionals[0]
assert.ok(values.registry
  ? positionals.length === 1 && /^@modus-ai\/modus@\d+\.\d+\.\d+(?:-[\w.-]+)?$/u.test(packageSpec)
  : positionals.length === 0, 'Registry verification requires an exact @modus-ai/modus@VERSION')

const root = await mkdtemp(join(tmpdir(), 'modus-dsh-package 项目-'))
const registry = 'https://registry.npmjs.org'
const fixtureRoot = new URL('../../../tests/fixtures/', import.meta.url)

async function runNpm(args, cwd) {
  // 锁文件和隔离安装使用同一公开 registry，避免机器默认镜像改变离线解析。
  return execute(process.execPath, [npm, ...args, `--registry=${registry}`], {
    cwd, maxBuffer: 4 * 1024 * 1024, timeout: 180_000,
  })
}

async function packPlugin() {
  const args = ['pack', '--json', '--ignore-scripts', '--pack-destination', root]
  if (values.registry) args.push(packageSpec)
  const [manifest] = JSON.parse((await runNpm(args)).stdout)
  const files = new Set(manifest.files.map(file => file.path))
  for (const path of [
    'lib/index.js', 'lib/runner.js', 'lib/index.d.ts', 'cordis.patch.yml',
    'LICENSE', 'README.md', 'architecture.md',
  ]) {
    assert.ok(files.has(path), `缺少分发文件：${path}`)
  }
  assert.ok(![...files].some(path => /^(?:node_modules|test|src|scripts)\//u.test(path)))
  return manifest
}

async function installProfile(manifest) {
  // npm ci 只需缓存中的锁定 tarball；再次 npm install 会重解 peer 范围并依赖元数据缓存。
  const source = JSON.parse(await readFile(new URL('../package.json', import.meta.url), 'utf8'))
  const lock = JSON.parse(await readFile(new URL('../package-lock.json', import.meta.url), 'utf8'))
  const archive = await execute('tar', ['-xOf', join(root, manifest.filename), 'package/package.json'])
  const { profile, profileLock } = createInstallProfile(source, lock, manifest, JSON.parse(archive.stdout))
  await writeFile(join(root, 'package.json'), JSON.stringify(profile))
  await writeFile(join(root, 'package-lock.json'), JSON.stringify(profileLock))
  const installOptions = ['--offline', '--ignore-scripts', '--no-audit', '--no-fund']
  console.log('隔离安装：按宿主锁及归档声明安装插件，保持依赖严格校验。')
  await runNpm(['ci', ...installOptions], root)
  await runNpm(['ls', '--all', '--json', '--offline'], root)
  console.log('隔离安装：完整依赖树校验通过。')
}

async function verifyInstalledPlugin() {
  await copyFile(new URL('./verify-installed.mjs', import.meta.url), join(root, 'verify.mjs'))
  const installation = await execute(process.execPath, [join(root, 'verify.mjs')], { cwd: root })
  process.stdout.write(installation.stdout)

  // 只复制消费者测试与业务样例。包入口从 node_modules 解析，无法回退到 checkout 的 lib。
  await mkdir(join(root, 'test'))
  for (const file of ['plugin.test.mjs', 'cli.test.mjs']) {
    await copyFile(new URL(`../test/${file}`, import.meta.url), join(root, 'test', file))
  }
  await cp(new URL('../test/support/', import.meta.url), join(root, 'test/support'), { recursive: true })
  for (const fixture of ['simple_service', 'authoring/async-import']) {
    await cp(new URL(fixture, fixtureRoot), join(root, 'fixtures', fixture), { recursive: true })
  }
  const behavior = await execute(process.execPath, [
    '--test', 'test/plugin.test.mjs', 'test/cli.test.mjs',
  ], {
    cwd: root,
    env: { ...process.env, MODUS_TEST_FIXTURE_ROOT: join(root, 'fixtures') },
    maxBuffer: 4 * 1024 * 1024,
    timeout: 120_000,
  })
  process.stdout.write(behavior.stdout)
}

try {
  const manifest = await packPlugin()
  await installProfile(manifest)
  await verifyInstalledPlugin()
  console.log(JSON.stringify({
    package: manifest.id,
    source: values.registry ? registry : 'local-build',
    offline: process.env.npm_config_offline === 'true',
    integrity: manifest.integrity,
    cli: process.env.MODUS_TEST_EXECUTABLE ? 'verified' : 'skipped',
  }))
} catch (error) {
  console.error(error.stderr || error.message)
  if (error.stdout) console.error(error.stdout)
  process.exitCode = 1
} finally {
  if (process.env.MODUS_KEEP_SMOKE_ARTIFACTS === '1') {
    console.log(`验收产物保留于 ${root}`)
  } else {
    await rm(root, { recursive: true, force: true })
  }
}
