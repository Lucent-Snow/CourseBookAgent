import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import ts from 'typescript'

const source = await readFile(new URL('../src/lib/time-node.ts', import.meta.url), 'utf8')
const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText
const { timeRangeStart, formatClock, withStartParam, videoIndexFrom } = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`)

test('parses the start second of a subtitle time range', () => {
  assert.equal(timeRangeStart('01:09:01-01:12:28'), 4141)
  assert.equal(timeRangeStart('32:42-37:20'), 1962)
  assert.equal(timeRangeStart('05:30-12:40 → c005'), 330)
  assert.equal(timeRangeStart('没有时间'), 0)
})

test('formats a clock label and appends ts inside the zhiyun hash route', () => {
  assert.equal(formatClock(4141), '1:09:01')
  assert.equal(formatClock(90), '01:30')
  assert.equal(
    withStartParam('https://interactivemeta.cmc.zju.edu.cn/#/replay?course_id=84429&sub_id=1&tenant_code=112', 4141),
    'https://interactivemeta.cmc.zju.edu.cn/#/replay?course_id=84429&sub_id=1&tenant_code=112&ts=4141',
  )
  assert.equal(withStartParam('https://example.com/play?ts={ts}', 90), 'https://example.com/play?ts=90')
  assert.equal(withStartParam('', 90), '')
})

test('reads the video index out of the book render config', () => {
  assert.deepEqual(videoIndexFrom({ video_index: { '第 1 讲': { file: 'https://x/1.mp4' } } }), { '第 1 讲': { file: 'https://x/1.mp4' } })
  assert.deepEqual(videoIndexFrom(undefined), {})
  assert.deepEqual(videoIndexFrom({ video_index: 'nope' }), {})
})
