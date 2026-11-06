import assert from 'node:assert/strict'
import { execFile } from 'node:child_process'
import { mkdtemp, mkdir, writeFile, rm, readFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { promisify } from 'node:util'
import test from 'node:test'
import { createInstallProfile } from '../scripts/package-profile.mjs'

const execute = promisify(execFile)
const npm = process.env.npm_execpath
const requiresNpm = { skip: !npm && '锁文件回归需通过 npm test 提供当前 npm CLI' }

// 完全由本地 tarball 构造宿主和插件；空缓存与 offline 共同排除开发机历史数据。
async function prepare(t, peerVersion) {
  const root = await mkdtemp(join(tmpdir(), 'modus-package-profile-'))
  t.after(() => rm(root, { recursive: true, force: true }))
  const run = args => execute(process.execPath, [npm, ...args], {
    cwd: root, env: { ...process.env, npm_config_cache: join(root, 'cache') },
    timeout: 30_000, maxBuffer: 1024 * 1024,
  })
  async function pack(directory, metadata) {
    const path = join(root, directory)
    await mkdir(path)
    await writeFile(join(path, 'package.json'), JSON.stringify(metadata))
    const result = await run(['pack', `./${directory}`, '--json', '--ignore-scripts', '--offline'])
    return JSON.parse(result.stdout)[0]
  }
  const host = await pack('host', { name: 'profile-host', version: '1.0.0' })
  const packedPackage = {
    name: 'profile-plugin', version: '1.0.0', peerDependencies: { 'profile-host': peerVersion },
  }
  const manifest = await pack('plugin', packedPackage)
  const source = {
    name: 'profile-author', version: '1.0.0',
    devDependencies: { 'profile-host': `file:${host.filename}` },
  }
  const lock = {
    name: source.name, version: source.version, lockfileVersion: 3, requires: true,
    packages: {
      '': { ...source },
      'node_modules/profile-host': {
        version: host.version, resolved: `file:${host.filename}`, integrity: host.integrity, dev: true,
      },
    },
  }
  const { profile, profileLock } = createInstallProfile(source, lock, manifest, packedPackage)
  await writeFile(join(root, 'package.json'), JSON.stringify(profile))
  await writeFile(join(root, 'package-lock.json'), JSON.stringify(profileLock))
  return { root, run }
}

test('frozen profile installs real tarballs and validates peers with an empty offline cache', requiresNpm, async t => {
  const { root, run } = await prepare(t, '^1.0.0')
  const before = await readFile(join(root, 'package-lock.json'), 'utf8')
  await run(['ci', '--offline', '--ignore-scripts', '--no-audit', '--no-fund'])
  const tree = JSON.parse((await run(['ls', '--all', '--json', '--offline'])).stdout)
  assert.equal(tree.dependencies['profile-plugin'].version, '1.0.0')
  assert.equal(tree.dependencies['profile-plugin'].dependencies['profile-host'].version, '1.0.0')
  assert.equal(await readFile(join(root, 'package-lock.json'), 'utf8'), before)
})

test('frozen profile rejects an incompatible peer instead of accepting the injected lock', requiresNpm, async t => {
  const { run } = await prepare(t, '^2.0.0')
  await assert.rejects(async () => {
    await run(['ci', '--offline', '--ignore-scripts', '--no-audit', '--no-fund'])
    await run(['ls', '--all', '--json', '--offline'])
  }, error => {
    assert.match(error.stderr, /ERESOLVE|ENOTCACHED|ELSPROBLEMS|invalid|Missing/u)
    return true
  })
})
