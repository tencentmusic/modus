import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import { readFile, writeFile, mkdir } from 'node:fs/promises'
import { join } from 'node:path'
import { test } from 'node:test'
import { createCliProject, snapshot } from './support/cli.mjs'

const requiresCli = { skip: !process.env.MODUS_TEST_EXECUTABLE }

test('real CLI round trip preserves project bytes and shell metacharacters', requiresCli, async t => {
  const { root, call } = await createCliProject(t, 'simple_service/')
  const before = await snapshot(root)
  const status = await call('modus_status')
  assert.equal(status.exitCode, 0)
  assert.ok(JSON.stringify(status.result).includes('dsh'))
  const context = await call('modus_context', {
    request: "--order ' $(touch injected) `touch injected2`",
    paths: ['order/order_service.py'],
    forChange: true,
  })
  assert.equal(context.exitCode, 0)
  assert.ok(JSON.stringify(context.result).includes('order_service.py'))
  const impact = await call('modus_knowledge_impact', {
    changedFiles: ['order/order_service.py'], validation: 'passed',
  })
  assert.deepEqual(impact.result.writes, [])
  const verification = await call('modus_verify_knowledge')
  assert.equal(verification.exitCode, 0)
  assert.equal(verification.result.status, 'clean')
  assert.deepEqual(await snapshot(root), before)
})

test('published tools retrieve CAS updates and preserve rejected writes', requiresCli, async t => {
  // 复用当前保留的联系人导入样稿，源码测试与隔离安装共同验证知识写入边界。
  const { root, cli, call } = await createCliProject(t, 'authoring/async-import/')
  const document = 'modus/knowledge/domain/contact-import/references/modules/submission-query.md'
  const original = await readFile(join(root, document), 'utf8')
  const digest = createHash('sha256').update(original).digest('hex')
  const clarification = 'DSH_CAS_MEMORY_BOUNDARY：导入任务仅存于导入器实例内存，进程退出后不会持久保存。'
  // 使用独有检索标识定位新增事实，避免长篇样稿的其他相关片段挤占预算。
  const updated = original.replace(/^(# .+)$/m, `$1\n\n${clarification}`)
  const knowledgeBefore = await snapshot(join(root, 'modus/knowledge'))
  const request = join(root, 'knowledge-update.json')
  const update = async payload => {
    await writeFile(request, JSON.stringify(payload))
    return cli('knowledge', 'update', '--input', request)
  }

  const impact = await call('modus_knowledge_impact', {
    changedFiles: ['import_source.py'], validation: 'passed',
  })
  assert.ok(impact.result.candidates.some(candidate => candidate.path === document))
  assert.deepEqual(impact.result.writes, [])
  assert.deepEqual(await snapshot(join(root, 'modus/knowledge')), knowledgeBefore)

  // 写入仍经过 Skill 使用的公开 CLI；原生工具不获得额外的写入接口。
  const payload = { documents: { [document]: updated }, expectedHashes: { [document]: digest } }
  const written = JSON.parse((await update(payload)).stdout)
  assert.deepEqual(written.writes, [document])
  assert.equal(await readFile(join(root, document), 'utf8'), updated)
  const context = await call('modus_context', {
    request: 'DSH_CAS_MEMORY_BOUNDARY', paths: ['import_source.py'],
  })
  assert.ok(JSON.stringify(context.result).includes(clarification), JSON.stringify(context.result))
  const verification = await call('modus_verify_knowledge', { domain: 'contact-import' })
  assert.equal(verification.exitCode, 0)
  assert.equal(verification.result.status, 'clean')

  const afterWrite = await snapshot(join(root, 'modus/knowledge'))
  const stale = { ...payload, documents: { [document]: `${updated}\n旧写者的覆盖。\n` } }
  await assert.rejects(update(stale), error => {
    assert.equal(error.code, 1)
    const result = JSON.parse(error.stdout)
    assert.deepEqual(result.writes, [])
    assert.ok(result.conflicts.length > 0)
    return true
  })
  const readme = await readFile(join(root, 'README.md'))
  await assert.rejects(update({ documents: {
    'modus/knowledge/domain/contact-import/references/new.md': '# Must not be written\n',
    'README.md': '# Outside knowledge\n',
  } }), error => error.code === 2)
  assert.deepEqual(await snapshot(join(root, 'modus/knowledge')), afterWrite)
  assert.deepEqual(await readFile(join(root, 'README.md')), readme)

  const changed = Object.keys(afterWrite).filter(path => afterWrite[path] !== knowledgeBefore[path])
  assert.deepEqual(changed, [document.slice('modus/knowledge/'.length)])
})


test('member publication reads the workspace card through the real CLI', requiresCli, async t => {
  const { execFileSync } = await import('node:child_process')
  const { root, cli, call } = await createCliProject(t, 'simple_service/')
  const members = ['orders', 'payments'].map(id => ({ id, path: id }))
  for (const member of members) {
    await mkdir(join(root, member.path))
    execFileSync('git', ['init', '-q', join(root, member.path)])
  }
  await writeFile(join(root, '.modus/config.yaml'), JSON.stringify({ kind: 'workspace', workspace: { members } }))
  await mkdir(join(root, 'modus/.cache/knowledge-authoring'), { recursive: true })
  const card = { modus: { authoring: { schemaVersion: 2, executionMode: 'serial', members: {
    orders: { path: 'orders', domains: { core: { status: 'pending' } } },
  } } } }
  await writeFile(join(root, 'modus/.cache/knowledge-authoring/scope-confirmation.md'), `---\n${JSON.stringify(card)}\n---\n`)
  const before = await snapshot(root)
  const result = await call('modus_verify_knowledge', { member: 'orders', publication: true })
  assert.equal(result.exitCode, 4)
  assert.deepEqual(result.result.scope, { domain: null, member: 'orders', memberPath: 'orders' })
  assert.ok(result.result.counts['authoring-domain-incomplete'])
  assert.equal(result.result.counts['authoring-card-unavailable'], undefined)
  // 未声明 member 的原生工具可直接走 Skill 的 CLI 入口，保留相同报告与退出码。
  await assert.rejects(cli('knowledge', 'verify', '--publication', '--member', 'orders', '--json'), error => {
    assert.equal(error.code, result.exitCode)
    assert.deepEqual(JSON.parse(error.stdout), result.result)
    return true
  })
  assert.deepEqual(await snapshot(root), before)
})
