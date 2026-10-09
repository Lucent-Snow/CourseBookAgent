import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import ts from 'typescript'

const source = await readFile(new URL('../src/api/product.ts', import.meta.url), 'utf8')
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
}).outputText
const { productApi } = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`)

test('source selection stays in the snapshot and does not restrict generated chapters', async (t) => {
  const calls = []
  t.mock.method(globalThis, 'fetch', async (path, init) => {
    calls.push({ path, body: JSON.parse(init.body) })
    return new Response(JSON.stringify({ snapshot_id: 'snap-test', job_id: 'job-test' }))
  })
  // Non-contiguous source lecture numbers must not become chapter numbers.
  await productApi.createSnapshot('ds-test', ['rev-lecture-1', 'rev-lecture-5', 'rev-lecture-6'])
  await productApi.startRun('74397', 'snap-test', 3, true)
  assert.deepEqual(calls[0].body.resource_revision_ids, ['rev-lecture-1', 'rev-lecture-5', 'rev-lecture-6'])
  assert.deepEqual(calls[1], {
    path: '/api/generate',
    body: { snapshot_id: 'snap-test', regenerate: false, review: true, concurrency: 3, course_id: '74397' },
  })
})

test('uploaded material can start a book without a course identifier', async (t) => {
  t.mock.method(globalThis, 'fetch', async (_path, init) => {
    assert.deepEqual(JSON.parse(init.body), {
      snapshot_id: 'snap-upload', regenerate: false, review: false, concurrency: 1,
    })
    return new Response(JSON.stringify({ job_id: 'job-upload' }))
  })
  await productApi.startRun('', 'snap-upload', 1, false)
})
