import assert from 'node:assert/strict'
import { test } from 'node:test'
import * as plugin from '@modus-ai/modus'
import { createHarness, success } from './support/runtime.mjs'

test('Cordis registers four tools and context, then disposes and reloads cleanly', async t => {
  const h = await createHarness(t)
  assert.equal(h.ctx.tools.schemas().length, 4)
  // 旧版内置 executor；新版通过服务注入，测试复用两版公开边界。
  h.ctx.tools.setExecutor?.({ describe: () => ({ schemas: h.ctx.tools.schemas() }) })
  const assembly = await h.ctx.systemPrompt.assemble()
  assert.ok(assembly.contexts.some(item => item.name === 'modus:project-knowledge'))
  await h.fiber.dispose()
  assert.equal(h.ctx.tools.schemas().length, 0)
  assert.ok(!(await h.ctx.systemPrompt.assemble()).contexts.some(item => item.name === 'modus:project-knowledge'))
  const reloaded = await h.ctx.plugin(plugin, {})
  assert.equal(h.ctx.tools.schemas().length, 4)
  await reloaded.dispose()
})

test('knowledge maintenance uses the same configured executable as native tools', async t => {
  const executable = "/opt/Modus project/it's modus"
  const h = await createHarness(t, { config: { executable } })
  h.ctx.tools.setExecutor?.({ describe: () => ({ schemas: h.ctx.tools.schemas() }) })
  const context = (await h.ctx.systemPrompt.assemble()).contexts.find(item => item.name === 'modus:project-knowledge')
  const quotedExecutable = "'/opt/Modus project/it'\\''s modus'"
  assert.ok(context.text.includes(quotedExecutable))
  await h.call('modus_status')
  assert.ok(h.calls[0].command.startsWith(quotedExecutable))
})

test('calls follow the session directory, signal, environment and sandbox policy', async t => {
  const h = await createHarness(t, { sandboxMode: 'workspace-write' })
  await h.call('modus_context', { root: '../project', request: '--help; $(touch nope)', paths: ["a'b.py"], forChange: true })
  assert.equal(h.calls.length, 2)
  const request = h.calls[1]
  assert.equal(request.workdir, '/remote/项目 one')
  assert.equal(request.signal, h.exec.signal)
  assert.deepEqual(request.sandboxPolicy, { mode: 'read-only', workspaceRoot: '/remote/项目 one' })
  assert.deepEqual(request.dshEnv, { DSH_SESSION_ID: 'one' })
  assert.equal(request.onExpiry, 'kill')
  assert.ok(request.command.includes("'--' '--help; $(touch nope)'"))
  assert.ok(request.command.includes("'--path=a'\\''b.py'"))
  h.exec.agent.session = { id: 'two', cwd: '/different/world' }
  await h.call('modus_status')
  assert.equal(h.calls[2].workdir, '/different/world')
  assert.equal(h.calls[3].dshEnv.DSH_SESSION_ID, 'two')
})

test('missing session or sandbox policy fails before execution', async t => {
  const h = await createHarness(t, { sandboxMode: 'read-only', policy: false })
  await assert.rejects(h.call('modus_status'), /sandboxPolicy/u)
  await assert.rejects(h.call('modus_status', {}, { signal: h.exec.signal }), /会话/u)
  assert.equal(h.calls.length, 0)
})

test('model arguments are validated before entering the CLI', async t => {
  const h = await createHarness(t)
  await assert.rejects(h.call('modus_context', { request: 1 }), /request/u)
  await assert.rejects(h.call('modus_knowledge_impact', { changedFiles: [] }), /validation/u)
  await assert.rejects(h.call('modus_knowledge_impact', { changedFiles: [], validation: 'unknown' }), /validation/u)
  assert.equal(h.calls.length, 0)
})

