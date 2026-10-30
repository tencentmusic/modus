import { execFile } from 'node:child_process'
import { cp, mkdtemp, readFile, readdir, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join, relative, resolve } from 'node:path'
import { promisify } from 'node:util'
import { createHarness, success } from './runtime.mjs'

const executeFile = promisify(execFile)
const fixtureRoot = process.env.MODUS_TEST_FIXTURE_ROOT
  ? resolve(process.env.MODUS_TEST_FIXTURE_ROOT)
  : new URL('../../../../tests/fixtures/', import.meta.url)

export async function snapshot(root) {
  const entries = await readdir(root, { withFileTypes: true, recursive: true })
  const files = {}
  for (const entry of entries) {
    if (!entry.isFile()) continue
    const path = join(entry.parentPath, entry.name)
    files[relative(root, path)] = await readFile(path, 'base64')
  }
  return files
}

// 隔离目录同时包含空格、Unicode 和单引号，真实执行不能依赖未经引用的路径。
export async function createCliProject(t, fixture) {
  const root = await mkdtemp(join(tmpdir(), "modus-dsh-项目 '"))
  t.after(() => rm(root, { recursive: true, force: true }))
  const source = typeof fixtureRoot === 'string'
    ? join(fixtureRoot, fixture)
    : new URL(fixture, fixtureRoot)
  await cp(source, root, { recursive: true })
  const executable = resolve(process.env.MODUS_TEST_EXECUTABLE)
  const cli = (...args) => executeFile(executable, ['-C', root, ...args])
  await cli('init', '--platform', 'dsh')
  const harness = await createHarness(t, {
    config: { executable },
    async execute(spec) {
      try {
        const result = await executeFile('bash', ['-c', spec.command], {
          cwd: spec.workdir,
          signal: spec.signal,
          timeout: spec.timeoutMs,
          maxBuffer: spec.stdoutMaxBytes,
        })
        return success(result.stdout, { stderr: { text: result.stderr, truncated: false } })
      } catch (error) {
        if (typeof error.code !== 'number') throw error
        return success(error.stdout, {
          exitCode: error.code,
          stderr: { text: error.stderr, truncated: false },
        })
      }
    },
  })
  harness.exec.agent.session.cwd = root
  return { root, cli, call: harness.call }
}
