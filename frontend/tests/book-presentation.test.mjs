import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import ts from 'typescript'
const source = await readFile(new URL('../src/lib/book-presentation.ts', import.meta.url), 'utf8')
const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText
const { readerText, readerBook } = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`)
test('reader omits unresolved claims and internal evidence without mutating saved book', () => {
  assert.equal(readerText('概率为 $0.5$。结果为 0.9[待核]。事件互斥。'), '概率为 $0.5$。事件互斥。')
  assert.equal(readerText('定义清楚。相关数值均须以原课件核对。出自原资料的说明。结论成立。'), '定义清楚。结论成立。')
  const original = { title: '书', warnings: ['待核'], chapters: [{ sections: [{ content: '定义。', source_labels: ['private'] }], warnings: ['note'] }] }
  const projected = readerBook(original)
  assert.deepEqual(projected.warnings, [])
  assert.deepEqual(projected.chapters[0].sections[0].source_labels, [])
  assert.deepEqual(original.warnings, ['待核'])
})

test('reader keeps subtitle time links so chapters can jump back to the video', () => {
  const book = { chapters: [{ sections: [{ time_links: ['01:09:01-01:12:28'] }] }] }
  assert.deepEqual(readerBook(book).chapters[0].sections[0].time_links, ['01:09:01-01:12:28'])
})
