import assert from 'node:assert/strict'
import { test } from 'node:test'
import { resolveConfig } from '../lib/config.js'
import { assertCompatibleVersion, parseReport } from '../lib/protocol.js'
import { quoteArgument } from '../lib/runner.js'

test('CLI version gate accepts only the supported stable protocol range', () => {
  for (const version of ['0.0.5', '0.0.9', 'modus 0.0.5\n']) assertCompatibleVersion(version)
  for (const version of ['0.0.4', '0.1.0', '1.0.0', '0.0.5-alpha', 'garbage']) {
    assert.throws(() => assertCompatibleVersion(version), /openmodus/u)
  }
})

test('configuration rejects relative executables, command fragments and unbounded limits', () => {
  for (const executable of ['', '  ', 'uv run modus', './modus', '../bin/modus', 'bin/modus', 'modus\n', 'bad\0name']) {
    assert.throws(() => resolveConfig({ executable }), /executable/u)
  }
  for (const timeoutMs of [Infinity, NaN, 99, 300_001, 100.5, '60000']) {
    assert.throws(() => resolveConfig({ timeoutMs }), /timeoutMs/u)
  }
  for (const maxOutputBytes of [1, Infinity, 16 * 1024 * 1024 + 1, 1024.5]) {
    assert.throws(() => resolveConfig({ maxOutputBytes }), /maxOutputBytes/u)
  }
  assert.equal(resolveConfig().executable, 'modus')
  assert.equal(resolveConfig({ executable: "/opt/项目 it's modus" }).executable, "/opt/项目 it's modus")
  assert.throws(() => quoteArgument('bad\0argument'), /NUL/u)
})

test('malformed JSON retains its cause and valid findings retain their values', () => {
  assert.throws(() => parseReport('not-json'), error => error.cause instanceof SyntaxError)
  assert.deepEqual(parseReport('{"status":"issues","findings":[{"line":7}]}'), {
    status: 'issues', findings: [{ line: 7 }],
  })
})
