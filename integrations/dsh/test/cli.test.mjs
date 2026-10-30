import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import { readFile, writeFile } from 'node:fs/promises'
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
  const { root, cli, call } = await createCliProject(t, 'authoring/simple-reservation/')
  const document = 'modus/knowledge/domain/reservation/references/modules/create-reservation.md'
  const original = await readFile(join(root, document), 'utf8')
  const digest = createHash('sha256').update(original).digest('hex')
  const clarification = '预约记录仅存于服务实例内存，进程退出后不会持久保存。'
  const updated = `${original.trimEnd()}\n\n${clarification}\n`
  const knowledgeBefore = await snapshot(join(root, 'modus/knowledge'))
  const request = join(root, 'knowledge-update.json')
  const update = async payload => {
    await writeFile(request, JSON.stringify(payload))
    return cli('knowledge', 'update', '--input', request)
  }

  const impact = await call('modus_knowledge_impact', {
    changedFiles: ['reservation_source.py'], validation: 'passed',
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
    request: '创建预约的数据持久化边界', paths: ['reservation_source.py'],
  })
  assert.ok(JSON.stringify(context.result).includes(clarification))
  const verification = await call('modus_verify_knowledge', { domain: 'reservation' })
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
    'modus/knowledge/domain/reservation/references/new.md': '# Must not be written\n',
    'README.md': '# Outside knowledge\n',
  } }), error => error.code === 2)
  assert.deepEqual(await snapshot(join(root, 'modus/knowledge')), afterWrite)
  assert.deepEqual(await readFile(join(root, 'README.md')), readme)

  const changed = Object.keys(afterWrite).filter(path => afterWrite[path] !== knowledgeBefore[path])
  assert.deepEqual(changed, [document.slice('modus/knowledge/'.length)])
})