test('verification findings and impact conflicts keep nonzero exit codes and reports', async t => {
  const h = await createHarness(t, { execute: spec => {
    if (spec.command.includes("'--version'")) return success('0.0.5')
    if (spec.command.includes("'verify'")) return success('{"status":"issues","findings":["drift"]}', { exitCode: 4 })
    return success('{"status":"partial","conflicts":["changed"]}', { exitCode: 1 })
  } })
  assert.deepEqual(await h.call('modus_verify_knowledge', { domain: '-domain', publication: true }), {
    exitCode: 4, result: { status: 'issues', findings: ['drift'] },
  })
  assert.deepEqual(await h.call('modus_knowledge_impact', { changedFiles: ['--file'], validation: 'failed' }), {
    exitCode: 1, result: { status: 'partial', conflicts: ['changed'] },
  })
  assert.ok(h.calls.at(-1).command.includes("'--changed-file=--file'"))
})

for (const [label, outcome, message] of [
  ['timeout with exit zero', success('{}', { timedOut: true }), /超时/u],
  ['cancelled with exit zero', success('{}', { aborted: true }), /取消/u],
  ['missing exit code', success('{}', { exitCode: null }), /终止/u],
  ['sandbox runner failure', success('{}', { sandbox: { runnerFailed: true } }), /沙箱/u],
  ['terminated process', success('{}', { signal: 'SIGTERM' }), /终止/u],
  ['sandbox denial', success('{}', { sandbox: { denied: true } }), /沙箱/u],
  ['truncated JSON', success('{}', { stdout: { text: '{}', truncated: true } }), /上限/u],
  ['invalid JSON', success('not-json'), /JSON/u],
  ['non-object JSON', success('[]'), /JSON/u],
  ['nonfinite JSON', success('{"n":1e999}'), /JSON/u],
  ['CLI failure', success('{"error":"failure"}', { exitCode: 3 }), /exit 3/u],
]) {
  test(`rejects ${label} instead of reporting evidence`, async t => {
    const h = await createHarness(t, { execute: spec => spec.command.includes("'--version'") ? success('0.0.5') : outcome })
    await assert.rejects(h.call('modus_status'), message)
  })
}

test('cancellation drains the execution result before settling the tool call', async t => {
  const controller = new AbortController()
  let drained = false
  const h = await createHarness(t, { execute: async spec => {
    controller.abort()
    await Promise.resolve()
    drained = true
    return success('{}', { aborted: true })
  } })
  await assert.rejects(h.call('modus_status', {}, { ...h.exec, signal: controller.signal }))
  assert.equal(drained, true)
  assert.equal(h.calls.length, 1)
  await assert.rejects(h.call('modus_status', {}, { ...h.exec, signal: controller.signal }))
  assert.equal(h.calls.length, 1)
})

test('invalid root and NUL arguments fail before any shell call', async t => {
  const h = await createHarness(t)
  await assert.rejects(h.call('modus_status', { root: ' ' }), /root/u)
  await assert.rejects(h.call('modus_context', { request: 'bad\0query' }), /NUL/u)
  await assert.rejects(h.call('modus_context', { request: 'query', paths: ['bad\0path'] }), /NUL/u)
  assert.equal(h.calls.length, 0)
})

test('failed or incompatible version probes never execute the requested command', async t => {
  for (const version of [success('0.0.4'), success('', { exitCode: 127, stderr: { text: 'missing CLI', truncated: false } })]) {
    const h = await createHarness(t, { execute: () => version })
    await assert.rejects(h.call('modus_status'), version.exitCode === 127 ? /missing CLI/u : /openmodus/u)
    assert.equal(h.calls.length, 1)
  }
})

test('business exit codes cannot leak into tools that do not declare them', async t => {
  const h = await createHarness(t, { execute: spec => spec.command.includes("'--version'")
    ? success('0.0.5') : success('{"status":"issues"}', { exitCode: 4 }) })
  await assert.rejects(h.call('modus_status'), /exit 4/u)
  await assert.rejects(h.call('modus_knowledge_impact', { changedFiles: [], validation: 'passed' }), /exit 4/u)
})
